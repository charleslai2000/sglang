import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (
    ExtentFileBackend,
)
from sglang.srt.mem_cache.storage.extent.extent_metadata import (
    SEGMENT_HEADER_SIZE,
    current_path,
    manifest_path,
    read_current,
    read_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "live-evidence-corrected"
STORAGE = EVIDENCE / "storage"
EVENTS = EVIDENCE / "corrected_live_wal.jsonl"
SUMMARY = EVIDENCE / "corrected_live_wal_summary.json"
PROVENANCE = EVIDENCE / "corrected_live_wal_provenance.json"
CONFIG_SUFFIX = "_live-wal-corrected_0_1"
THRESHOLD = 512


def config():
    return HiCacheStorageConfig(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name="live-wal-corrected",
        extra_config={
            "storage_dir": str(STORAGE),
            "extent_size": "16Ki",
            "file_size": "128Ki",
            "wal_checkpoint_bytes": str(THRESHOLD),
        },
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_binding():
    source_paths = [
        ROOT / "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
        ROOT / "python/sglang/srt/mem_cache/storage/extent/extent_metadata.py",
        ROOT / "python/sglang/srt/mem_cache/hicache_storage.py",
        Path(__file__).resolve(),
    ]
    return {
        str(path.relative_to(ROOT)): {
            "absolute_path": str(path),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in source_paths
    }


def storage_snapshot():
    files = []
    for path in sorted(STORAGE.iterdir()):
        if path.is_file():
            files.append({"name": path.name, "size": path.stat().st_size})
    manifest = manifest_path(str(STORAGE), CONFIG_SUFFIX)
    current = current_path(str(STORAGE), CONFIG_SUFFIX)
    state = read_manifest(manifest) if os.path.exists(manifest) else None
    current_generation = read_current(current) if os.path.exists(current) else None
    usage = shutil.disk_usage(STORAGE)
    return {
        "files": files,
        "wal_segments": [item for item in files if ".wal." in item["name"]],
        "manifest_generation": state.wal_active_gen if state else None,
        "manifest_floor": state.wal_floor if state else None,
        "manifest_checkpoint_lsn": state.checkpoint_lsn if state else None,
        "manifest_entry_count": len(state.entries) if state else None,
        "current_generation": current_generation,
        "filesystem": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        },
    }


def emit(backend, kind, **fields):
    stats = backend.stats_snapshot()
    record = {
        "ts_wall_ns": time.time_ns(),
        "ts_mono_ns": time.monotonic_ns(),
        "kind": kind,
        "stats": stats,
        "wal_generation": backend._wal_generation,
        "wal_offset": backend._wal_offset,
        "wal_active_bytes_calculated": max(
            0, backend._wal_offset - SEGMENT_HEADER_SIZE
        ),
        **fields,
    }
    record["storage"] = storage_snapshot()
    with EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True), flush=True)
    return record


def wait_for_success(backend, target, label, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if backend.stats_snapshot()["wal_checkpoint_successes"] >= target:
            return emit(backend, "checkpoint-success-observed", label=label, target=target)
        time.sleep(0.01)
    emit(backend, "checkpoint-timeout", label=label, target=target)
    raise AssertionError(
        f"checkpoint target {target} not reached for {label}: {backend.stats_snapshot()}"
    )


def wait_for_decline(backend, successes, label, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stats = backend.stats_snapshot()
        if stats["wal_checkpoint_requested"] >= 1 and stats["wal_checkpoint_successes"] == successes:
            return emit(backend, "checkpoint-decline-observed", label=label)
        time.sleep(0.01)
    emit(backend, "checkpoint-decline-timeout", label=label)
    raise AssertionError(
        f"checkpoint decline not reached for {label}: {backend.stats_snapshot()}"
    )


def assert_exact(backend, values):
    for key, expected in values.items():
        target = bytearray(len(expected))
        result = backend.get(key, target)
        if result is None or bytes(target) != expected:
            raise AssertionError(f"value mismatch for {key}")


def write_provenance(source_hashes):
    command_args = [sys.executable, *sys.argv]
    command_shell = " ".join(
        json.dumps(arg) if any(char.isspace() for char in arg) else arg
        for arg in command_args
    )
    effective_pythonpath = os.environ.get("PYTHONPATH", "")
    if effective_pythonpath:
        command_shell = f"PYTHONPATH={json.dumps(effective_pythonpath)} {command_shell}"
    provenance = {
        "command_line": command_args,
        "command_line_shell_form": command_shell,
        "interpreter": sys.executable,
        "python_version": sys.version,
        "effective_pythonpath": effective_pythonpath,
        "working_directory": os.getcwd(),
        "isolated_root": str(ROOT),
        "storage_directory": str(STORAGE),
        "source_binding": source_hashes,
        "scope": "test-only corrected live WAL evidence; no crash evidence",
    }
    PROVENANCE.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return provenance


def main():
    if STORAGE.exists():
        shutil.rmtree(STORAGE)
    STORAGE.mkdir(parents=True)
    for path in (EVENTS, SUMMARY, PROVENANCE):
        if path.exists():
            path.unlink()

    source_hashes = source_binding()
    backend = None
    values = {}
    incomplete_keys = []
    original_pre_close_stats = None
    reopened_stats_before_close = None
    try:
        backend = ExtentFileBackend(config())
        emit(backend, "open", threshold=THRESHOLD, storage=str(STORAGE))
        successful_before = 0
        for cycle in range(4):
            for member in range(4):
                key = f"auto-{cycle}-{member}"
                value = bytes([31 + cycle * 4 + member]) * 2048
                started = time.monotonic_ns()
                if not backend.set(key, bytearray(value)):
                    raise AssertionError(f"write failed for {key}")
                values[key] = value
                emit(
                    backend,
                    "write",
                    cycle=cycle,
                    key=key,
                    bytes=len(value),
                    latency_ns=time.monotonic_ns() - started,
                )
            target = successful_before + 1
            wait_for_success(backend, target, f"automatic-cycle-{cycle}")
            stats = backend.stats_snapshot()
            if stats["wal_active_bytes"] > THRESHOLD:
                raise AssertionError(f"WAL did not reset below threshold: {stats}")
            emit(
                backend,
                "cycle-verified",
                cycle=cycle,
                old_generation=backend._wal_generation - 1,
                new_generation=backend._wal_generation,
            )
            successful_before = target

        group_id = backend.open_group()
        incomplete_keys = [f"incomplete-aborted-{member}" for member in range(4)]
        incomplete_values = [b"incomplete" * 200 for _ in incomplete_keys]
        for key, value in zip(incomplete_keys, incomplete_values):
            staged = backend._write_pages(
                [backend._storage_key(key)], [bytearray(value)], group_id=group_id
            )
            if not staged or backend.exists(key):
                raise AssertionError("incomplete group became visible before commit")
        emit(
            backend,
            "incomplete-group-staged",
            group_id=[group_id[0].hex(), group_id[1]],
            keys=incomplete_keys,
        )
        wait_for_decline(backend, successful_before, "incomplete-group-decline", timeout=2.0)
        if not backend.abort_group(group_id):
            raise AssertionError("incomplete group abort failed")
        emit(
            backend,
            "incomplete-group-aborted",
            group_id=[group_id[0].hex(), group_id[1]],
        )
        post_abort = wait_for_success(
            backend, successful_before + 1, "post-abort-checkpoint"
        )
        successful_before += 1
        if any(backend.exists(key) for key in incomplete_keys):
            raise AssertionError("aborted group became visible")
        assert_exact(backend, values)
        original_pre_close_stats = backend.stats_snapshot()
        emit(
            backend,
            "original-pre-close-integrity-verified",
            value_count=len(values),
            authoritative_checkpoint_count=original_pre_close_stats[
                "wal_checkpoint_successes"
            ],
            post_abort_success_generation=post_abort["wal_generation"],
        )
        if original_pre_close_stats["wal_checkpoint_successes"] != successful_before:
            raise AssertionError("original pre-close count was not authoritative")
        backend.close()
        backend = None

        reopened = ExtentFileBackend(config())
        try:
            assert_exact(reopened, values)
            if any(reopened.exists(key) for key in incomplete_keys):
                raise AssertionError("aborted group recovered as visible")
            reopened_stats_before_close = reopened.stats_snapshot()
            emit(
                reopened,
                "reopen-integrity-verified",
                value_count=len(values),
                reopened_stats=True,
                exact_values=True,
            )
        finally:
            # This close, including its final checkpoint, must finish before the
            # final storage snapshot or corrected summary is written.
            reopened.close()

        final_storage = storage_snapshot()
        summary = {
            "result": "PASS",
            "automatic_successes_before_group": 4,
            "post_abort_checkpoint_success": True,
            "authoritative_original_pre_close_checkpoint_count": original_pre_close_stats[
                "wal_checkpoint_successes"
            ],
            "original_pre_close_stats": original_pre_close_stats,
            "reopened_stats_before_close": reopened_stats_before_close,
            "reopen_values": len(values),
            "final_storage": final_storage,
            "threshold_bytes": THRESHOLD,
            "source_binding": source_hashes,
            "remaining_crash_windows": [
                "No process-loss test was run between data pwrite and WAL sync.",
                "No process-loss test was run between manifest publication and current-pointer publication.",
                "No torn-WAL-tail or interrupted-reclamation test was run.",
                "No crash evidence is claimed by this package.",
            ],
        }
        SUMMARY.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_provenance(source_hashes)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    main()
