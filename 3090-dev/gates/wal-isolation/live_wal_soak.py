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
    segment_path,
)


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "live-storage"
EVIDENCE = ROOT / "live-evidence"
EVENTS = EVIDENCE / "live_wal_soak.jsonl"


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
        model_name="live-wal-soak",
        extra_config={
            "storage_dir": str(STORAGE),
            "extent_size": "16Ki",
            "file_size": "128Ki",
            "wal_checkpoint_bytes": "512",
        },
    )


def storage_snapshot(backend):
    names = []
    for path in sorted(STORAGE.iterdir()):
        if path.is_file():
            names.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                }
            )
    manifest = manifest_path(str(STORAGE), backend.config_suffix)
    current = current_path(str(STORAGE), backend.config_suffix)
    state = read_manifest(manifest) if os.path.exists(manifest) else None
    current_generation = read_current(current) if os.path.exists(current) else None
    usage = shutil.disk_usage(STORAGE)
    return {
        "files": names,
        "wal_segments": [
            item for item in names if ".wal." in item["name"]
        ],
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
    record = {
        "ts_wall_ns": time.time_ns(),
        "ts_mono_ns": time.monotonic_ns(),
        "kind": kind,
        "stats": backend.stats_snapshot(),
        "wal_generation": backend._wal_generation,
        "wal_offset": backend._wal_offset,
        "wal_active_bytes_calculated": max(
            0, backend._wal_offset - SEGMENT_HEADER_SIZE
        ),
        **fields,
    }
    record["storage"] = storage_snapshot(backend)
    with EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True), flush=True)
    return record


def wait_for_success(backend, target, label, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stats = backend.stats_snapshot()
        if stats["wal_checkpoint_successes"] >= target:
            emit(backend, "checkpoint-success-observed", label=label, target=target)
            return
        time.sleep(0.01)
    emit(backend, "checkpoint-timeout", label=label, target=target)
    raise AssertionError(
        f"checkpoint target {target} not reached for {label}: {backend.stats_snapshot()}"
    )


def wait_for_decline(backend, successes, label, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stats = backend.stats_snapshot()
        if (
            stats["wal_checkpoint_requested"] >= 1
            and stats["wal_checkpoint_successes"] == successes
        ):
            emit(backend, "checkpoint-decline-observed", label=label)
            return
        time.sleep(0.01)
    emit(backend, "checkpoint-decline-timeout", label=label)
    raise AssertionError(
        f"checkpoint decline not observed for {label}: {backend.stats_snapshot()}"
    )


def assert_exact(backend, values):
    for key, expected in values.items():
        target = bytearray(len(expected))
        result = backend.get(key, target)
        if result is None or bytes(target) != expected:
            raise AssertionError(f"reopen/value mismatch for {key}")


def main():
    if STORAGE.exists():
        shutil.rmtree(STORAGE)
    STORAGE.mkdir(parents=True)
    if EVENTS.exists():
        EVENTS.unlink()

    backend = ExtentFileBackend(config())
    values = {}
    try:
        emit(backend, "open", threshold=512, storage=str(STORAGE))
        successful_before = 0
        for cycle in range(4):
            for member in range(4):
                key = f"auto-{cycle}-{member}"
                value = bytes([31 + cycle * 4 + member]) * 2048
                started = time.monotonic_ns()
                if not backend.set(key, bytearray(value)):
                    raise AssertionError(f"write failed for {key}")
                latency_ns = time.monotonic_ns() - started
                values[key] = value
                emit(backend, "write", cycle=cycle, key=key, bytes=len(value), latency_ns=latency_ns)
            target = successful_before + 1
            wait_for_success(backend, target, f"automatic-cycle-{cycle}")
            stats = backend.stats_snapshot()
            if stats["wal_active_bytes"] > 512:
                raise AssertionError(f"WAL did not reset below threshold: {stats}")
            emit(
                backend,
                "cycle-verified",
                cycle=cycle,
                old_generation=backend._wal_generation - 1,
                new_generation=backend._wal_generation,
            )
            successful_before = target

        # A staged group is deliberately left incomplete.  The automatic worker
        # must decline it (no publication), then abort and permit the next
        # checkpoint to publish the remaining complete state.
        group_id = backend.open_group()
        incomplete_keys = [f"incomplete-aborted-{member}" for member in range(4)]
        incomplete_values = [b"incomplete" * 200 for _ in incomplete_keys]
        for key, value in zip(incomplete_keys, incomplete_values):
            staged = backend._write_pages(
                [backend._storage_key(key)],
                [bytearray(value)],
                group_id=group_id,
            )
            if not staged or backend.exists(key):
                raise AssertionError("incomplete group was visible before commit")
        emit(backend, "incomplete-group-staged", group_id=[group_id[0].hex(), group_id[1]], keys=incomplete_keys)
        wait_for_decline(backend, successful_before, "incomplete-group-decline", timeout=2.0)
        if not backend.abort_group(group_id):
            raise AssertionError("incomplete group abort failed")
        emit(backend, "incomplete-group-aborted", group_id=[group_id[0].hex(), group_id[1]])
        wait_for_success(backend, successful_before + 1, "post-abort-checkpoint")
        successful_before += 1
        if any(backend.exists(key) for key in incomplete_keys):
            raise AssertionError("aborted group became visible")

        assert_exact(backend, values)
        emit(backend, "pre-close-integrity-verified", value_count=len(values))
        backend.close()
        backend = None

        reopened = ExtentFileBackend(config())
        try:
            assert_exact(reopened, values)
            if any(reopened.exists(key) for key in incomplete_keys):
                raise AssertionError("aborted group recovered as visible")
            emit(reopened, "reopen-integrity-verified", value_count=len(values))
            final_stats = reopened.stats_snapshot()
            final_storage = storage_snapshot(reopened)
            summary = {
                "result": "PASS",
                "automatic_successes_before_group": 4,
                "successful_checkpoints_total": final_stats["wal_checkpoint_successes"],
                "reopen_values": len(values),
                "final_stats": final_stats,
                "final_storage": final_storage,
                "remaining_crash_windows": [
                    "This live test does not exercise process loss between data pwrite and WAL sync, between manifest publication and current-pointer publication, or torn WAL tails.",
                ],
            }
            (EVIDENCE / "live_wal_soak_summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
        finally:
            reopened.close()
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    main()
