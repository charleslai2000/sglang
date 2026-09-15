ENTRY: ACCEPT

# P0 durable V3 `build_complete` emitter independent gate review

- Task ID: `REV-20260908-P0-BUILD-COMPLETE-EMITTER`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Scope and authoritative inputs

Reviewed read-only:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_trace_context_v4.py`
- `3090-dev/p0_session_barrier_vehicle.py`
- `python/sglang/srt/mem_cache/trace_context.py`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `COD-20260908-P0-BUILD-COMPLETE-EMITTER.md`
- accepted `review/gates/P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2.md`

The worktree is dirty with unrelated earlier Phase-2 changes. No product,
vehicle, launcher, or ledger files were modified by this review. This report is
the only gate artifact written in the product worktree.

## Findings

### F-1 — High / blocking: conflicting node context is overwritten before readback

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:851-858`,
`861-916`.

`_t38c_record_node_context` stores contexts under a tuple containing
`(session_id, session_generation, build_rid, node_id)`, but its authoritative
lookup index is only `node_id`. When a different session/build records the same
node, line 858 overwrites `_t38c_node_context_index[str(node.id)]` with the new
tuple; it does not detect that the node already has a conflicting binding. The
emitter then reads that overwritten index at line 915, sees the new context as
equal, and emits `build_complete`.

Independent boundary probe:

1. Bound `shared` to `(s1, generation 1, r1)`.
2. Bound the same `shared` node to `(s2, generation 1, r2)`.
3. Observed `_t38c_node_contexts` retain both tuples while
   `_t38c_node_context_index['shared']` points to `s2/r2`.
4. Invoked the extracted emitter for `s2/r2`; it emitted one successful
   `build_complete` record for the conflicting binding.

This directly violates the architecture memo's authoritative boundary:
already-bound or ambiguous nodes must fail closed and produce no build event
unless the existing node-side binding is exactly the request context. It can
allow a later session/build to claim a shared or reused radix node and can
produce an invalid exact identity join in the vehicle. The index/binding logic
must preserve the conflict and make the emitter return without publishing.

Acceptance impact: **merge-blocking** for exact node/context equality,
conflict handling, and fail-closed P0 evidence.

### F-2 — Medium / blocking evidence gap: unfinished-request fixture is absent

Location: `3090-dev/test_p0_trace_context_v4.py:90-201`.

The emitter does guard `finished_reason is None` at
`unified_radix_cache.py:886-887`, but `_BuildReq` defaults to a non-`None`
object and the focused checks only exercise non-insert and explicit abort
cases at lines 191-194. There is no fixture invocation with
`finished_reason=None`, despite the frozen contract requiring zero emission on
unfinished paths.

The implementation guard independently returns no event for that input, but
the required regression evidence is missing. Add an explicit unfinished case
to the focused fixture so future changes cannot remove this gate unnoticed.

Acceptance impact: the required fixture evidence for “no unfinished emission”
is incomplete; this remains open even after F-1 is fixed.

## Requirement review

- Exact producer boundary: **implemented as intended**. The call at
  `unified_radix_cache.py:1852-1862` follows insert, `req.last_node`, and
  node-context binding, and precedes component cleanup at line 1864.
- Marker/V3 gating: **pass by inspection**. The helper requires the marker,
  exact `p0_durable.v3` context, complete identity, and uses the existing
  logger; it emits no compatibility V2 build event.
- Context/RID/node/hash equality: **fail** because F-1 permits conflicting
  node bindings to be overwritten and then pass readback.
- Warm/abort/unfinished exclusion: **code guard pass; fixture incomplete**
  for unfinished as F-2. Warm RID mismatch and explicit abort are covered.
- Canonical TP leader fail-closed behavior: **pass by inspection and fixture**.
  TP=1 publishes; multi-rank publication requires initialized
  `get_rank(group=self.tp_group) == 0`; no global-rank fallback is present.
- Ordering and duplicate/reopen behavior: **pass for the covered paths**.
  The call is before cleanup; repeated exact identities are allowed; RID and
  generation separation is exercised. Conflicting node binding remains the
  blocking exception.
- Scope/diff: **scoped paths inspected**. The current checkout also contains
  unrelated pre-existing modifications, so authorship of the dirty-file
  aggregate cannot be independently attributed to this Task ID. No unrelated
  product file was changed by this review.
- Vehicle compatibility: **pass by contract inspection** for the emitted
  field shape. The existing vehicle requires exact V3 and the four-field
  identity; its helper remains fixture-only and is not used by the product
  emitter.

## Evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-build python3 -m py_compile ...` —
  **PASS** for the implementation and focused fixture.
- AST parse of the implementation and fixture — **PASS** (the fixture itself
  performs AST extraction).
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` —
  **PASS**.
- Independent AST-extracted conflict probe — **FAIL as a gate test**: the
  conflicting second binding was indexed as authoritative and produced a
  `build_complete` record.
- No engine, pytest, launcher, remote, or live S=25 vehicle run was performed;
  live acceptance remains separate and is not inferred here.

## Verdict and followups

Status: `done`.

The emitter has the intended narrow call boundary, V3 marker gating, RID/hash
checks, TP leader rule, and cleanup ordering, but it is **not accepted**. Fix
F-1 by making node-context binding conflict-aware and fail closed, then add the
unfinished fixture required by F-2 and rerun this independent gate. Live
S=25 RH-off evidence is still required after the narrow gate is accepted.

Open issues:

1. F-1 conflicting node binding can produce a false logical build identity.
2. F-2 unfinished-request regression evidence is missing.
3. Live runtime/vehicle acceptance remains outstanding.
4. The dirty worktree lacks a task-specific commit boundary for full diff
   attribution.
