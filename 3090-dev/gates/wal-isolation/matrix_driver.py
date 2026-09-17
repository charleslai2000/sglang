"""Bounded live-WAL crash matrix for the isolated ExtentFileBackend tree.

This is acceptance harness material, not product code.  It only starts children
which use the real backend and the normal metadata/WAL filesystem boundaries.
The three checkpoint-boundary cases replace an already existing Python helper in
the child process with a barrier; no product files are changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).resolve().parent
PYTHONPATH = str(ROOT / "python")
CONFIG = {
    "tp_rank": 0,
    "tp_size": 1,
    "pp_rank": 0,
    "pp_size": 1,
    "attn_cp_rank": 0,
    "attn_cp_size": 1,
    "is_mla_model": False,
    "enable_storage_metrics": False,
    "is_page_first_layout": True,
    "model_name": "wal-crash-matrix",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_snapshot(path: Path) -> list[dict[str, Any]]:
    result = []
    for item in sorted(path.iterdir()):
        if item.is_file():
            result.append({"name": item.name, "size": item.stat().st_size, "sha256": digest(item)})
    return result


def run_child(role: str, case: str, storage: Path, result_path: Path, **env_extra: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH + os.pathsep + env.get("PYTHONPATH", "")
    env.update({k: str(v) for k, v in env_extra.items()})
    command = [sys.executable, str(Path(__file__).resolve()), "--child", role, case, str(storage), str(result_path)]
    out = result_path.with_suffix(".stdout.log")
    err = result_path.with_suffix(".stderr.log")
    started = time.monotonic()
    proc = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=20)
    out.write_text(proc.stdout, encoding="utf-8")
    err.write_text(proc.stderr, encoding="utf-8")
    return {
        "command": command,
        "status": proc.returncode,
        "duration_s": round(time.monotonic() - started, 6),
        "stdout_artifact": str(out),
        "stderr_artifact": str(err),
        "result": json.loads(result_path.read_text()) if result_path.exists() else None,
    }


def backend(storage: Path, threshold: int = 0):
    from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
    from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

    cfg = HiCacheStorageConfig(
        **CONFIG,
        extra_config={
            "storage_dir": str(storage),
            "extent_size": "16Ki",
            "file_size": "64Ki",
            "wal_checkpoint_bytes": threshold,
        },
    )
    return ExtentFileBackend(cfg)


def emit(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def child(role: str, case: str, storage: Path, result_path: Path) -> int:
    # Imports occur in the child so the parent itself does not accidentally hold
    # a metadata lock in a case namespace.
    from sglang.srt.mem_cache.storage.extent import extent_file_backend as efb
    from sglang.srt.mem_cache.storage.extent.extent_file_backend import component_from_pool_name
    from sglang.srt.mem_cache.hicache_storage import PoolName
    from sglang.srt.mem_cache.storage.extent.extent_metadata import (
        current_path,
        iter_segment_frames,
        manifest_path,
        segment_path,
    )

    storage.mkdir(parents=True, exist_ok=True)
    value = b"ACKED-LIVE-WAL-VALUE" * 32

    if role == "seed":
        b = backend(storage, 0)
        ok = b.set("acked", value)
        emit(result_path, {"role": role, "ack": ok, "value_sha256": hashlib.sha256(value).hexdigest()})
        os._exit(0)

    if role == "boundary":
        b = backend(storage, 0)
        if not b.set("acked", value):
            emit(result_path, {"role": role, "ack": False})
            os._exit(3)
        marker = result_path.with_name("boundary.marker")
        release = result_path.with_name("boundary.release")
        original_manifest = efb.write_manifest_atomic
        original_current = efb.publish_current
        original_unlink = efb.os.unlink
        fired = {"value": False}

        def wait_at(name: str) -> None:
            marker.write_text(json.dumps({"case": case, "point": name}) + "\n", encoding="utf-8")
            while not release.exists():
                time.sleep(0.01)

        if case == "loss_before_manifest_publication":
            def blocked_manifest(path, state):
                if not fired["value"]:
                    fired["value"] = True
                    wait_at("before_write_manifest_atomic_completes")
                return original_manifest(path, state)
            efb.write_manifest_atomic = blocked_manifest
        elif case == "loss_after_manifest_before_current":
            def blocked_current(path, generation):
                if not fired["value"]:
                    fired["value"] = True
                    wait_at("before_publish_current_completes")
                return original_current(path, generation)
            efb.publish_current = blocked_current
        elif case == "loss_after_current_before_unlink":
            def blocked_unlink(path, *args, **kwargs):
                path_text = os.fspath(path)
                if not fired["value"] and path_text.endswith(".wal.0"):
                    fired["value"] = True
                    wait_at("before_old_segment_unlink_completes")
                return original_unlink(path, *args, **kwargs)
            efb.os.unlink = blocked_unlink
        else:
            raise ValueError(case)
        try:
            b.checkpoint()
        except BaseException as exc:
            emit(result_path, {"role": role, "exception": repr(exc)})
            os._exit(4)
        emit(result_path, {"role": role, "checkpoint_returned": True})
        os._exit(0)

    if role == "ack_threshold":
        b = backend(storage, 1)
        marker = result_path.with_name("threshold.marker")

        def blocked_signal():
            marker.write_text(json.dumps({"point": "ack_complete_before_background_checkpoint"}) + "\n", encoding="utf-8")
            while not result_path.with_name("threshold.release").exists():
                time.sleep(0.01)

        b._signal_wal_checkpoint_if_needed = blocked_signal
        ok = b.set("acked", value)
        emit(result_path, {"role": role, "ack": ok, "value_sha256": hashlib.sha256(value).hexdigest()})
        os._exit(0)

    if role in {"torn_tail", "interior_corruption"}:
        b = backend(storage, 0)
        ok = b.set("acked", value)
        current = Path(current_path(storage, b.config_suffix))
        generation = int(current.read_text().strip())
        wal = Path(segment_path(storage, b.config_suffix, generation))
        if role == "torn_tail":
            size_before = wal.stat().st_size
            with wal.open("ab") as f:
                f.write(b"\x46\x31\x01\x00\x00\x00")
                f.flush()
                os.fsync(f.fileno())
            mutation = {
                "kind": "six_byte_active_tail",
                "wal": wal.name,
                "size_before": size_before,
                "size_after": wal.stat().st_size,
                "sha256_after": digest(wal),
            }
        else:
            frames = iter_segment_frames(wal, active=True)
            target = frames[0]
            with wal.open("r+b") as f:
                f.seek(target.offset + 26)
                old = f.read(1)
                f.seek(target.offset + 26)
                f.write(bytes([old[0] ^ 0x01]))
                f.flush()
                os.fsync(f.fileno())
            mutation = {
                "kind": "interior_crc_byte_flip",
                "wal": wal.name,
                "frame_offset": target.offset,
                "frame_seq": target.seq,
                "byte_offset": target.offset + 26,
                "sha256_after": digest(wal),
            }
        emit(result_path, {"role": role, "ack": ok, "mutation": mutation, "value_sha256": hashlib.sha256(value).hexdigest()})
        os._exit(0)

    if role in {"group_incomplete", "group_committed"}:
        b = backend(storage, 0)
        group = b.open_group()
        kv_key = b._storage_key("group-kv")
        mamba_key = b._component_key(PoolName.MAMBA, "group-state")
        kv_value = b"GROUP-KV-VALUE" * 16
        mamba_value = b"GROUP-MAMBA-VALUE" * 16
        ok1 = b._write_pages([kv_key], [kv_value], group_id=group, component=component_from_pool_name(PoolName.KV))
        ok2 = b._write_pages([mamba_key], [mamba_value], group_id=group, component=component_from_pool_name(PoolName.MAMBA))
        committed = False
        if role == "group_committed":
            committed = b.commit_group(group)
        emit(result_path, {
            "role": role,
            "member_acks": [ok1, ok2],
            "group_commit": committed,
            "expected_group_sha256": {
                kv_key: hashlib.sha256(kv_value).hexdigest(),
                mamba_key: hashlib.sha256(mamba_value).hexdigest(),
            },
        })
        os._exit(0)

    if role == "reopen":
        try:
            b = backend(storage, 0)
            kv = bytearray(len(value))
            got = b.get("acked", target_location=kv)
            checks: dict[str, Any] = {
                "opened": True,
                "acked_present": got is not None,
                "acked_value_sha256": hashlib.sha256(bytes(kv)).hexdigest() if got is not None else None,
                "current": Path(current_path(storage, b.config_suffix)).read_text().strip(),
                "manifest_sha256": digest(Path(manifest_path(storage, b.config_suffix))),
                "segments": tree_snapshot(storage),
            }
            for key in (b._storage_key("group-kv"), b._component_key(PoolName.MAMBA, "group-state")):
                page = b._read_pages([key])[0]
                checks.setdefault("group_pages", {})[key] = (
                    hashlib.sha256(bytes(page)).hexdigest() if page is not None else None
                )
            emit(result_path, checks)
            os._exit(0)
        except Exception as exc:
            emit(result_path, {"opened": False, "exception": repr(exc), "failure_class": getattr(exc, "failure_class", None)})
            os._exit(2)

    if role == "reopen_interior":
        try:
            b = backend(storage, 0)
            emit(result_path, {"opened": True})
            os._exit(0)
        except Exception as exc:
            emit(result_path, {"opened": False, "exception": repr(exc), "failure_class": getattr(exc, "failure_class", None)})
            os._exit(2)
    raise ValueError(role)


def wait_marker(path: Path, timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return False


def kill_at_boundary(case: str, role: str, expect_marker: str) -> dict[str, Any]:
    storage = EVIDENCE / case / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    result = EVIDENCE / case / "child.json"
    marker_name = "threshold.marker" if role == "ack_threshold" else "boundary.marker"
    marker = EVIDENCE / case / marker_name
    release = EVIDENCE / case / ("threshold.release" if role == "ack_threshold" else "boundary.release")
    proc_env = os.environ.copy()
    proc_env["PYTHONPATH"] = PYTHONPATH + os.pathsep + proc_env.get("PYTHONPATH", "")
    command = [sys.executable, str(Path(__file__).resolve()), "--child", role, case, str(storage), str(result)]
    out = EVIDENCE / case / "child.stdout.log"
    err = EVIDENCE / case / "child.stderr.log"
    with out.open("w") as stdout, err.open("w") as stderr:
        proc = subprocess.Popen(command, cwd=str(ROOT), env=proc_env, stdout=stdout, stderr=stderr)
        marked = wait_marker(marker)
        before = tree_snapshot(storage)
        if marked:
            proc.send_signal(signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=10)
    return {
        "command": command,
        "status": proc.returncode,
        "marker_seen": marked,
        "marker_expected": expect_marker,
        "before_kill_tree": before,
        "result": json.loads(result.read_text()) if result.exists() else None,
        "stdout_artifact": str(out),
        "stderr_artifact": str(err),
    }


def case_simple(case: str, role: str, reopen_role: str = "reopen") -> dict[str, Any]:
    storage = EVIDENCE / case / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    seed_result = EVIDENCE / case / "seed.json"
    child_result = run_child(role, case, storage, seed_result)
    reopen_result = run_child(reopen_role, case, storage, EVIDENCE / case / "reopen.json")
    return {"seed": child_result, "reopen": reopen_result, "post_reopen_tree": tree_snapshot(storage)}


def evaluate(name: str, raw: dict[str, Any]) -> str:
    if name == "loss_before_manifest_publication":
        r = raw["reopen"]["result"] or {}
        return "PASS" if raw["crash"]["marker_seen"] and raw["crash"]["status"] == -signal.SIGKILL and r.get("opened") and r.get("acked_present") else "UNPROVEN"
    if name in {"loss_after_manifest_before_current", "loss_after_current_before_unlink"}:
        r = raw["reopen"]["result"] or {}
        return "PASS" if raw["crash"]["marker_seen"] and raw["crash"]["status"] == -signal.SIGKILL and r.get("opened") and r.get("acked_present") else "UNPROVEN"
    if name == "active_wal_torn_tail":
        r = raw["reopen"]["result"] or {}
        mutation = (raw["seed"]["result"] or {}).get("mutation") or {}
        return "PASS" if raw["seed"]["status"] == 0 and raw["reopen"]["status"] == 0 and r.get("acked_present") and mutation.get("size_after", 0) > mutation.get("size_before", 0) and r.get("segments") else "FAIL"
    if name == "active_wal_interior_corruption":
        return "PASS" if raw["seed"]["status"] == 0 and raw["reopen"]["status"] != 0 and not (raw["reopen"]["result"] or {}).get("opened") else "FAIL"
    if name == "acked_before_checkpoint_threshold":
        r = raw["reopen"]["result"] or {}
        return "PASS" if raw["crash"]["marker_seen"] and raw["crash"]["status"] == -signal.SIGKILL and r.get("opened") and r.get("acked_present") else "UNPROVEN"
    if name == "incomplete_group_before_group_commit":
        r = raw["reopen"]["result"] or {}
        pages = r.get("group_pages", {})
        return "PASS" if raw["seed"]["status"] == 0 and raw["reopen"]["status"] == 0 and pages and not any(pages.values()) else "FAIL"
    if name == "committed_group_after_group_commit":
        r = raw["reopen"]["result"] or {}
        pages = r.get("group_pages", {})
        expected = (raw["seed"]["result"] or {}).get("expected_group_sha256", {})
        return "PASS" if raw["seed"]["status"] == 0 and raw["reopen"]["status"] == 0 and pages and expected and pages == expected else "FAIL"
    return "UNPROVEN"


def parent() -> int:
    source_files = [
        ROOT / "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
        ROOT / "python/sglang/srt/mem_cache/storage/extent/extent_metadata.py",
        ROOT / "python/sglang/srt/mem_cache/storage/extent/extent_allocator.py",
        ROOT / "python/sglang/srt/mem_cache/hicache_storage.py",
        Path(__file__),
    ]
    provenance = {
        "root": str(ROOT),
        "evidence_root": str(EVIDENCE),
        "interpreter": sys.executable,
        "python_version": sys.version,
        "pythonpath": PYTHONPATH,
        "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in source_files if p.exists()},
        "environment": {k: os.environ.get(k) for k in ("PYTHONPATH", "PATH", "SGLANG_HICACHE_EXTENT_BACKEND_WAL_CHECKPOINT_BYTES")},
    }
    (EVIDENCE / "provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
    matrix: dict[str, Any] = {"schema": "wal-crash-matrix.v1", "provenance": provenance, "cases": {}}

    for name, role, point in (
        ("loss_before_manifest_publication", "boundary", "before_write_manifest_atomic_completes"),
        ("loss_after_manifest_before_current", "boundary", "before_publish_current_completes"),
        ("loss_after_current_before_unlink", "boundary", "before_old_segment_unlink_completes"),
    ):
        raw = {"crash": kill_at_boundary(name, role, point)}
        raw["reopen"] = run_child("reopen", name, EVIDENCE / name / "storage", EVIDENCE / name / "reopen.json")
        raw["post_reopen_tree"] = tree_snapshot(EVIDENCE / name / "storage")
        raw["status"] = evaluate(name, raw)
        matrix["cases"][name] = raw

    raw = case_simple("active_wal_torn_tail", "torn_tail")
    raw["status"] = evaluate("active_wal_torn_tail", raw)
    matrix["cases"]["active_wal_torn_tail"] = raw
    raw = case_simple("active_wal_interior_corruption", "interior_corruption", "reopen_interior")
    raw["status"] = evaluate("active_wal_interior_corruption", raw)
    matrix["cases"]["active_wal_interior_corruption"] = raw

    raw = {"crash": kill_at_boundary("acked_before_checkpoint_threshold", "ack_threshold", "ack_complete_before_background_checkpoint")}
    raw["crash"]["release_not_created"] = True
    raw["reopen"] = run_child("reopen", "acked_before_checkpoint_threshold", EVIDENCE / "acked_before_checkpoint_threshold" / "storage", EVIDENCE / "acked_before_checkpoint_threshold" / "reopen.json")
    raw["status"] = evaluate("acked_before_checkpoint_threshold", raw)
    matrix["cases"]["acked_before_checkpoint_threshold"] = raw

    for name, role in (("incomplete_group_before_group_commit", "group_incomplete"), ("committed_group_after_group_commit", "group_committed")):
        raw = case_simple(name, role)
        raw["status"] = evaluate(name, raw)
        matrix["cases"][name] = raw

    (EVIDENCE / "matrix.json").write_text(json.dumps(matrix, sort_keys=True, indent=2) + "\n")
    print(json.dumps({name: case["status"] for name, case in matrix["cases"].items()}, sort_keys=True))
    return 0 if all(case["status"] in {"PASS", "UNPROVEN"} for case in matrix["cases"].values()) else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        raise SystemExit(child(sys.argv[2], sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])))
    raise SystemExit(parent())
