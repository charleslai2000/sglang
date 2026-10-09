ENTRY: ACCEPT

# SCOUT-20260908-P0-R3-EVENT-GAP

- Task ID: `SCOUT-20260908-P0-R3-EVENT-GAP`
- Orchestration epoch: `2026-09-08`
- Role: `scout`
- Invocation status: `done`
- Scope: read-only inspection of the local vehicle, local trace helper, and relevant local reports/tests. No remote access and no file changes outside this report.

## Artifacts inspected

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/trace_context.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
- `.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-S25-LIVE-R3.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-SESSION-BARRIER-VEHICLE.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-DURABILITY-TRACE-V2.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V3.md`

## Observed facts

1. The vehicle hard-codes `SCHEMA = "p0_durable.v3"` and the complete required identity tuple `(session_id, build_rid, node_id, final_kv_hash)` at `p0_session_barrier_vehicle.py:32-33`.

2. Every tailed JSONL record is rejected before session state is updated when `schema_version` is not exactly V3 (`p0_session_barrier_vehicle.py:210-231`, especially `217-219`). A record with the right event name but V2 schema therefore cannot satisfy any vehicle predicate.

3. Even a V3 record is not joinable unless all four identity fields are non-empty strings (`p0_session_barrier_vehicle.py:233-239`). The reducer also rejects a `build_rid` mismatch for a session (`:241-245`).

4. Warm issuance waits for the same session to have: build identity, KV durable evidence, Mamba durable evidence, `durability_barrier(combined_durable=true)`, and `residency_barrier(cold_residency=true)` (`p0_session_barrier_vehicle.py:343-354`). The two explicit durable evidence event families are `kv_durable`/`storage_persisted` with `kv_durable is True` and `mamba_durable`/`mamba_persisted` with `mamba_durable is True` (`:56-59`, `:107-118`).

5. The durability barrier is accepted only after ordered exact evidence: build, KV evidence, and Mamba evidence must precede `durability_barrier(combined_durable=true)` (`p0_session_barrier_vehicle.py:262-275`). Residency is accepted only after that durability barrier and `cold_residency=true` (`:276-281`).

6. The live vehicle does not issue the warm request until `tailer.wait_for(lambda: reducer.ready_for_warm(...))` returns true (`p0_session_barrier_vehicle.py:831-843`). The event tailer only reads the configured `--events` JSONL path and feeds each object to the reducer (`:421-440`, `:786-795`).

7. The R3 execution report records vehicle PID `999350`, 405 lines in `/tmp/t38c-probe.log`, zero lines in `/tmp/t38c-durable-trace`, no vehicle result files, and no verdict while the vehicle remained active (`DEVOPS-20260908-P0-S25-LIVE-R3.md:41-51`). This is the available local report evidence; the remote files themselves were not accessed in this invocation.

8. The relevant V2 design report defines the durable event envelope as `schema_version=p0_durable.v2` with common process/operation fields and optional correlation fields (`COD-20260908-P0-DURABILITY-TRACE-V2.md:21-35`). The earlier live-vehicle report states that V2 records did not consistently carry `session_id` and `build_rid`, and that no keyed `durability_barrier(combined_durable=true)` was exposed (`COD-20260908-P0-LIVE-VEHICLE.md:12-27`).

9. `trace_context.py` defines `TRACE_SCHEMA = "p0_durable.v3"` and enables context only when the marker path exists (`trace_context.py:10-11`, `:28-30`). `make_trace_context` additionally requires `session_id`, scheduler-owned `session_generation`, and `build_rid`, returning `None` otherwise (`:59-81`). `attach_trace_context` copies context to top-level fields and sets V3 schema; it does not write a file or emit a barrier (`:84-91`).

10. The V3 context includes `session_id`, `session_generation`, `build_rid`, and optional `warm_rid`; the vehicle’s join additionally requires top-level `node_id` and `final_kv_hash`. This distinction is explicit in `trace_context.py:75-81` versus `p0_session_barrier_vehicle.py:32-33`.

11. The focused V4.3 test exercises marker-off context absence, marker-on context creation, missing generation rejection, and exact slot-token lifecycle behavior (`test_p0_trace_context_v4.py:52-75`, `:113-168`). It does not validate a live V2-to-V3 compatibility path.

## Causal hypothesis

Primary hypothesis (inference): R3 is waiting indefinitely because the configured event source is producing the older V2/probe-shaped stream (including residency observations), while the vehicle accepts only `p0_durable.v3` records with the full session/build/node/hash identity and ordered KV+Mamba evidence. The reducer drops non-V3 records at `p0_session_barrier_vehicle.py:217-219`; consequently `ready_for_warm` remains false and the vehicle never reaches the warm request or verdict path.

The zero-line `/tmp/t38c-durable-trace` observation is consistent with the same gap, but it does not by itself distinguish “V3 emitter inactive/not deployed” from “the 405-line file is a V2/probe stream.” `trace_context.py` is only a marker-gated context helper, so an existing marker file alone cannot prove that V3 barrier events were emitted.

## Proposed next diagnostic

Under a fresh diagnostic Task ID and without changing the vehicle contract:

1. Obtain a local copy of the exact R3 event file or a sanitized first-line sample, then compute a read-only histogram of `schema_version`, `evt`, and presence of `session_id`, `build_rid`, `node_id`, and `final_kv_hash`. This directly distinguishes V2 residency records from V3 records and identifies the first rejected shape.
2. Independently verify the deployed trace-helper/product hashes and marker existence before a one-session smoke run; marker contents are irrelevant to `durable_trace_enabled()` because it tests path existence only.
3. For one session, confirm whether any V3 `build_complete`, `kv_durable`, `mamba_durable`, `durability_barrier`, and `residency_barrier` records appear with one stable identity tuple. Do not infer V3 from event names or timestamps, and do not treat V2 residency alone as readiness.

## Summary

The exact wait contract is: same-session V3 records, exact `(session_id, build_rid, node_id, final_kv_hash)`, ordered build/KV/Mamba evidence, then `durability_barrier.combined_durable=true` followed by `residency_barrier.cold_residency=true`. R3’s reported 405 probe lines and zero V3 durable lines do not meet that contract. The strongest current explanation is a V2/probe-versus-V3 event/schema mismatch, with emitter deployment/activity still unconfirmed.

## Followups

- Run the proposed event-shape histogram and one-session smoke diagnostic under a fresh Task ID.
- If no V3 records exist, route the remaining work to the runtime/deployment owner to verify the V3 emitter deployment and marker-gated activation.

## Open issues / unknowns

- The raw R3 `/tmp/t38c-probe.log` contents were not available within the authorized local read-only scope; the V2 shape is supported by local design/report evidence and the supplied R3 observation, not direct raw-line inspection.
- It is not established here whether R3’s zero V3 output came from stale V2 product files, an inactive V3 emitter, an event-path mismatch, or a later emitter-side failure.
- No remote process, file, or host was accessed or altered.
