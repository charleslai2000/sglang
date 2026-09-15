ENTRY: ACCEPT

# P0 finished zero-key guard independent gate review

- Task ID: `REV-20260908-P0-FINISHED-ZERO-KEY-GUARD`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_trace_context_v4.py`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `COD-20260908-P0-FINISHED-ZERO-KEY-GUARD.md`
- accepted gates `P0-BUILD-COMPLETE-EMITTER-FIX1.md`,
  `P0-BUILD-COMPLETE-EMITTER-FIX2.md`, and
  `P0-R7-JOIN-ROBUSTNESS-FIX5.md`

No product code, test code, remote host, launcher, or prior gate was modified by
this review. The target checkout has no repository-root `AGENTS.md`; the supplied
orchestration protocol was followed.

## Blocking finding

### P1 / blocking — validated zero-boundary result can create a false session reference

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:993-1027`,
`2076-2096`.

Evidence:

1. `_t38c_finished_boundary_result` accepts a stored boundary when the saved
   `(session, generation, build RID)`, request RID, live FULL/MAMBA values, and
   current hash match. It does not re-read
   `_t38c_trace_context_for_node(candidate_id)` and does not require the current
   hash to be a string.
2. `_t38c_emit_build_complete` does perform those stricter checks at
   `1105-1116`: an ambiguous/mismatched node sidecar or non-string hash causes
   the event to be suppressed.
3. The caller nevertheless uses only `event_result is not None` for session-ref
   registration at `2094-2096`. Therefore a zero-key finish can produce a
   non-null validated-looking `event_result`, have `build_complete` correctly
   rejected by the emitter, and still call `register_session_ref(req)`.

Independent AST-extracted probe result:

```text
current _t38c_trace_context_for_node(7) = None  # ambiguous sidecar
_t38c_finished_boundary_result(...) -> non-null InsertResult
production registration guard -> True
expected contract -> reject and do not register
```

The same split exists for a truthy non-string `final_kv_hash`: the emitter
rejects it, while the session-ref guard still sees a non-null result. This
violates the explicit zero-key requirement of no false session ref and the
architectural fail-closed node-context/hash contract. It can pin a node to a
session whose identity is no longer authoritative and can make later session
retirement/resource accounting inconsistent.

Acceptance impact: **blocking**. The gate cannot accept until the zero-boundary
reuse path either performs the same current node-context and string-hash
validation before returning its result, or the session-ref registration path
uses a separately validated predicate. Add focused cases for ambiguous node
sidecar and invalid hash type; both must produce no build event and no session
reference.

## Passed checks

- `effective_cache_len <= 0` is guarded before the production `insert` call;
  the guard contains no insert call (`unified_radix_cache.py:2023-2032`).
- The zero path frees the request tail, leaves `result=None` for component
  cleanup, then preserves request lock release and ordinary cleanup ordering.
- Abort, unfinished, missing-boundary, root, missing-Mamba, context/RID
  mismatch, and hash mismatch are rejected by the boundary helper.
- The valid boundary helper probe passed for an integer non-root node with live
  FULL/MAMBA values, matching context/RID, and matching hash.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-zero-key python3 -m py_compile
  python/sglang/srt/mem_cache/unified_radix_cache.py
  3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `git diff --check` on the tracked implementation — **PASS**; the untracked
  focused fixture produced no whitespace diagnostics under `git diff --no-index`.

## Evidence limitation

The fixture's `check_finished_zero_effective_length_fixture` is an AST check plus
a hand-written `FinishedZeroFixture` model; it does not invoke production
`cache_finished_req`, `_t38c_finished_boundary_result`, allocator free, lock
release, component cleanup, or session-ref code. It therefore missed the
blocking split above. This is a non-independent evidence gap in addition to the
implementation finding.

## Summary

The no-empty-key/no-synthetic-root guard and the ordinary cleanup/free/lock
structure are directionally correct, and the valid boundary conditions mostly
fail closed. However, stale or malformed node identity can still cause a false
session reference because validation used for event emission is stricter than
validation used for registration. This fails the requested resource-lifecycle
contract.

## Followups

- Repair the validation/registration split under a fresh coder Task ID.
- Extend the focused fixture with current-sidecar ambiguity and non-string hash
  cases and exercise the production path or an extracted production call graph.
- Re-run this independent gate after the repair; no live acceptance was run.

## Open issues

1. The blocking P1 finding above remains open.
2. No engine, live vehicle, launcher, remote, or tester acceptance was run, as
   prohibited by this dispatch.
3. The aggregate worktree remains dirty and has no task-specific revision
   boundary, so broad diff attribution is a process caveat.
