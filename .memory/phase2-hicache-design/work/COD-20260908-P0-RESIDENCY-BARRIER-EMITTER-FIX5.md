STATUS: done

# COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX5

- Task ID: `COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX5`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `coder`
- Invocation status: `done`
- Admission: `ACCEPT`

## Summary

Closed FIX4 blocker B1. `_t38c_residency_barrier` now checks the owning cache
controller's primary KV `host_mem_release_queue` and every
`extra_host_mem_release_queues` queue under the controller's release-handoff
lock immediately before logging. A non-empty queue, or a missing required
queue/lock surface, returns without publishing. The existing cache-owned
residency `RLock`, six-field identity, completion-triggered re-entry, strict
build/durability/device/live/root/forced-miss predicates, and at-most-once
publication state remain unchanged.

## Changed artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added the fail-closed primary/extra release-queue predicate around the
    existing residency-barrier publication.
  - Holds `_t38c_release_handoff_lock` through the queue check and log call so
    enqueue/pop handoff cannot race the publication decision.
- `3090-dev/test_p0_residency_barrier_emitter.py`
  - Added dependency-free primary-KV and extra-host-queue regression cases:
    non-empty queue produces no event; draining then polling produces exactly
    one event; repeated polling remains one.
  - Retained all prior focused emitter, F-1/F-2/F-3/F-4, and marker-off cases.

No vehicle, Mamba component, ledger, gate report, remote host, or unrelated
file was modified.

## Verification evidence

All commands ran locally from
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`; no remote/live run
was performed.

1. `python3 3090-dev/test_p0_residency_barrier_emitter.py`

   Output included:

   ```text
   No-next-request final-token trigger: PASS
   Non-empty host-release queue barrier: PASS
   F-3 run-ID collision probe: PASS
   F-4 invalid residency context ...: PASS
   P0 residency-barrier emitter focused checks: PASS
   ```

2. `python3 3090-dev/test_p0_trace_context_v4.py`

   ```text
   P0 trace-context V4.3 focused checks: PASS
   ```

3. `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix5-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit code `0`.

4. AST parse:

   ```text
   AST parse: PASS python/sglang/srt/mem_cache/unified_radix_cache.py
   AST parse: PASS 3090-dev/test_p0_residency_barrier_emitter.py
   ```

5. `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py`

   Exit code `0`, no output.

6. `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py`

   Exit code `1` is expected because the focused fixture is untracked in this
   aggregate worktree; no whitespace diagnostics were emitted.

## Next fresh review conditions

Dispatch a fresh independent reviewer for the FIX5 gate. The reviewer should
inspect the exact scoped diff and verify that primary and extra host-release
queues are checked under the handoff lock before publication, that queue drain
retry and at-most-once behavior hold, and that all FIX3/FIX4 protections remain
intact. This report makes no remote/live acceptance claim.

## Open issues

- Live/remote S=25 residency and warm behavior remains unverified and belongs
  to the separately authorized operational/test work.
- The aggregate worktree remains dirty without a task-specific commit boundary;
  attribution is limited to the authorized paths and this report.
