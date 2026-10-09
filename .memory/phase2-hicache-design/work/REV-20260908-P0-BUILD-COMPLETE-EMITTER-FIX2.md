ENTRY: ACCEPT

# REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX2

- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT** for the unit emitter gate

## Artifacts

- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-BUILD-COMPLETE-EMITTER-FIX2.md`
- Reviewed implementation: `python/sglang/srt/mem_cache/unified_radix_cache.py`
- Reviewed focused fixture: `3090-dev/test_p0_trace_context_v4.py`

## Evidence

- R4 terminal evidence independently correlates the real failure to integer
  `last_device_node`/`req.last_node` handling: `AttributeError` on
  `get_last_hash_value`, zero eligible sessions, and `NOT_VERIFIED`.
- The actual TreeCore API declares integer `NodeId` and resolves it through
  `node_by_id`; FIX2 performs that lookup before hash readback and catches
  missing/invalid lookup failures.
- Independent integer probe observed exact lookup, node ID, final hash, and
  context readback, with one V3 `build_complete` event.
- Missing integer, unhashable, arbitrary, root, and empty-hash cases failed
  closed without exceptions or emitted records.
- FIX1 conflict probe still leaves a reused node's authoritative index `None`.
- Marker/V3/RID/finished/abort/warm/TP/order/duplicate/reopen behavior passed
  source inspection and the dependency-free focused fixture.
- Focused fixture, AST parse, `py_compile`, and implementation whitespace checks
  passed. The untracked fixture's no-index whitespace check returned the
  expected difference status with no diagnostics.

## Summary

FIX2 is accepted at the narrow unit-gate level. It fixes the concrete R4 runtime
type mismatch by normalizing integer tree handles through `tree_core.node_by_id`
before calling node methods, while preserving FIX1 conflict-aware binding and
all reviewed V3 fail-closed lifecycle semantics.

The live P0 gate is not accepted: the supplied R4 run ended `NOT_VERIFIED`, and
no fresh runtime run was authorized or performed during this review.

## Followups

- Run a fresh authorized S=25 RH-off vehicle test and independently review its
  exact identity and causal-order evidence.
- Retain R4 as the failed runtime baseline.
- Supply the missing FIX2 coder summary for complete task provenance if required.

## Open issues

1. Fresh live runtime/vehicle acceptance is outstanding.
2. The expected FIX2 coder summary was not found in the designated memory path.
3. Worktree attribution remains caveated by unrelated dirty changes and no
   task-specific commit boundary.

