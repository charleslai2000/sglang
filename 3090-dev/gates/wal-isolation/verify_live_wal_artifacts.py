import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
records = [json.loads(line) for line in (ROOT / "live-evidence/live_wal_soak.jsonl").read_text().splitlines()]
successes = [r for r in records if r["kind"] == "checkpoint-success-observed"]
automatic = [r for r in successes if r["label"].startswith("automatic-cycle-")]
cycles = [r for r in records if r["kind"] == "cycle-verified"]
declines = [r for r in records if r["kind"] == "checkpoint-decline-observed"]
reopen = [r for r in records if r["kind"] == "reopen-integrity-verified"]

assert len(automatic) >= 3, len(automatic)
assert len(cycles) == 4, len(cycles)
assert [r["new_generation"] for r in cycles] == [1, 2, 3, 4]
assert all(r["stats"]["wal_active_bytes"] == 0 for r in successes)
assert all(
    r["storage"]["wal_segments"]
    == [
        {
            "name": next(
                item["name"]
                for item in r["storage"]["wal_segments"]
                if item["name"].endswith(f".wal.{r['new_generation']}")
            ),
            "size": 28,
        },
        {"name": next(item["name"] for item in r["storage"]["wal_segments"] if item["name"].endswith(".wal.current")), "size": 2},
    ]
    for r in cycles
)
assert len(declines) == 1
assert declines[0]["stats"]["wal_checkpoint_successes"] == 4
assert len(reopen) == 1 and reopen[0]["value_count"] == 16
assert all(r["stats"]["wal_checkpoint_failures"] == 0 for r in records)

write_records = [r for r in records if r["kind"] == "write"]
latencies = [r["latency_ns"] for r in write_records]
result = {
    "result": "PASS",
    "automatic_checkpoint_count": len(automatic),
    "automatic_generations": [r["new_generation"] for r in cycles],
    "active_bytes_after_each_checkpoint": [r["stats"]["wal_active_bytes"] for r in successes],
    "declined_incomplete_group": True,
    "reopen_value_count": reopen[0]["value_count"],
    "checkpoint_failures": max(r["stats"]["wal_checkpoint_failures"] for r in records),
    "write_latency_ns_min": min(latencies),
    "write_latency_ns_max": max(latencies),
    "write_latency_ns_count": len(latencies),
    "filesystem_free_bytes_at_last_event": records[-1]["storage"]["filesystem"]["free"],
}
(ROOT / "live-evidence/live_wal_artifact_verification.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(result, indent=2, sort_keys=True))
