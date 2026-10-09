ENTRY: ACCEPT

# V4.2 coder report

- Task ID: `COD-20260908-P0-TRACE-CONTEXT-V4.2`
- Epoch: `E20260908-P0P1P2`
- Role: `coder`
- Status: `done`
- Invocation: accepted; extra work requires a fresh Task ID.

## Artifacts

Authorized product/test changes are limited to:

- `python/sglang/srt/mem_cache/trace_context.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `3090-dev/test_p0_trace_context_v4.py`

This report is the requested deliverable. Review reports, vehicle files, ledger,
plan, context, and the live vehicle were not modified or run.

## Summary

- F1: Added a controller-owned release handoff lock. Marker-on producers publish
  the existing page payload and exact token together; the unified P0 drain takes
  the pair under the same lock. The exact drain has no digest fallback. Marker-off
  release behavior remains the original page FIFO path with no trace registration.
- F2: Removed `_t38c_durability_current` as an authority. Candidates remain
  keyed by node/operation/attempt, and promotion selects exactly one node/hash
  candidate. Same-hash ambiguity remains pending and emits no barrier.
- F3: Added complete context validation for session ID, non-null generation,
  build RID, node, and final hash before a barrier can be emitted. Missing context
  remains diagnostic-only.
- F4: Mamba durability now requires a non-empty ordered key set and exact
  succeeded-page count. ACK/candidate/barrier evidence includes key digest/count,
  operation/attempt identity, and rank-set metadata or `rank_set_unavailable`.
- F5: Session retirement replaces queued tokens for that session with inert
  metadata while preserving the real release FIFO; reset clears trace-only
  handoff metadata under the handoff lock. Token completion remains exact-token
  only.
- F6: The reviewer’s storage-query marker-off concern is pre-existing V2 query
  behavior outside this trace repair. The fixture adds a marker-gating assertion;
  no query redesign was made.

## Verification evidence

All passed from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 -m py_compile` on the four authorized Python files — PASS.
- Independent `ast.parse` on the four authorized Python files — PASS.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS.
- `git diff --check` for the authorized tracked paths — PASS.
- Static fixture checks prove the exact P0 drain uses the atomic pair helper,
  contains no legacy token-pop path, contains no mutable current selector, and
  requires context and non-empty Mamba proof before a barrier.
- Dependency-free fixture coverage includes concurrent handoff modeling,
  same-digest reuse, child/parent ordering, same-hash repeated attempts,
  missing context, zero-page Mamba, and session cleanup.

## Followups

- Independent reviewer gate acceptance is still required before any merge or P0
  vehicle decision.
- Runtime storage/backend and remote-engine verification remain outside this
  invocation and were not claimed.

## Open issues

- No runtime claim is made for real storage threads, distributed ranks, or
  allocator/backend interactions; pytest/runtime dependencies were not installed
  and the remote engine was not run.
- The implementation intentionally fails closed when same-hash candidates lack a
  tree-owned generation that would disambiguate them.
