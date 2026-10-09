ENTRY: ACCEPT

# COD-20260908-P0-BUILD-COMPLETE-EMITTER-FIX1

- Orchestration epoch: `2026-09-08`
- Role: `coder`
- Invocation status: `done`
- Scope: the two authorized product/fixture files only.

## Artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `_t38c_record_node_context` now scans existing node candidates before
    indexing a context.
  - A differing candidate or an already-ambiguous node stores `None` in the
    node-only index, preserving fail-closed ambiguity; it never overwrites the
    index with a conflicting context.
  - An exact existing context remains idempotent.
  - Changed implementation lines: 853-879.
- `3090-dev/test_p0_trace_context_v4.py`
  - Added an explicit `_BuildReq("build-a", finished_reason=None)` fixture and
    asserted zero emitted records.
  - Changed fixture lines: 196-199.

## Verification evidence

Executed from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

1. `python3 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `0`
   - Output: `P0 trace-context V4.3 focused checks: PASS`
2. `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-build-complete-fix1 python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `0`
   - Output: none.
3. AST parse of both authorized files.
   - Exit: `0`
   - Output: `AST parse: PASS`
4. `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `0`
   - Output: none.
5. `git diff --no-index --check /dev/null 3090-dev/test_p0_trace_context_v4.py`
   - Exit: `1`, because the fixture is untracked and differs from `/dev/null`.
   - Output: none; no whitespace diagnostics.
6. Dependency-free AST-extracted conflict probe.
   - Exit: `0`
   - Output: `conflict probe: PASS`
   - Evidence: after contexts `s1/r1` and `s2/r2` recorded for the same node,
     the node-only index was `None` and node readback was `None`.

No engine, pytest, launcher, remote, deployment, or unrelated command was run.

## Summary

Both blocking findings are repaired without changing the V3-only marker gate,
RID/hash equality, TP-group rank semantics, or the existing call boundary.

## Followups

- Rerun the independent P0 build-complete gate.
- Live S=25 RH-off acceptance remains with its named runtime/operational owner.

## Open issues

- Independent gate acceptance and live runtime evidence remain outstanding; this
  task performed only the requested unit-level verification.
