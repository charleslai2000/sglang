ENTRY: ACCEPT

# COD-20260908-P0-RESIDENCY-BARRIER-NODE-SIDECAR-FIX1

- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `coder`
- Invocation status: `done`
- Scope: authorized product file and focused emitter test only; no remote or
  process actions.

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `_t38c_record_node_context` now reads each visited node's exact ID and
    `get_last_hash_value()`, stores them in a per-node context copy, and
    rejects missing/invalid hashes without fabricating identity evidence.
  - Parent-chain entries bind their own node ID/hash. Existing immutable
    conflict/ambiguity behavior remains fail-closed and does not become
    last-write-wins.
  - `build_complete` and finished-boundary validation now compare only the
    stable request fields against the enriched sidecar; build registration
    uses the strict identity from that sidecar. The strict identity helper,
    queues, barrier predicates, scheduler admission, and vehicle were not
    changed.

- `3090-dev/test_p0_residency_barrier_emitter.py`
  - Added dependency-free regression coverage for leaf/parent six-field
    sidecars, strict identity and build registration, mismatch/ambiguity
    rejection, and repeat/conflict no-last-write-wins behavior.

## Verification evidence

All commands ran locally from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.

1. `python3 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit `0`; output included:

   ```text
   Six-field leaf/parent sidecar and no-last-write-wins checks: PASS
   Real TP=1 scheduler checkpoint primary/extra probe: PASS
   P0 residency-barrier emitter focused checks: PASS
   ```

2. `python3 3090-dev/test_p0_trace_context_v4.py`

   Exit `0`: `P0 trace-context V4.3 focused checks: PASS`.

3. `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix1-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit `0`.

4. AST parse of both authorized Python files: PASS.

5. `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py`: exit `0`.

6. `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py`:
   expected exit `1` because the focused test is an untracked file in this
   aggregate worktree; no whitespace diagnostics were emitted.

## Summary

The node-sidecar identity construction gap is fixed without relaxing strict
validation or changing residency lifecycle ownership. Local focused and V4.3
verification pass.

## Followups

- Independent tester/reviewer and a fresh live run remain separate tasks.

## Open issues

- The aggregate checkout was already dirty in unrelated files; those files
  were preserved and not modified by this task.
- No remote/live acceptance claim is made.
