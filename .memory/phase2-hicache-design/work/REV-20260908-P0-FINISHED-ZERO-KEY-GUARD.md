ENTRY: ACCEPT

# REV-20260908-P0-FINISHED-ZERO-KEY-GUARD

- Task ID: `REV-20260908-P0-FINISHED-ZERO-KEY-GUARD`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Artifacts

- Gate: [P0-FINISHED-ZERO-KEY-GUARD.md](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-FINISHED-ZERO-KEY-GUARD.md)
- Reviewed implementation: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Read authoritative build-complete contract, coder report, and all three
  designated accepted gates.
- Focused fixture: PASS.
- `py_compile`: PASS.
- `git diff --check`: PASS.
- Independent helper probe: valid integer non-root KV+Mamba reuse passed;
  abort, unfinished, RID/context/hash/root/missing-Mamba cases rejected.
- Independent stale-sidecar probe: `_t38c_finished_boundary_result` returned a
  non-null result while current node context was `None`, and the production
  `event_result` guard would still register a session reference.

## Summary

The zero-key guard correctly avoids empty radix insertion and preserves the
normal cleanup/free/lock structure. The gate is rejected because the boundary
reuse helper does not validate current node-sidecar identity (or string hash)
before returning `event_result`, while the caller registers a session reference
solely on non-null `event_result`. The emitter can suppress the build event but
cannot prevent this false session reference.

## Followups

- Fresh coder Task ID: make zero-boundary reuse fail closed on current node
  context and hash type, or gate session registration on equivalent validation.
- Add executable production-path coverage for ambiguous sidecar, invalid hash,
  valid reuse, abort, unfinished, no-boundary, and cleanup/ref behavior.
- Dispatch a fresh independent review after repair.

## Open issues

- Blocking finding: false session reference on stale/ambiguous node identity.
- Live engine/tester acceptance remains outside this invocation and was not run.
- Worktree is dirty without a task-specific commit boundary.

