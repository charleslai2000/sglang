ENTRY: ACCEPT

# COD-20260908-P0-TRACE-CONTEXT-V4.1

- Task ID: `COD-20260908-P0-TRACE-CONTEXT-V4.1`
- Epoch: `E20260908-P0P1P2`
- Role: `coder`
- Status: `done`
- P0 runtime/pass claim: **not claimed**

## Summary

Closed the requested narrow V4 residuals without changing the vehicle or
normal marker-off release behavior. The trace-only durability and residency
joins now retain exact attempt/token identity at their handoff points.

## Changed files

- `python/sglang/srt/mem_cache/trace_context.py`
  - Added exact-token context lookup and token-aware completion.
  - Digest-only completion remains only for non-release legacy helper paths;
    queued release drain supplies the exact token.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Stores durability candidates under `(node_id, operation_id, attempt_id)`
    instead of one mutable node value.
  - Selects a promoted node's current candidate by its own attempt and final
    hash, emits at most one barrier for that promoted node, and retires only
    the selected candidate.
  - Release drain consumes the controller-owned parallel FIFO token for KV and
    extra pools before calling token-aware completion.
  - `release_session` now retires the same trace-only lifecycle state as
    `release_radix_session`; reset clears the durability selector state.
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
  - Added trace-only parallel FIFO metadata queues for KV and each extra pool.
  - Enqueue records the exact token returned by `remember_slot_context`; reset
    clears metadata queues. Existing release queue payloads and operations are
    unchanged.
- `3090-dev/test_p0_trace_context_v4.py`
  - Added dependency-free attempt-keyed child/parent/repeated-attempt fixture
    with exactly-once barrier assertions.
  - Added same-digest exact-token FIFO and slot-reuse assertions.

## Verification evidence

- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4 focused checks: PASS (F1-F5/static durability contract)`.
- `python3 -m py_compile` on the three product files and fixture — **PASS**.
- Python AST parse of the three product files and fixture — **PASS**.
- `git diff --check` — **PASS**.
- Remote engine/vehicle — **not run**, as prohibited.

## Residual limitations / open issues

- The fixture is dependency-free and exercises the attempt/token join models
  plus source contracts; it does not instantiate the full cache controller,
  tree core, storage backend, or live queue drain.
- No project pytest/runtime test was run, and no P0 runtime/pass conclusion is
  made. Independent re-review remains required.
- Unrelated pre-existing/user worktree edits were preserved and not modified.

## Followups

- Fresh independent review of this V4.1 revision and its focused evidence.
- Run project-level runtime coverage only under a separately authorized task
  and environment with dependencies.

Artifacts: the four authorized source/test files and this report.
Evidence: focused fixture PASS, py_compile PASS, AST PASS, and diff-check PASS.
Extra work requires a fresh Task ID.
