ENTRY: ACCEPT

# COD-20260908-P0-TRACE-CONTEXT-V4

- Task ID: `COD-20260908-P0-TRACE-CONTEXT-V4`
- Epoch: `E20260908-P0P1P2`
- Role: `coder`
- Invocation status: `done`
- Final status: `done`
- Admission: `ACCEPT`
- P0 runtime/pass claim: **not claimed**

## Summary

Repaired the V3 trace-context patch within the authorized product write set.
The changes are diagnostic-only and marker-gated; no scheduler, allocator,
promotion policy, retry, sleep, fsync, eviction, or remote-engine behavior was
changed.

## Changed files

- `python/sglang/srt/mem_cache/trace_context.py`
  - Requires an authoritative session generation when constructing context.
  - Keys slot-sidecar records by digest plus defensive lifecycle tokens carrying
    run, session, node, generation/build, and detach sequence identity.
  - Retires exact completion records and supports session/reset retirement.
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
  - Adds the optional `trace_context` parameter to
    `append_host_mem_release`, preserving existing callers.
  - Copies inferred/explicit context defensively.
  - Emits explicit `kv_durable` and `mamba_durable` fields with operation and
    attempt identity on the backup ACK evidence.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Retains complete KV/Mamba evidence per node until that node is promoted.
  - Retroactive frontier promotion uses the promoted node’s own operation and
    attempt; parent evidence is not reused for a child.
  - Adds top-level operation/attempt identity and explicit durable booleans to
    `durability_barrier` records, with exact completion counts.
  - Scopes request/node/session context by session, generation, and build RID;
    missing generation fails closed; close/reopen/reset retires trace state.
  - Retires lifecycle-scoped residency state on completion/barrier/reset and
    removes session-owned lifecycle state on session release.
- `3090-dev/test_p0_trace_context_v4.py`
  - Dependency-free focused static/lifecycle fixture for F1-F5 and the explicit
    durability evidence contract.

No vehicle, reviewer report, ledger, plan, context, extent allocator/backend,
or Mamba component file was edited by this V4 task.

## Acceptance evidence

- F-1: AST signature check confirms `append_host_mem_release` accepts the
  optional `trace_context`; the completed-prefetch call passes that keyword.
  The fixture probes marker-off context absence and marker-on context creation.
- F-2: `_t38c_durability_evidence` is keyed by node and stores operation,
  attempt, KV completion counts, Mamba expected/succeeded counts, and context.
  Each promoted node reads only its own stored record; evidence is consumed on
  promotion even when Mamba evidence is incomplete.
- F-3: Context maps use `(session_id, session_generation, build_rid)` identity;
  requests without generation produce no context. Open, release, and full reset
  retire stale mappings.
- F-4: `durability_barrier` includes top-level `operation_id`, `attempt_id`,
  `node_id`, `final_kv_hash`, and explicit KV/Mamba durable evidence, allowing
  repeated attempts to be distinguished.
- F-5: Slot records carry lifecycle tokens including run/session/node,
  generation/build, and monotonic detach sequence. Completion retires the slot
  record; reset/session release also retire remaining records.

## Commands and results

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**
  (`P0 trace-context V4 focused checks: PASS (F1-F5/static durability contract)`)
- `python3 -m py_compile` on the three product files and focused fixture —
  **PASS**
- Python AST parse of the three product files — **PASS**
- `git diff --check` — **PASS**
- `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q`
  — **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
  No dependency was installed.
- Remote engine/vehicle execution — **not run**, as prohibited by the task.

## Residual risks and open issues

- The focused runtime pytest remains environment-blocked; the standalone
  fixture provides static and helper-level coverage only.
- No live prefetch, frontier, session reuse, residency reuse, or storage
  backend runtime was exercised.
- The V4 implementation does not establish the P0 vehicle’s S=25 result,
  barrier-before-lookup ordering, cleanup, or ordinary correctness. Those remain
  separate vehicle/test/reviewer responsibilities.
- An independent reviewer must inspect the new revision before merge; no P0
  runtime/pass claim is made here.

## Followups

- Fresh independent review of the authorized product diff and focused evidence.
- Run the focused runtime unit test in an environment containing pytest and the
  required project dependencies.
- Only after independent acceptance may the separately authorized vehicle task
  run; extra implementation or vehicle work requires a fresh Task ID.

Artifacts: the three authorized product files, the dependency-free focused
fixture, and this report.
Evidence: focused fixture PASS, py_compile PASS, AST PASS, diff-check PASS, and
pytest dependency blocker reproduced.
