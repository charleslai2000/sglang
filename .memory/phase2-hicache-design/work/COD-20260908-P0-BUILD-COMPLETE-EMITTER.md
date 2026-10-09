ENTRY: ACCEPT

# COD-20260908-P0-BUILD-COMPLETE-EMITTER

- Orchestration epoch: `2026-09-08`
- Role: `coder`
- Invocation status: `done`
- Scope: product-side V3 `build_complete` emitter and focused dependency-free fixtures only.

## Change manifest

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added a marker-gated `_t38c_emit_build_complete` helper immediately after
    final insert node-context binding.
  - Requires successful insert, non-abort completed request, complete V3
    context, request RID equal to preserved `build_rid`, non-root finalized
    node, non-empty string final hash, and exact node-context readback.
  - Publishes only from TP-group rank 0; TP=1 publishes locally and
    uninitialized/ambiguous multi-rank state fails closed.
  - Reuses `_t38c_durable_log`; emits no V2 compatibility event and carries
    null storage operation/attempt fields.
- `3090-dev/test_p0_trace_context_v4.py`
  - Added dependency-free AST-extracted emitter fixtures covering ordering,
    warm exclusion, missing context/readback/node/hash, marker-off,
    abort/non-insert, TP publication, exact duplicate identity, and session
    reopen generation/RID separation.

No other product, vehicle, launcher, memory, or review-gate files were changed
by this task.

## Verification evidence

Executed in `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

1. `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-build-complete python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `0`
   - Output: none.
2. AST parse of both authorized files.
   - Output: `AST parse: PASS`
3. `python3 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `0`
   - Output: `P0 trace-context V4.3 focused checks: PASS`
4. `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py`
   - Exit: `0`
   - Output: none.
5. `git diff --no-index --check /dev/null 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `1` because the fixture is untracked and differs from `/dev/null`;
     output was empty, with no whitespace diagnostics.

No engine, pytest, remote, launcher, or deployment command was run.

## Followups

- The separate launcher activation and live S=25 RH-off evidence remain with
  their named operational/runtime owners.

## Open issues

- Live runtime acceptance is not established by this unit-level task and
  remains subject to the existing P0 gate.
