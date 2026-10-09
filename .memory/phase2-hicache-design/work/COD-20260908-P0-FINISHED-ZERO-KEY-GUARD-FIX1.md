ENTRY: ACCEPT

# COD-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1

- Task ID: `COD-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1.md`

## Summary

- `_t38c_finished_boundary_result` now fails closed before returning a non-empty
  `InsertResult` unless the resolved non-root node has a non-empty string final
  hash matching the recorded boundary and its current node sidecar exactly
  matches the request's complete V3 context.
- Existing request RID, session, generation, schema, and warm-RID checks remain
  before boundary reuse. The zero-boundary caller therefore registers a session
  reference only from the same fully validated `event_result`; stale/ambiguous
  sidecars and non-string hashes produce neither `build_complete` nor a session
  reference.
- No `len(token_ids)` Mamba boundary fallback, remote command, or unrelated file
  change was introduced. Existing unrelated dirty edits were preserved.

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`: added current node
  context exact-match, node identity, and string-hash validation to the finished
  zero-boundary helper.
- `3090-dev/test_p0_trace_context_v4.py`: added AST assertions and an extracted
  production-path probe for valid reuse, ambiguous sidecar, non-string hash,
  abort, unfinished, missing boundary, build-event suppression, and session-ref
  behavior.

## Evidence

- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**;
  `P0 trace-context V4.3 focused checks: PASS`.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-zero-key-guard python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- Direct invocation of
  `check_finished_zero_effective_length_fixture()` with AST-extracted helper
  and emitter — **PASS**; `AST/extracted production-path probe: PASS`.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` —
  **PASS**.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_trace_context_v4.py`
  emitted no whitespace diagnostics; its exit code 1 is the expected
  untracked-file/content-difference status against `/dev/null`.
- No engine, launcher, live vehicle, or remote execution performed.

## Followups

- Run the fresh independent reviewer gate for this repair.
- Live/runtime acceptance remains a separate authorized task.

## Open issues

- The target checkout remains aggregate-dirty with unrelated prior edits and no
  task-specific revision boundary; this report attributes only the two requested
  files and preserves the existing worktree state.
- No live runtime evidence was requested or collected in this coder invocation.
