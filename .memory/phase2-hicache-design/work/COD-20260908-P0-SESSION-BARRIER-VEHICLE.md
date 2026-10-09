ENTRY: ACCEPT

Task ID: COD-20260908-P0-SESSION-BARRIER-VEHICLE  
Epoch: E20260908-P0P1P2  
Role: coder  
Status: done

## Summary

Implemented the isolated P0 S=25 vehicle at:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`

No engine, server, remote process, or live endpoint was started.  The vehicle is ready for a future V3-backed run; this task does not claim a P0 PASS.

## Changed files

- Added only `3090-dev/p0_session_barrier_vehicle.py` in the authorized source repository.
- Added this report at the exact requested memory path.
- Did not edit `gate3_parked.py`, `rh_durability_driver.py`, product Python files, ledger, plan, or context.  Pre-existing worktree modifications remain untouched.

## Implemented behavior

- Frozen configuration is enforced: `S=25`, approximately `55K` history, `active=8`, `build_workers=8`, and RH off.
- Reuses `gate3_parked.build_history_prompt` and its corpus semantics through the existing script import; live mode loads the explicitly supplied tokenizer/model path.
- Uses an explicit OpenAI-compatible `POST /v1/chat/completions` endpoint.  Every build and warm payload carries a deterministic `p0-s25-sNNNNN` top-level `session_id`; no timestamp-derived identity is used.
- Build `build_rid` and warm `warm_rid` are accepted only from response `id`.  Missing response IDs prevent that session from proceeding.
- Tails the configured `p0_durable.v3` JSONL file with per-session state.  Scoped events require top-level `session_id`, `build_rid`, `node_id`, and `final_kv_hash`; malformed or mismatched joins are rejected.
- Uses event arrival order for causality.  Wall timestamps are retained as evidence only.  A warm request is issued only after the same tuple has observed ordered build identity, explicit KV durable evidence, explicit Mamba durable evidence, `durability_barrier(combined_durable=true)`, and `residency_barrier(cold_residency=true)`.
- Missing barriers, malformed joins, watchdog expiry, missing restore events, or wrong ordering prevent warm issuance and produce `NOT_VERIFIED`; observed HTTP/restore failures produce `FAIL`.  `PASS` is only reachable when every planned full session satisfies the exact join, ordered barriers, successful restore, and response checks.
- Live evidence includes resolved config, trace copy, build/warm metrics, barrier wait outcomes, reducer result, manifest/verdict, and `MD5SUMS`.
- `--dry-run` is parser/reducer-only and always reports `NOT_VERIFIED` with `execution_started=false`.

## Verification evidence

- `python3 -m py_compile 3090-dev/p0_session_barrier_vehicle.py` — passed.
- `python3 3090-dev/p0_session_barrier_vehicle.py --help` — passed and exposed explicit `--events`, `--endpoint`, `--model`, and `--model-path` requirements for live mode.
- `python3 3090-dev/p0_session_barrier_vehicle.py --dry-run --evidence-dir /tmp/p0-session-barrier-YnZrCJ/evidence-v2` — completed with `verdict=NOT_VERIFIED`, `execution_started=false`, 25 eligible fixture rows, 25 exact identities, 25 ordered barrier rows, and 25 restore-success fixture rows.  The generated bundle contained `config-resolved.json`, `trace-copy.jsonl`, `build-warm.jsonl`, `barrier-waits.jsonl`, `reducer-result.json`, `verdict.json`, `vehicle.log`, and `MD5SUMS`.
- Direct reducer check — passed: a barrier before KV/Mamba evidence was not warm-ready, a premature warm was marked invalid, and a session event missing `final_kv_hash` was rejected.
- Live invocation without `--events` — rejected with exit 1: `live mode requires explicit --events`.
- No fixed `sleep` call exists in the vehicle; condition waits are watchdog/polling only and cannot produce success.
- No remote execution was performed.

## Residual product dependency and uncertainty

The current read-only scout evidence confirms that the request path already stores `session_id`, but the active product trace does not yet provide the required V3 propagation and barrier events. Product V3 must therefore emit the exact top-level tuple on every scoped event, explicit `kv_durable=true` and `mamba_durable=true` evidence, and the two keyed barriers. The live vehicle deliberately does not infer these from timestamps, `storage_persisted` alone, or client labels. If the deployed request path does not accept/preserve the top-level `session_id`, or if response `id` does not match V3 `build_rid`, the vehicle remains `NOT_VERIFIED` and does not issue the warm request for that session.

## Followups

- Product owner: land and validate the authorized V3 trace-context/barrier propagation before live use.
- Tester/reviewer: execute and independently assess the focused S=25 RH-off run under a fresh Task ID; this vehicle does not authorize that execution or gate decision.

## Open issues

- V3 event names/fields must conform to the strict contract encoded by this vehicle; no compatibility inference is intentionally provided.
- The dry-run uses deterministic fixture identities solely to test parsing/reduction and is not runtime evidence.
