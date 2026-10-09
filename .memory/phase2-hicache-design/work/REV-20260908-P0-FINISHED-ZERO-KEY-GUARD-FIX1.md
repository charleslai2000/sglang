ENTRY: ACCEPT

# REV-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1

- Task ID: `REV-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT**

## Artifacts

- Gate: [P0-FINISHED-ZERO-KEY-GUARD-FIX1.md](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-FINISHED-ZERO-KEY-GUARD-FIX1.md)
- Reviewed implementation: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Read the prior rejected zero-key gate/report, coder FIX1 report,
  authoritative build-complete contract, and accepted emitter FIX1/FIX2 and
  R7 FIX5 gates.
- Focused fixture: **PASS**.
- `py_compile` for the reviewed product and fixture: **PASS**.
- Independent extracted helper/caller probe: **PASS** for valid reuse and all
  requested rejection cases.
- `git diff --check`: **PASS** for the tracked product file; the untracked
  fixture comparison produced no whitespace diagnostics.
- No remote or live execution performed.

## Summary

The prior false session-reference path is closed. `_t38c_finished_boundary_result`
now requires the current node sidecar to exactly match the request context and
requires a non-empty string current hash matching the recorded boundary, in
addition to the existing V3, session, generation, RID, warm, finished, live
component, node, and uniqueness checks. The caller registers a session ref only
when this same validated result exists, so invalid zero-boundary cases produce
neither a build event nor a session reference. Valid reuse remains accepted and
produces both through the established path.

## Findings

No blocking or non-blocking findings.

## Followups

- Live/runtime vehicle acceptance remains a separate authorized task.

## Open issues

- No live runtime evidence was requested or collected in this invocation.
- The aggregate target checkout remains dirty without a task-specific revision
  boundary; this is an attribution caveat, not a FIX1 gate finding.

## Status

done
