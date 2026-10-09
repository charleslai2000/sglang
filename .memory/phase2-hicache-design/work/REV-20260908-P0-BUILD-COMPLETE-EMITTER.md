ENTRY: ACCEPT

# REV-20260908-P0-BUILD-COMPLETE-EMITTER

- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Artifacts

- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-BUILD-COMPLETE-EMITTER.md`
- Reviewed implementation: `python/sglang/srt/mem_cache/unified_radix_cache.py`
- Reviewed focused fixture: `3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused fixture: **PASS**.
- Implementation and fixture `py_compile`: **PASS**.
- AST parsing and implementation `git diff --check`: **PASS**.
- Independent extracted-method probe: **FAIL** for conflicting node binding.
  Binding node `shared` first to `(s1,1,r1)` and then `(s2,1,r2)` overwrote
  the node index to `s2/1/r2` while retaining both sidecars; the emitter then
  published `build_complete` for the conflicting second identity.
- Focused fixture has no explicit `finished_reason=None` unfinished-path case.
- No live engine, pytest, launcher, remote, or S=25 vehicle run performed.

## Summary

The call site is correctly placed after insert/node-context binding and before
cleanup. Marker/V3 gating, RID and final-hash checks, TP-group leader selection,
warm/abort guards, and exact duplicate/reopen behavior are present in the
covered paths. However, `_t38c_record_node_context` overwrites the single node
index for a conflicting session/build, so the emitter's readback equality check
is not fail-closed. This is merge-blocking under the frozen architecture
contract. The required unfinished fixture evidence is also absent.

## Followups

1. Make node-context binding detect an existing different node identity and
   suppress `build_complete` on conflict/ambiguity.
2. Add an explicit unfinished-request fixture with `finished_reason=None`.
3. Rerun the independent gate, then obtain the required live S=25 RH-off
   vehicle evidence.

## Open issues

- F-1: conflicting node context can yield a false build identity.
- F-2: unfinished emission is guarded in code but not covered by the focused
  fixture.
- Live runtime acceptance is not established.
- The dirty worktree has no task-specific commit boundary for full diff
  attribution.
