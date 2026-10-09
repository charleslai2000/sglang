ENTRY: ACCEPT

Task ID: COD-20260908-P0-TRACE-CONTEXT-V4.3
Orchestration epoch: E20260908-P0P1P2
Role: coder
Status: done
Invocation status: done

Artifacts

- Implemented the authorized V4.3 source/test changes in the dirty worktree at
  /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt.
- Wrote this report at the exact requested path.
- No vehicle, remote engine, review report, ledger, plan, or context file was
  modified.

Changed files

- python/sglang/srt/mem_cache/trace_context.py
  - Added the explicit INERT_RELEASE_TOKEN.
  - Made completion exact-token-only; None and inert tokens cannot complete a
    digest lifecycle.
  - Added exact token lookup for allocator-free completion paths.
- python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
  - Enqueues one page/token pair for every release page, including marker-off,
    missing-context, and marker-transition cases.
  - Publishes page and metadata under the existing controller handoff lock.
  - Captures the actual TP rank topology at initialization and carries expected
    ranks and ACK identity metadata.
  - Retires queued tokens with the inert sentinel rather than None.
- python/sglang/srt/mem_cache/unified_radix_cache.py
  - Drains paired release metadata regardless of current marker state.
  - Makes queued and allocator completion paths fail closed without an exact
    token.
  - Aggregates Mamba ACK evidence by operation, attempt, node, and final hash;
    a multi-rank barrier requires every expected rank, while single-rank local
    success is all-rank by topology.
  - Carries expected/observed rank sets and counts, key digest/count, and exact
    operation/attempt metadata through candidate/barrier evidence.
  - Retires completed queued-release tokens during session release/reopen.
- python/sglang/srt/mem_cache/hiradix_cache.py
  - Narrowly updated the legacy shared release drain to consume paired metadata
    under the controller handoff path. Functional page freeing remains the same.
- 3090-dev/test_p0_trace_context_v4.py
  - Added dependency-free same-digest, missing-context, marker-transition,
    session-token, single-rank, and missing-rank fail-closed coverage.

Verification evidence

- python3 -m py_compile on trace context, unified radix, Hybrid controller,
  HiRadix, Mamba component, and the focused fixture: PASS.
- Independent ast.parse on the same six files: PASS.
- python3 3090-dev/test_p0_trace_context_v4.py: PASS
  (P0 trace-context V4.3 focused checks: PASS).
- git diff --check: PASS.
- python3 -m pytest 3090-dev/test_p0_trace_context_v4.py -q: not runnable;
  /usr/bin/python3: No module named pytest.

Summary

The two V4.2 blocking findings are addressed in scope: release completion is
bound to an exact paired token with inert fail-closed metadata, and Mamba
durability cannot become combined durability without a complete expected-rank
ACK set. Queued completion tuples are included in session retirement.

Followups

- Independent reviewer must re-run the V4.3 gate against the implementation
  diff and evidence.
- Runtime/P0 vehicle validation remains owned by the runtime/vehicle owners.
- No P0 runtime acceptance or pass claim is made here.
- Any additional implementation requires a fresh Task ID.

Open issues

- Pytest collection evidence is unavailable in this environment because pytest
  is not installed.
- The inherited marker-off storage-query compatibility issue remains documented
  and was not redesigned.
- Existing unrelated dirty-worktree changes were preserved and not reviewed or
  modified under this task.
