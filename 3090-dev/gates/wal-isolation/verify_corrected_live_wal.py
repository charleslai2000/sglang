import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from sglang.srt.mem_cache.storage.extent.extent_metadata import (
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
OUTPUT = EVIDENCE / "corrected_live_wal_verification.json"
HASHES = EVIDENCE / "corrected_live_wal_hashes.json"
CONFIG_SUFFIX = "_live-wal-corrected_0_1"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot():
    files = [
        {"name": path.name, "size": path.stat().st_size}
        for path in sorted(STORAGE.iterdir())
        if path.is_file()
    ]
    manifest = manifest_path(str(STORAGE), CONFIG_SUFFIX)
    current = current_path(str(STORAGE), CONFIG_SUFFIX)
    state = read_manifest(manifest)
    usage = shutil.disk_usage(STORAGE)
    return {
        "files": files,
        "wal_segments": [item for item in files if ".wal." in item["name"]],
        "manifest_generation": state.wal_active_gen,
        "manifest_floor": state.wal_floor,
        "manifest_checkpoint_lsn": state.checkpoint_lsn,
        "manifest_entry_count": len(state.entries),
        "current_generation": read_current(current),
        "filesystem": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        },
    }


def main():
    records = [json.loads(line) for line in EVENTS.read_text().splitlines()]
    summary = json.loads(SUMMARY.read_text())
    provenance = json.loads(PROVENANCE.read_text())
    final_storage = snapshot()

    successes = [r for r in records if r["kind"] == "checkpoint-success-observed"]
    automatic = [
        r for r in successes if r["label"].startswith("automatic-cycle-")
    ]
    post_abort = [r for r in successes if r["label"] == "post-abort-checkpoint"]
    declines = [r for r in records if r["kind"] == "checkpoint-decline-observed"]
    cycles = [r for r in records if r["kind"] == "cycle-verified"]
    original = [
        r for r in records if r["kind"] == "original-pre-close-integrity-verified"
    ]
    reopened = [r for r in records if r["kind"] == "reopen-integrity-verified"]

    assert len(automatic) >= 3, len(automatic)
    assert len(cycles) == 4, len(cycles)
    assert [r["new_generation"] for r in cycles] == [1, 2, 3, 4]
    assert len(post_abort) == 1
    assert len(declines) == 1
    assert len(original) == 1
    assert len(reopened) == 1
    assert reopened[0]["exact_values"] is True
    assert reopened[0]["value_count"] == 16
    assert original[0]["authoritative_checkpoint_count"] == 5
    assert summary["authoritative_original_pre_close_checkpoint_count"] == 5
    assert summary["automatic_successes_before_group"] == 4
    assert summary["post_abort_checkpoint_success"] is True
    assert summary["reopen_values"] == 16
    for field in (
        "files",
        "wal_segments",
        "manifest_generation",
        "manifest_floor",
        "manifest_checkpoint_lsn",
        "manifest_entry_count",
        "current_generation",
    ):
        assert final_storage[field] == summary["final_storage"][field], field
    assert final_storage["current_generation"] == final_storage["manifest_generation"] + 1
    assert final_storage["manifest_floor"] == final_storage["current_generation"]
    assert final_storage["manifest_entry_count"] == 16
    assert final_storage["wal_segments"] == [
        {
            "name": f"hicache.meta{CONFIG_SUFFIX}.wal.{final_storage['current_generation']}",
            "size": 28,
        },
        {
            "name": f"hicache.meta{CONFIG_SUFFIX}.wal.current",
            "size": 2,
        },
    ]
    assert all(r["stats"]["wal_active_bytes"] == 0 for r in successes)
    assert all(r["stats"]["wal_checkpoint_failures"] == 0 for r in records)
    assert all(r["stats"]["wal_checkpoint_retries"] == 0 for r in records)
    assert all(r["stats"]["wal_active_bytes"] <= 512 for r in cycles)
    assert provenance["interpreter"] == sys.executable
    assert provenance["effective_pythonpath"] == os.environ.get("PYTHONPATH", "")
    assert provenance["command_line"][0] == provenance["interpreter"]
    assert provenance["command_line"][1].endswith("corrected_live_wal_soak.py")
    assert summary["source_binding"] == provenance["source_binding"]

    result = {
        "result": "PASS",
        "records": len(records),
        "automatic_checkpoint_count": len(automatic),
        "automatic_generations": [r["new_generation"] for r in cycles],
        "post_abort_generation": post_abort[0]["wal_generation"],
        "declined_incomplete_group": True,
        "authoritative_original_pre_close_checkpoint_count": original[0][
            "authoritative_checkpoint_count"
        ],
        "reopen_value_count": reopened[0]["value_count"],
        "final_storage_matches_summary": True,
        "final_generation_pointer_consistent": True,
        "wal_active_bytes_after_successes": [
            r["stats"]["wal_active_bytes"] for r in successes
        ],
        "checkpoint_failures": max(
            r["stats"]["wal_checkpoint_failures"] for r in records
        ),
        "checkpoint_retries": max(
            r["stats"]["wal_checkpoint_retries"] for r in records
        ),
        "crash_evidence_claimed": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    artifacts = [EVENTS, SUMMARY, PROVENANCE, OUTPUT]
    hashes = {
        str(path.relative_to(EVIDENCE)): {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in artifacts
    }
    HASHES.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
