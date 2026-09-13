"""CPU-only P3 crash, corruption, and liveness vehicle.

This module is acceptance infrastructure, not a storage or scheduler
mechanism.  Backend recovery is reached only through an explicitly supplied
subprocess command.  The vehicle copies a caller-owned fixture into a
preserved artifact namespace before making a controlled mutation; it never
mutates the caller's storage tree.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import p3_harness
from p3_harness import (
    DEFAULT_ARTIFACT_ROOT,
    ArtifactNamespace,
    GpuLock,
    HarnessError,
    OwnedProcess,
    args_hash,
    cleanup_owned,
    collect_provenance,
    launch_owned,
    rollback_namespace,
    sanitize_argv,
    utc_now,
)


SCHEMA_VERSION = "p3-crash-vehicle.v1"
BACKEND_CASES = {"torn-tail", "committed-corruption", "stale-generation"}
ALL_CASES = BACKEND_CASES | {"process-crash", "no-liveness-loss"}
SEGMENT_HEADER_SIZE = 28
FRAME_HEADER_SIZE = 26
FRAME_SET = 1
FRAME_BATCH_COMMIT = 2
FRAME_GROUP_COMMIT = 3
EVIDENCE_CLASSES = {"UNIT_FIXTURE", "EXPLICIT_ORACLE", "REAL_BACKEND"}
_AUTHORITATIVE_BACKEND_ADAPTER = "p3_authoritative_backend_adapter.py"


def _crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


class CrashVehicleError(HarnessError):
    """The P3 vehicle contract could not be established."""


@dataclasses.dataclass(frozen=True)
class CrashVehicleConfig:
    case: str
    storage_path: Path | None = None
    backend_command: Sequence[str] | None = None
    liveness_command: Sequence[str] | None = None
    restart_config: Any | None = None
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    profile: str = "p3-crash"
    repo_root: Path = Path.cwd()
    cwd: Path | None = None
    timeout: float = 30.0
    poll_interval: float = 0.01
    zero_progress_timeout: float = 1.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise CrashVehicleError(f"storage namespace is not a directory: {path}")
    files: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise CrashVehicleError(f"symlink is not accepted in storage namespace: {item}")
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            files.append({"path": relative, "size": item.stat().st_size, "sha256": _sha256_file(item)})
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _copy_fixture(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise CrashVehicleError(f"test-owned storage path is not a directory: {source}")
    destination.mkdir(parents=True, exist_ok=False)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_symlink():
            raise CrashVehicleError(f"symlink is not accepted in fixture: {item}")
        if item.is_dir():
            target.mkdir()
        elif item.is_file():
            shutil.copy2(item, target)
        else:
            raise CrashVehicleError(f"unsupported fixture entry: {item}")


def _decode_frame(raw: bytes, offset: int) -> tuple[int, int, bytes, int]:
    if offset + FRAME_HEADER_SIZE > len(raw):
        raise CrashVehicleError("fixture has a truncated WAL frame header")
    magic, version, frame_type, _flags, _reserved, payload_len, seq = struct.unpack_from(
        "<IHBBHIQ", raw, offset
    )
    total = FRAME_HEADER_SIZE + payload_len
    if magic != 0x484D3146 or version != 1 or offset + total > len(raw):
        raise CrashVehicleError("fixture has an invalid WAL frame")
    payload = raw[offset + FRAME_HEADER_SIZE : offset + total]
    stored_crc = struct.unpack_from("<I", raw, offset + 22)[0]
    if _crc32c(raw[offset : offset + 22] + payload) != stored_crc:
        raise CrashVehicleError("fixture has a WAL frame CRC mismatch")
    return frame_type, seq, payload, total


def _validate_committed_fixture(storage: Path) -> dict[str, Any]:
    """Validate the minimum product WAL commit graph before any mutation.

    This is deliberately a byte-level fixture oracle.  It does not claim that
    a product backend recovered the fixture; that claim is reserved for
    REAL_BACKEND evidence from the supplied recovery command.
    """

    _current, segment, _generation = _active_wal(storage)
    raw = segment.read_bytes()
    if len(raw) < SEGMENT_HEADER_SIZE:
        raise CrashVehicleError("fixture has no complete WAL segment header")
    magic, version, _flags, _segment_generation, _base_lsn = struct.unpack_from(
        "<IHHQQ", raw, 0
    )
    if magic != 0x484D3153 or version != 1:
        raise CrashVehicleError("fixture has an invalid WAL segment header")
    if _crc32c(raw[:24]) != struct.unpack_from("<I", raw, 24)[0]:
        raise CrashVehicleError("fixture has a WAL segment header CRC mismatch")

    frames: list[dict[str, Any]] = []
    offset = SEGMENT_HEADER_SIZE
    expected_seq = None
    sets: list[dict[str, Any]] = []
    batch_commits: dict[int, int] = {}
    group_commits: dict[tuple[bytes, int], int] = {}
    while offset < len(raw):
        frame_type, seq, payload, consumed = _decode_frame(raw, offset)
        if expected_seq is not None and seq != expected_seq:
            raise CrashVehicleError("fixture WAL sequence is discontinuous")
        expected_seq = seq + 1
        frames.append({"type": frame_type, "seq": seq, "offset": offset, "consumed": consumed})
        if frame_type == FRAME_SET:
            if len(payload) < 40:
                raise CrashVehicleError("fixture SET payload is truncated")
            group_epoch, group_seq, batch_id, member_index, member_count = struct.unpack_from(
                "<16sQQII", payload, 0
            )
            if member_count == 0 or member_index >= member_count:
                raise CrashVehicleError("fixture SET member geometry is invalid")
            cursor = 40
            entry_count = 0
            while cursor < len(payload):
                if cursor + 2 > len(payload):
                    raise CrashVehicleError("fixture SET key length is truncated")
                key_len = struct.unpack_from("<H", payload, cursor)[0]
                entry_size = 2 + key_len + 4 + 4 + 4 + 8 + 1
                if cursor + entry_size > len(payload):
                    raise CrashVehicleError("fixture SET entry is truncated")
                cursor += entry_size
                entry_count += 1
            if not entry_count:
                raise CrashVehicleError("fixture SET has no entries")
            sets.append({
                "group": (group_epoch, group_seq),
                "batch_id": batch_id,
                "member_index": member_index,
                "member_count": member_count,
                "entry_count": entry_count,
                "offset": offset,
                "seq": seq,
            })
        elif frame_type == FRAME_BATCH_COMMIT:
            if len(payload) != 12:
                raise CrashVehicleError("fixture batch commit payload is invalid")
            batch_id, member_count = struct.unpack("<QI", payload)
            batch_commits[batch_id] = member_count
        elif frame_type == FRAME_GROUP_COMMIT:
            if len(payload) != 28:
                raise CrashVehicleError("fixture group commit payload is invalid")
            group_epoch, group_seq, member_count = struct.unpack("<16sQI", payload)
            group_commits[(group_epoch, group_seq)] = member_count
        offset += consumed

    batches: dict[int, list[dict[str, Any]]] = {}
    for item in sets:
        batches.setdefault(item["batch_id"], []).append(item)
    complete_batches = []
    for batch_id, members in batches.items():
        expected_count = batch_commits.get(batch_id)
        if expected_count is None or not members:
            continue
        expected_members = set(range(expected_count))
        actual_members = {item["member_index"] for item in members}
        if len(members) != expected_count or actual_members != expected_members:
            continue
        if any(
            item["batch_id"] != batch_id
            or item["member_count"] != expected_count
            for item in members
        ):
            continue
        complete_batches.append(batch_id)
    committed_groups: dict[tuple[bytes, int], int] = {}
    for item in sets:
        if item["batch_id"] in complete_batches:
            committed_groups[item["group"]] = committed_groups.get(item["group"], 0) + item["entry_count"]
    complete_groups = [
        group for group, count in committed_groups.items()
        if group in group_commits and group_commits[group] == count
    ]
    committed_sets = [
        item
        for item in sets
        if item["batch_id"] in complete_batches and item["group"] in complete_groups
    ]
    committed_set_identities = [
        {
            "offset": item["offset"],
            "seq": item["seq"],
            "batch_id": item["batch_id"],
            "member_index": item["member_index"],
            "member_count": item["member_count"],
            "group_epoch": item["group"][0].hex(),
            "group_seq": item["group"][1],
        }
        for item in committed_sets
    ]
    if not complete_batches or not complete_groups or not committed_set_identities:
        raise CrashVehicleError(
            "fixture must contain at least one committed batch and committed group"
        )
    committed_offsets = {item["offset"] for item in committed_set_identities}
    if not any(
        item["offset"] in committed_offsets
        and item["offset"] + item["consumed"] < len(raw)
        for item in frames
    ):
        raise CrashVehicleError("fixture has no interior committed frame to mutate")
    return {
        "status": "PASS",
        "classification": "EXPLICIT_ORACLE",
        "frame_count": len(frames),
        "set_count": len(sets),
        "complete_batches": sorted(complete_batches),
        "complete_groups": len(complete_groups),
        "committed_set_identities": committed_set_identities,
        "frames": frames,
    }


def _is_bound_authoritative_backend(
    command: Sequence[str], repo_root: Path,
) -> bool:
    """Recognize only the adapter in this reviewed vehicle source tree.

    ``repo_root`` is caller-controlled configuration, so it may not identify
    the trusted tree.  A conflicting root conservatively makes the adapter
    non-authoritative, even when it contains a same-named script.
    """

    if len(command) < 2 or str(command[0]) != sys.executable:
        return False
    try:
        vehicle_source = Path(__file__).resolve().parent
        reviewed_repo_root = vehicle_source.parent.resolve(strict=True)
        supplied_repo_root = Path(repo_root).expanduser().resolve(strict=True)
        if supplied_repo_root != reviewed_repo_root:
            return False
        adapter = (vehicle_source / _AUTHORITATIVE_BACKEND_ADAPTER).resolve(strict=True)
        supplied = Path(str(command[1])).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return supplied == adapter


def _real_backend_capability(
    command: Sequence[str] | None = None, repo_root: Path | None = None,
) -> dict[str, Any]:
    """Report real-backend capability only for the bound adapter identity."""

    if command is None or repo_root is None or not _is_bound_authoritative_backend(command, repo_root):
        return {
            "available": False,
            "status": "NOT_COMPUTABLE",
            "error": "no explicitly bound in-tree authoritative backend adapter",
        }

    try:
        importlib.import_module("sglang.srt.mem_cache.storage.extent.extent_file_backend")
    except Exception as exc:  # capability is deliberately reported, not repaired
        return {
            "available": False,
            "status": "NOT_COMPUTABLE",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"available": True, "status": "PASS", "backend": "ExtentFileBackend"}


def _evidence_classification(evidence: Mapping[str, Any]) -> str | None:
    value = evidence.get("evidence_class", evidence.get("classification"))
    return value if isinstance(value, str) and value in EVIDENCE_CLASSES else None


def _effective_evidence_classification(
    evidence: Mapping[str, Any] | None, *, authoritative: bool,
) -> str | None:
    if evidence is None:
        return None
    classification = _evidence_classification(evidence)
    if classification == "REAL_BACKEND" and not authoritative:
        return "EXPLICIT_ORACLE"
    return classification


def _validate_artifact_root(root: Path) -> None:
    supplied = Path(root).expanduser().absolute().resolve(strict=False)
    required = DEFAULT_ARTIFACT_ROOT.absolute().resolve(strict=False)
    if supplied != required and required not in supplied.parents:
        raise CrashVehicleError(f"artifact root must be under {DEFAULT_ARTIFACT_ROOT}")


def _validate_case(case: str) -> None:
    if case not in ALL_CASES:
        raise CrashVehicleError(f"unsupported P3 case: {case}")


def _command_identity(command: Sequence[str]) -> dict[str, Any]:
    command = [str(item) for item in command]
    return {"argv": sanitize_argv(command), "args_sha256": args_hash(command)}


def _active_wal(storage: Path) -> tuple[Path, Path, int]:
    currents = sorted(storage.glob("hicache.meta*.wal.current"))
    if len(currents) != 1 or any(item.is_symlink() for item in currents):
        raise CrashVehicleError("mutation requires exactly one non-symlink active WAL pointer")
    current = currents[0]
    text = current.read_text(encoding="ascii")
    if not text.endswith("\n") or not text[:-1].isdigit():
        raise CrashVehicleError("mutation refused: active WAL pointer is malformed")
    generation = int(text[:-1])
    prefix = current.name[: -len(".wal.current")]
    segment = storage / f"{prefix}.wal.{generation}"
    if not segment.is_file() or segment.is_symlink():
        raise CrashVehicleError("mutation refused: active WAL segment is absent or unsafe")
    return current, segment, generation


def _mutate_fixture(storage: Path, case: str) -> dict[str, Any]:
    """Perform one fixed, auditable mutation and return its description."""

    _current, segment, generation = _active_wal(storage)
    before = _tree_snapshot(storage)
    if case == "torn-tail":
        payload = b"P3-TORN-TAIL"
        with segment.open("ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fdatasync(stream.fileno())
        description = "append a 12-byte incomplete WAL frame tail to the active segment"
        offset = before["files"][[item["path"] for item in before["files"]].index(segment.name)]["size"]
    elif case == "committed-corruption":
        baseline_fixture = _validate_committed_fixture(storage)
        raw = bytearray(segment.read_bytes())
        committed_offsets = {
            item["offset"] for item in baseline_fixture["committed_set_identities"]
        }
        candidates = [
            item for item in baseline_fixture["frames"]
            if item["type"] == FRAME_SET
            and item["offset"] in committed_offsets
            and item["offset"] + item["consumed"] < len(raw)
        ]
        if not candidates:
            raise CrashVehicleError("mutation refused: no interior committed SET frame")
        target = candidates[0]
        crc_offset = target["offset"] + 22
        raw[crc_offset] ^= 0x01
        segment.write_bytes(raw)
        with segment.open("r+b") as stream:
            os.fdatasync(stream.fileno())
        description = "flip one byte in the CRC of an interior committed WAL frame"
        offset = crc_offset
    elif case == "stale-generation":
        baseline_fixture = _validate_committed_fixture(storage)
        raw = bytearray(segment.read_bytes())
        offset_cursor = SEGMENT_HEADER_SIZE
        target_offset = None
        old_generation = None
        target_batch = None
        committed_offsets = {
            item["offset"] for item in baseline_fixture["committed_set_identities"]
        }
        while offset_cursor + FRAME_HEADER_SIZE <= len(raw):
            frame_type, _seq, frame_payload, total = _decode_frame(raw, offset_cursor)
            if frame_type == FRAME_SET and offset_cursor in committed_offsets:
                payload = offset_cursor + FRAME_HEADER_SIZE
                key_len = struct.unpack_from("<H", raw, payload + 40)[0]
                generation_offset = payload + 40 + 2 + key_len + 4 + 4 + 4
                if generation_offset + 8 <= offset_cursor + total:
                    old_generation = struct.unpack_from("<Q", raw, generation_offset)[0]
                    target_offset = generation_offset
                    target_batch = struct.unpack_from("<Q", raw, payload + 16)[0]
                    break
            offset_cursor += total
        if target_offset is None or old_generation is None or target_batch is None:
            raise CrashVehicleError(
                "mutation refused: fixture has no committed reference"
            )
        if target_batch not in baseline_fixture["complete_batches"]:
            raise CrashVehicleError("mutation refused: reference is not in a committed batch")
        new_generation = old_generation + 1
        struct.pack_into("<Q", raw, target_offset, new_generation)
        frame_start = offset_cursor
        frame_end = frame_start + total
        crc = _crc32c(bytes(raw[frame_start : frame_start + 22]) + bytes(raw[frame_start + FRAME_HEADER_SIZE : frame_end]))
        struct.pack_into("<I", raw, frame_start + 22, crc)
        segment.write_bytes(raw)
        with segment.open("r+b") as stream:
            os.fdatasync(stream.fileno())
        description = f"replace committed WAL reference generation {old_generation} with mismatched generation {new_generation}"
        offset = target_offset
    else:
        raise CrashVehicleError(f"not a backend mutation case: {case}")
    after = _tree_snapshot(storage)
    return {
        "case": case,
        "target": str(segment),
        "generation": generation,
        "offset": offset,
        "description": description,
        "baseline_sha256": before["tree_sha256"],
        "modified_sha256": after["tree_sha256"],
        "baseline_snapshot": before,
        "modified_snapshot": after,
        "baseline_segment_size": next(
            item["size"] for item in before["files"] if item["path"] == segment.name
        ),
        "modified_segment_size": next(
            item["size"] for item in after["files"] if item["path"] == segment.name
        ),
        "fixture_baseline": baseline_fixture if case in {"committed-corruption", "stale-generation"} else None,
    }


def _action_env(namespace: ArtifactNamespace, *, case: str, storage: Path, evidence: Path, phase: str, mutation: Mapping[str, Any] | None = None) -> dict[str, str]:
    values = {
        "P3_CASE": case,
        "P3_PHASE": phase,
        "P3_STORAGE_PATH": str(storage),
        "P3_EVIDENCE_PATH": str(evidence),
        "P3_RUN_ID": namespace.run_id,
    }
    if mutation is not None:
        values["P3_BASELINE_SEGMENT_SIZE"] = str(mutation["baseline_segment_size"])
        values["P3_MODIFIED_SEGMENT_SIZE"] = str(mutation["modified_segment_size"])
    return values


def _run_command(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    namespace: ArtifactNamespace,
    phase: str,
    cwd: Path | None,
    timeout: float,
) -> dict[str, Any]:
    sanitized = sanitize_argv(command)
    stdout_path = namespace.path / "logs" / f"{phase}.stdout.log"
    stderr_path = namespace.path / "logs" / f"{phase}.stderr.log"
    process: subprocess.Popen[Any] | None = None
    owned: OwnedProcess | None = None
    result: dict[str, Any] = {
        "phase": phase,
        "command": {"argv": sanitized, "args_sha256": args_hash(command)},
        "pid": None,
        "status": "FAIL",
        "exit_code": None,
        "timeout": False,
        "cleanup": None,
        "errors": [],
    }
    child_env = os.environ.copy()
    child_env.update(env)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(
                [str(item) for item in command],
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                env=child_env,
                start_new_session=True,
            )
            owned = OwnedProcess(process, [str(item) for item in command], utc_now(), p3_harness._proc_start_time(process.pid))
            result["pid"] = owned.pid
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timeout"] = True
                result["errors"].append("command timeout")
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if process is not None:
            result["exit_code"] = process.poll()
        result["cleanup"] = cleanup_owned(owned) if owned is not None else {
            "status": "PASS", "attempted": False, "gone": True, "ownership_valid": True, "errors": []
        }
        if result["cleanup"].get("status") != "PASS":
            result["errors"].append("owned command cleanup failed")
    if result["timeout"]:
        result["status"] = "FAIL"
    elif result["exit_code"] == 0:
        result["status"] = "PASS"
    else:
        result["status"] = "FAIL"
    return result


def _read_evidence(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"missing or invalid evidence: {type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, "evidence must be a JSON object"
    return value, None


def _base_result(namespace: ArtifactNamespace, config: CrashVehicleConfig) -> dict[str, Any]:
    command = config.backend_command or config.liveness_command or []
    provenance = collect_provenance(
        repo_root=config.repo_root,
        profile=config.profile,
        argv=command,
        run_id=namespace.run_id,
        started_at=utc_now(),
    )
    provenance["source"] = {"path": str(Path(__file__).resolve()), "sha256": _sha256_file(Path(__file__).resolve())}
    provenance["command"] = _command_identity(command) if command else None
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": namespace.run_id,
        "case": config.case,
        "status": "BLOCKED",
        "reason": {"code": "NOT_COMPLETED"},
        "provenance": provenance,
        "health": {"configured": False, "status": "NOT_APPLICABLE"},
        "command": None,
        "recovery_error": None,
        "failure_class": None,
        "visibility": {"resurrection": "NOT_COMPUTABLE"},
        "mutation": None,
        "baseline_sha256": None,
        "modified_sha256": None,
        "post_recovery_sha256": None,
        "evidence_classification": None,
        "product_acceptance": {"status": "NOT_COMPUTABLE", "reason": "not evaluated"},
        "backend_capability": None,
        "storage_hashes": {},
        "rollback": {"attempted": False, "status": "PENDING", "detail": "deferred"},
        "cleanup": {},
        "manifest_write": {"status": "PENDING", "path": str(namespace.path / "metadata" / "manifest.json")},
    }


def _finish(namespace: ArtifactNamespace, result: dict[str, Any]) -> dict[str, Any]:
    try:
        result["rollback"] = rollback_namespace(namespace)
    except Exception as exc:  # pragma: no cover - defensive evidence path
        result["rollback"] = {"attempted": True, "status": "FAIL", "errors": [f"{type(exc).__name__}: {exc}"]}
    if result["rollback"].get("status") != "PASS":
        result["status"] = "FAIL"
        result["reason"] = {"code": "ROLLBACK_FAILED"}
    result["finished_at"] = utc_now()
    manifest = namespace.path / "metadata" / "manifest.json"
    result["manifest_write"] = {"status": "PASS", "path": str(manifest)}
    try:
        namespace.write_metadata("manifest.json", result)
        persisted = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            persisted.get("status") != result.get("status")
            or persisted.get("manifest_write", {}).get("status") != "PASS"
        ):
            raise CrashVehicleError("returned and persisted manifest status disagree")
    except Exception as exc:  # pragma: no cover - defensive evidence path
        result["status"] = "FAIL"
        result["reason"] = {"code": "MANIFEST_WRITE_FAILED", "detail": f"{type(exc).__name__}: {exc}"}
        result["manifest_write"] = {"status": "FAIL", "path": str(manifest), "error": str(exc)}
        try:
            namespace.write_metadata("manifest.json", result)
        except Exception:
            pass
    return result


def _backend_outcome(
    *,
    command_result: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    evidence_error: str | None,
    contract_pass: bool,
    capability: Mapping[str, Any],
    baseline_evidence: Mapping[str, Any] | None = None,
    authoritative: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Separate fixture/oracle evidence from product acceptance."""

    if evidence_error is not None or evidence is None:
        return "NOT_COMPUTABLE", {"code": "MISSING_EVIDENCE", "detail": evidence_error}, {
            "status": "NOT_COMPUTABLE", "reason": "missing evidence"
        }
    classification = _effective_evidence_classification(evidence, authoritative=authoritative)
    if classification is None:
        return "NOT_COMPUTABLE", {"code": "EVIDENCE_CLASS_REQUIRED"}, {
            "status": "NOT_COMPUTABLE", "reason": "evidence class is absent or invalid"
        }
    if command_result.get("status") != "PASS" or not contract_pass:
        return "FAIL", {"code": "FAIL_CLOSED_CONTRACT_FAILED"}, {
            "status": "FAIL", "reason": "backend command or recovery contract failed"
        }
    if classification != "REAL_BACKEND":
        if not capability.get("available"):
            return "BLOCKED", {
                "code": "REAL_BACKEND_UNAVAILABLE",
                "detail": capability.get("error", "real backend capability unavailable"),
            }, {
                "status": "BLOCKED", "reason": "REAL_BACKEND capability unavailable",
                "classification": classification,
            }
        return "FIXTURE_PASS", {
            "code": "FIXTURE_ORACLE_ONLY",
            "classification": classification,
            "detail": "synthetic or explicit-oracle evidence is not product acceptance",
        }, {
            "status": "BLOCKED",
            "reason": "REAL_BACKEND evidence is required for product acceptance",
            "classification": classification,
        }
    if not capability.get("available"):
        return "BLOCKED", {
            "code": "REAL_BACKEND_UNAVAILABLE",
            "detail": capability.get("error", "real backend capability unavailable"),
        }, {
            "status": "BLOCKED", "reason": capability.get("error", "capability unavailable")
        }
    if _effective_evidence_classification(
        baseline_evidence, authoritative=authoritative
    ) != "REAL_BACKEND":
        return "BLOCKED", {"code": "BASELINE_EVIDENCE_NOT_REAL"}, {
            "status": "BLOCKED", "reason": "REAL_BACKEND baseline evidence is required"
        }
    return "PASS", {"code": "REAL_BACKEND_CONTRACT"}, {"status": "PASS", "reason": "REAL_BACKEND"}


def run_backend_case(config: CrashVehicleConfig) -> dict[str, Any]:
    _validate_case(config.case)
    if config.case not in BACKEND_CASES:
        raise CrashVehicleError(f"backend case required, got {config.case}")
    if config.storage_path is None or config.backend_command is None:
        raise CrashVehicleError("backend cases require storage_path and backend_command")
    _validate_artifact_root(config.artifact_root)
    sanitize_argv(config.backend_command)
    namespace = ArtifactNamespace(config.artifact_root, profile=config.profile)
    namespace.create()
    result = _base_result(namespace, config)
    source = Path(config.storage_path).expanduser().absolute()
    fixture = namespace.path / "storage-copy"
    evidence_path = namespace.path / "metadata" / "backend-evidence.json"
    baseline_evidence_path = namespace.path / "metadata" / "baseline-evidence.json"
    try:
        source_snapshot = _tree_snapshot(source)
        _copy_fixture(source, fixture)
        baseline = _tree_snapshot(fixture)
        if baseline["tree_sha256"] != source_snapshot["tree_sha256"]:
            raise CrashVehicleError("fixture copy hash differs from source baseline")
        if _tree_snapshot(source) != source_snapshot:
            raise CrashVehicleError("caller-owned fixture changed during immutable copy")
        # Validate the immutable mutation preconditions before invoking any
        # backend; this preserves fail-fast fixture rejection without writing.
        _active_wal(fixture)
        if config.case in {"committed-corruption", "stale-generation"}:
            _validate_committed_fixture(fixture)
        authoritative = _is_bound_authoritative_backend(
            config.backend_command, config.repo_root
        )
        capability = _real_backend_capability(config.backend_command, config.repo_root)
        result["backend_capability"] = capability
        with GpuLock():
            baseline_env = _action_env(
                namespace, case=config.case, storage=fixture,
                evidence=baseline_evidence_path, phase="baseline",
            )
            baseline_env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(config.repo_root / "python"), os.environ.get("PYTHONPATH", "")]))
            baseline_command = _run_command(
                config.backend_command, env=baseline_env, namespace=namespace,
                phase="backend-baseline", cwd=config.cwd, timeout=config.timeout,
            )
            baseline_evidence, baseline_error = _read_evidence(baseline_evidence_path)
            result["baseline_evidence"] = baseline_evidence
            baseline_classification = _effective_evidence_classification(
                baseline_evidence, authoritative=authoritative
            )
            baseline_ok = (
                baseline_command.get("status") == "PASS"
                and baseline_command.get("exit_code") == 0
                and baseline_error is None
                and baseline_evidence is not None
                and baseline_evidence.get("status") == "BASELINE_RECOVERED"
                and baseline_classification is not None
            )
            result["baseline_command"] = baseline_command
            if not baseline_ok:
                if baseline_error is not None:
                    reason = {"code": "BASELINE_EVIDENCE_MISSING", "detail": baseline_error}
                elif baseline_command.get("status") != "PASS" or baseline_command.get("exit_code") != 0:
                    reason = {
                        "code": "BASELINE_COMMAND_FAILED",
                        "detail": "baseline command must exit successfully before mutation",
                    }
                elif baseline_classification is None:
                    reason = {"code": "BASELINE_EVIDENCE_CLASS_REQUIRED"}
                else:
                    reason = {"code": "BASELINE_EVIDENCE_INVALID"}
                result["status"] = "NOT_COMPUTABLE"
                result["reason"] = reason
                result["fixture_outcome"] = {
                    "status": "NOT_COMPUTABLE",
                    "reason": reason,
                }
                return _finish(namespace, result)
            mutation = _mutate_fixture(fixture, config.case)
            result["mutation"] = mutation
            result["baseline_sha256"] = mutation["baseline_sha256"]
            result["modified_sha256"] = mutation["modified_sha256"]
            result["storage_hashes"] = {
                "pre_seed": source_snapshot["tree_sha256"],
                "post_seed": mutation["baseline_sha256"],
            }
            backend_env = _action_env(namespace, case=config.case, storage=fixture, evidence=evidence_path, phase="recover", mutation=mutation)
            backend_env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(config.repo_root / "python"), os.environ.get("PYTHONPATH", "")]))
            result["command"] = _run_command(
                config.backend_command,
                env=backend_env,
                namespace=namespace,
                phase="backend-recover",
                cwd=config.cwd,
                timeout=config.timeout,
            )
        evidence, evidence_error = _read_evidence(evidence_path)
        result["evidence"] = evidence
        result["storage_hashes"]["post_recovery"] = _tree_snapshot(fixture)["tree_sha256"]
        result["post_recovery_sha256"] = result["storage_hashes"]["post_recovery"]
        if evidence_error is not None:
            result["status"] = "NOT_COMPUTABLE"
            result["reason"] = {"code": "MISSING_EVIDENCE", "detail": evidence_error}
        elif config.case == "torn-tail":
            repaired = evidence.get("repaired_tail") is True and (
                evidence.get("post_segment_size") == mutation["baseline_segment_size"]
            )
            resurrected = evidence.get("resurrected_incomplete") is True
            result["visibility"] = {"resurrection": "FAIL" if resurrected else "NOT_RESURRECTED"}
            contract_pass = baseline_ok and repaired and not resurrected
            status, reason, acceptance = _backend_outcome(
                command_result=result["command"], evidence=evidence,
                evidence_error=evidence_error, contract_pass=contract_pass,
                capability=capability,
                baseline_evidence=baseline_evidence,
                authoritative=authoritative,
            )
            result["status"], result["reason"], result["product_acceptance"] = status, reason, acceptance
            result["evidence_classification"] = _effective_evidence_classification(
                evidence, authoritative=authoritative
            )
            result["fixture_outcome"] = {"status": "PASS" if contract_pass else "FAIL", "reason": {"code": "TORN_TAIL_REPAIRED_NO_RESURRECTION" if contract_pass else "TORN_TAIL_CONTRACT_FAILED"}}
        else:
            result["recovery_error"] = evidence.get("recovery_error")
            result["failure_class"] = evidence.get("failure_class")
            outcome = evidence.get("visibility")
            result["visibility"] = {"resurrection": outcome if outcome is not None else "NOT_COMPUTABLE"}
            valid_error = evidence.get("status") == "RECOVERY_ERROR" and isinstance(result["recovery_error"], str)
            fail_closed = evidence.get("cold_start") is not True and evidence.get("salvaged") is not True
            invisible = outcome in {"NOT_RESURRECTED", "INVISIBLE", "NO_RESURRECTION"}
            contract_pass = baseline_ok and valid_error and bool(result["failure_class"]) and fail_closed and invisible
            status, reason, acceptance = _backend_outcome(
                command_result=result["command"], evidence=evidence,
                evidence_error=evidence_error, contract_pass=contract_pass,
                capability=capability,
                baseline_evidence=baseline_evidence,
                authoritative=authoritative,
            )
            result["status"], result["reason"], result["product_acceptance"] = status, reason, acceptance
            result["evidence_classification"] = _effective_evidence_classification(
                evidence, authoritative=authoritative
            )
            result["fixture_outcome"] = {"status": "PASS" if contract_pass else "FAIL", "reason": {"code": "FAIL_CLOSED_RECOVERY_ERROR" if contract_pass else "FAIL_CLOSED_CONTRACT_FAILED"}}
    except CrashVehicleError as exc:
        result["status"] = "NOT_COMPUTABLE"
        result["reason"] = {"code": "MUTATION_REFUSED", "detail": str(exc)}
    except Exception as exc:  # preserve structured vehicle failures
        result["status"] = "FAIL"
        result["reason"] = {"code": "VEHICLE_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    return _finish(namespace, result)


def _progress(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"invalid liveness progress: {type(exc).__name__}: {exc}"
    if not isinstance(value, dict) or "progress" not in value or "healthy" not in value:
        return None, "liveness progress requires progress and healthy fields"
    return value, None


def run_liveness_case(config: CrashVehicleConfig) -> dict[str, Any]:
    if config.case != "no-liveness-loss":
        raise CrashVehicleError(f"liveness case required, got {config.case}")
    if config.liveness_command is None:
        raise CrashVehicleError("no-liveness-loss requires liveness_command")
    _validate_artifact_root(config.artifact_root)
    sanitize_argv(config.liveness_command)
    namespace = ArtifactNamespace(config.artifact_root, profile=config.profile)
    namespace.create()
    result = _base_result(namespace, config)
    request_path = namespace.path / "metadata" / "request.json"
    progress_path = namespace.path / "metadata" / "progress.json"
    response_path = namespace.path / "metadata" / "response.json"
    request = {"request_id": namespace.run_id, "created_at": utc_now(), "status": "PENDING"}
    request_path.write_text(json.dumps(request, sort_keys=True), encoding="utf-8")
    started = time.monotonic()
    last_progress: Any = object()
    last_progress_at = started
    command_result: dict[str, Any]
    reason: dict[str, Any] | None = None
    with GpuLock():
        child_env = _action_env(namespace, case=config.case, storage=namespace.path, evidence=response_path, phase="liveness")
        child_env.update({"P3_REQUEST_PATH": str(request_path), "P3_PROGRESS_PATH": str(progress_path), "P3_RESPONSE_PATH": str(response_path)})
        # The command is launched once, and only this exact PID is ever acted on.
        command_result = _run_command_live(
            config.liveness_command,
            env=child_env,
            namespace=namespace,
            cwd=config.cwd,
            timeout=config.timeout,
            poll_interval=config.poll_interval,
            zero_progress_timeout=config.zero_progress_timeout,
            progress_path=progress_path,
            response_path=response_path,
            request_id=namespace.run_id,
        )
    result["command"] = command_result
    result["evidence"] = command_result.get("evidence")
    result["cleanup"] = {"liveness": command_result.get("cleanup")}
    result["visibility"] = {"resurrection": "NOT_APPLICABLE", "request": command_result.get("request_outcome")}
    result["reason"] = command_result.get("reason") or {"code": "LIVENESS_ORACLE"}
    result["status"] = command_result.get("status", "NOT_COMPUTABLE")
    return _finish(namespace, result)


def _run_command_live(
    command: Sequence[str], *, env: Mapping[str, str], namespace: ArtifactNamespace,
    cwd: Path | None, timeout: float, poll_interval: float, zero_progress_timeout: float,
    progress_path: Path, response_path: Path, request_id: str,
) -> dict[str, Any]:
    stdout_path = namespace.path / "logs" / "liveness.stdout.log"
    stderr_path = namespace.path / "logs" / "liveness.stderr.log"
    child_env = os.environ.copy()
    child_env.update(env)
    started = time.monotonic()
    owned: OwnedProcess | None = None
    process: subprocess.Popen[Any] | None = None
    result: dict[str, Any] = {"phase": "liveness", "command": _command_identity(command), "pid": None, "status": "NOT_COMPUTABLE", "errors": []}
    last_progress: Any = object()
    last_progress_at = started
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen([str(item) for item in command], stdout=stdout, stderr=stderr, cwd=cwd, env=child_env, start_new_session=True)
            owned = OwnedProcess(process, [str(item) for item in command], utc_now(), p3_harness._proc_start_time(process.pid))
            result["pid"] = owned.pid
            while process.poll() is None:
                now = time.monotonic()
                if now - started >= timeout:
                    result.update(status="FAIL", reason={"code": "TIMEOUT"}, request_outcome="TIMEOUT")
                    break
                value, error = _progress(progress_path)
                if error is not None:
                    if now - started < min(0.1, timeout / 2):
                        time.sleep(max(0.0, poll_interval))
                        continue
                    result.update(status="NOT_COMPUTABLE", reason={"code": "PROGRESS_UNAVAILABLE", "detail": error}, request_outcome="NOT_COMPUTABLE")
                    break
                if not value["healthy"]:
                    result.update(status="FAIL", reason={"code": "HEALTH_LOSS"}, request_outcome="HEALTH_LOSS")
                    break
                progress = value["progress"]
                if progress != last_progress:
                    last_progress = progress
                    last_progress_at = now
                elif now - last_progress_at >= zero_progress_timeout:
                    result.update(status="FAIL", reason={"code": "ZERO_PROGRESS"}, request_outcome="ZERO_PROGRESS")
                    break
                try:
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError):
                    response = None
                if isinstance(response, dict) and response.get("request_id") == request_id and response.get("status") == "COMPLETE":
                    result.update(status="PASS", reason={"code": "REQUEST_COMPLETED"}, request_outcome="COMPLETED", evidence=response)
                    break
                time.sleep(max(0.0, poll_interval))
            if process.poll() is not None and result["status"] == "NOT_COMPUTABLE":
                result.update(reason={"code": "CHILD_EXIT_WITHOUT_RESPONSE"}, request_outcome="NOT_COMPUTABLE")
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["reason"] = {"code": "ACTION_FAILED"}
    finally:
        result["exit_code"] = None if process is None else process.poll()
        result["cleanup"] = cleanup_owned(owned) if owned is not None else {"status": "PASS", "gone": True, "ownership_valid": True, "errors": []}
        if result["cleanup"].get("status") != "PASS":
            result["status"] = "FAIL"
            result["reason"] = {"code": "CLEANUP_FAILED"}
    return result


def run_restart_case(config: CrashVehicleConfig) -> dict[str, Any]:
    if config.case != "process-crash" or config.restart_config is None:
        raise CrashVehicleError("process-crash requires restart_config")
    from p3_restart_vehicle import run_restart

    _validate_artifact_root(config.artifact_root)
    storage_namespace = ArtifactNamespace(config.artifact_root, profile=f"{config.profile}-storage")
    storage_namespace.create()
    requested_storage = Path(config.restart_config.storage_path).expanduser().absolute()
    storage = storage_namespace.path / "storage"
    if requested_storage.exists():
        _copy_fixture(requested_storage, storage)
        pre_seed = _tree_snapshot(storage)
    else:
        storage.mkdir()
        pre_seed = _tree_snapshot(storage)
    restart_config = dataclasses.replace(config.restart_config, storage_path=storage)
    restart_result = run_restart(restart_config)
    snapshot = _tree_snapshot(storage) if storage.is_dir() else None
    restart_result.update({
        "schema_version": SCHEMA_VERSION,
        "case": "process-crash",
        "baseline_sha256": restart_result.get("seed", {}).get("storage", {}).get("tree_sha256"),
        "modified_sha256": snapshot["tree_sha256"] if snapshot else None,
        "post_recovery_sha256": restart_result.get("restore", {}).get("storage", {}).get("tree_sha256"),
        "mutation": {"case": "process-crash", "description": "exact owned-child SIGKILL; no storage mutation"},
        "recovery_error": None,
        "failure_class": None,
        "visibility": {"resurrection": "NOT_APPLICABLE", "identity_byte_equivalence": restart_result.get("reason", {}).get("code") == "IDENTITY_BYTE_EQUIVALENT"},
        "storage_hashes": {
            "pre_seed": pre_seed["tree_sha256"],
            "post_seed": restart_result.get("seed", {}).get("storage", {}).get("tree_sha256"),
            "post_recovery": restart_result.get("restore", {}).get("storage", {}).get("tree_sha256"),
        },
    })
    manifest_path = Path(restart_result["manifest_write"]["path"])
    p3_harness.atomic_json(manifest_path, restart_result)
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    if persisted.get("status") != restart_result.get("status"):
        restart_result["status"] = "FAIL"
        restart_result["reason"] = {"code": "MANIFEST_WRITE_FAILED", "detail": "returned and persisted manifest status disagree"}
        p3_harness.atomic_json(manifest_path, restart_result)
    return restart_result


def run_case(config: CrashVehicleConfig) -> dict[str, Any]:
    _validate_case(config.case)
    if config.case in BACKEND_CASES:
        return run_backend_case(config)
    if config.case == "no-liveness-loss":
        return run_liveness_case(config)
    return run_restart_case(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(ALL_CASES), required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--profile", default="p3-crash")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--storage-path", type=Path)
    parser.add_argument("--backend-command", nargs="+")
    parser.add_argument("--liveness-command", nargs="+")
    parser.add_argument("--restart-config", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--zero-progress-timeout", type=float, default=1.0)
    return parser


def _restart_config(path: Path, args: argparse.Namespace) -> Any:
    from p3_restart_vehicle import RestartVehicleConfig

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CrashVehicleError("restart config must be a JSON object")
    value.update({"artifact_root": args.artifact_root, "repo_root": args.repo_root, "cwd": args.cwd})
    return RestartVehicleConfig(**value)


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    restart = _restart_config(args.restart_config, args) if args.restart_config else None
    result = run_case(CrashVehicleConfig(
        case=args.case, storage_path=args.storage_path, backend_command=args.backend_command,
        liveness_command=args.liveness_command, restart_config=restart,
        artifact_root=args.artifact_root, profile=args.profile, repo_root=args.repo_root,
        cwd=args.cwd, timeout=args.timeout, poll_interval=args.poll_interval,
        zero_progress_timeout=args.zero_progress_timeout,
    ))
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
