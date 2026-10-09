# DEVOPS-20260908-P0-S25-LIVE-R4-EXACT

status: done (terminal evidence collected; acceptance verdict NOT_VERIFIED)
task_id: DEVOPS-20260908-P0-S25-LIVE-R4-EXACT
host: 175.155.64.171:24052
checkout: /root/sglang-b1-continuity

## Run

- run id: `p0-s25-v43-fix1-live-20260907T225519Z`
- endpoint: `http://127.0.0.1:8024`
- settings: TP1, FP8, Graph8, max-running 8, mamba ratio 0.42, hicache ratio 1.3, max-total 600000, wait_complete, 120G storage, RH off
- launcher radix-cache flag count: exactly 1
- readiness evidence: health succeeded and launcher-ready marker recorded at `2026-09-07T22:57:35Z`
- exact vehicle shape was used: sessions 25, active 8, build-workers 8, history-target 55000, RH off

## Pre-R4 preservation

Snapshot paths:

- `/root/evidence-gate3-parked/p0-s25-v43-live-r3/raw/t38c-probe.log.pre-r4` — 842782347 bytes, SHA-256 `b124bf952000f22e0712c857278a1474832026b65fcf41a52cb42c0df97a7d28`
- `/root/evidence-gate3-parked/p0-s25-v43-live-r3/raw/t38c-durable-trace.pre-r4` — 0 bytes, SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

## Terminal result

Vehicle terminal exit code: 1. `vehicle/verdict.json` reports:

- verdict: `NOT_VERIFIED`
- planned sessions: 25; eligible full sessions: 0; restore success: 0
- branches: A omitted transfer 0, B write failure 0, C key mismatch 0, D recycle/remove 0, E late write/barrier 0, F unresolved 17
- barrier waits: 0; fail-closed: true; missing-event-join: true; no-fixed-sleep-success: true
- errors: 8 `IncompleteRead` failures (2988 bytes read) and 17 build responses missing `response.id`

V3 trace counts in `vehicle/trace-copy.jsonl`: 405 events, including 192 `residency_free_complete`, 184 `residency_detach`, 3 `extent_commit`, 2 `storage_persisted`, and 0 barrier events. Eight sessions emitted trace events; no session established the required exact identity join `(session_id, build_rid, node_id, final_kv_hash)`. Reducer result records identity/schema errors and all 25 sessions unresolved or incomplete; no branch/TTFT/restore metric was eligible for acceptance.

Engine log also records a scheduler exception ending in `AttributeError: 'int' object has no attribute 'get_last_hash_value'`. Other logged torchcodec/libavutil load warnings and late Triton kernel-load warnings are preserved in `engine.log`.

## Changed resources and preserved evidence

Fresh run root (preserved): `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r4`

- `engine.log`, `engine.pid`, `ready-marker`, `run-id`, `event-path`, `durable-trace-path`
- `vehicle/stdout` and `vehicle/stderr` (captured as `vehicle.stdout` and `vehicle.stderr`), `vehicle/verdict.json`, `vehicle/reducer-result.json`, `vehicle/config-resolved.json`, `vehicle/build-warm.jsonl`, `vehicle/trace-copy.jsonl`, `vehicle/barrier-waits.jsonl`, `vehicle/vehicle.log`, `vehicle/MD5SUMS`
- `storage/hicache.data_qwen3.5-9b-gptq_0_1` (120000000000 bytes)
- `/tmp/t38c-probe.log` was truncated only after the R3 snapshot; `/tmp/t38c-durable-trace` was ensured to exist.

## Verification evidence

- Preflight found no matching engine/vehicle/gate3 processes.
- Post-stop process capture is empty, and a subsequent process check found no matching `p0_session_barrier_vehicle`, `sglang.launch_server`, or launcher process.
- Engine PID `1003883` was stopped after vehicle terminal exit; no replacement was launched.
- Old R1/R2/R3 evidence/storage was not deleted or modified beyond creating the authorized R3 `raw` snapshot directory and snapshot files.

## Open issues / followups

- This run does not satisfy the requested P0 acceptance because the terminal verdict is `NOT_VERIFIED`, with zero restore/eligible sessions and no accepted TTFT/branch metrics.
- The preserved engine and vehicle logs contain the runtime failures and should be handled by a separately authorized diagnostic or rerun task. No diagnosis, code change, or replacement run was performed here.
