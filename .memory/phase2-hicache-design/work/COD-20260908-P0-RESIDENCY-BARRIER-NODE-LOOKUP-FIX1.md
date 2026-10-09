ENTRY: ACCEPT

# COD-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1

- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `coder`
- Invocation status: `done`
- Scope: authorized product file and focused emitter test only; no remote or
  process actions.

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added `_t38c_residency_node_lookup`, a strict lookup boundary for the
    serialized identity node ID. It accepts the product `NodeId` integer or
    its canonical decimal string, verifies the resolved node's ID, and returns
    no node for missing, wrong-ID, or distinct integer/string aliases.
  - The residency fold now uses this boundary before hash, identity, build,
    durability, detach, queue, and publication predicates. Strict six-field
    identity validation and all lifecycle semantics remain unchanged.

- `3090-dev/test_p0_residency_barrier_emitter.py`
  - Added regression coverage for integer/string NodeId resolution, missing
    nodes, wrong-node rejection, and ambiguous integer/string aliases.

## Verification evidence

All commands ran locally from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.

1. `python3 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit `0`; output included:

   ```text
   Exact NodeId/string lookup, missing, and ambiguity checks: PASS
   Real TP=1 scheduler checkpoint primary/extra probe: PASS
   P0 residency-barrier emitter focused checks: PASS
   ```

2. `python3 3090-dev/test_p0_trace_context_v4.py`

   Exit `0`: `P0 trace-context V4.3 focused checks: PASS`.

3. `PYTHONPYCACHEPREFIX=<temporary> python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit `0`.

4. AST parse of both authorized Python files: PASS.

5. `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py`: exit `0`.

6. `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py`:
   expected exit `1` because the focused test is untracked in this aggregate
   worktree; no whitespace diagnostics were emitted.

## Summary

The strict residency fold now resolves the real integer TreeCore NodeId from
the identity's canonical string form while rejecting missing, wrong, and
ambiguous matches. Existing identity, lock, parent/hash, queue, deduplication,
and vehicle-adjacent lifecycle behavior was not changed.

## Followups

- Independent tester/reviewer and fresh live evidence remain separate tasks.

## Open issues

- The aggregate checkout was already dirty in unrelated files; those files
  were preserved and not modified by this task.
- No remote/live acceptance claim is made.
