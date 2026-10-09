# COD-20260908-P0-FINISHED-ZERO-KEY-GUARD

- Task ID: `COD-20260908-P0-FINISHED-ZERO-KEY-GUARD`
- Orchestration epoch: `2026-09-08`
- Role: `coder`
- Invocation status: **done**
- Entry: **ACCEPT**

## Artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Summary

- Finished caching now treats `effective_cache_len <= 0` as a no-insert path:
  it does not construct/insert an empty radix key, leaves
  `insert_result=None` for component cleanup, frees the request KV tail, and
  preserves request lock release.
- Added request/build-scoped Mamba-boundary provenance. A zero-length finish
  may publish/register only a live non-root node with recorded nonzero KV plus
  Mamba checkpoint provenance, usable Full/Mamba device or host values, a
  non-empty hash, and exact V3 session/generation/build-RID context.
- No `len(token_ids)` fallback, root identity, abort publication, or blind
  `req.last_node` reuse was added.
- Added a dependency-free focused fixture covering no boundary, valid integer
  non-root reuse, abort, unfinished, context conflict, missing Mamba data, and
  normal nonzero insertion; existing focused checks remain in place.

## Verification evidence

- `python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_trace_context_v4.py` — pass.
- `python3 3090-dev/test_p0_trace_context_v4.py` — `P0 trace-context V4.3 focused checks: PASS`.
- Standalone AST zero-guard probe — `AST zero-guard: PASS`.
- Extracted zero-key cleanup probe — `extracted zero-key cleanup probe: PASS`.
- Direct focused fixture invocation — `focused zero-boundary fixture: PASS`.
- `git diff --check` — pass.
- No engine or remote run performed.

## Followups

- Independent tester may run the authorized live R8-like lifecycle probe if
  runtime evidence is required.

## Open issues

- Live runtime validation remains outside this coder task and was not run.
- Existing unrelated dirty changes in the target worktree were preserved.
