ENTRY: ACCEPT

# DOMAIN-20260908-P0-MAMBA-FINISH-LENGTH

- Task ID: `DOMAIN-20260908-P0-MAMBA-FINISH-LENGTH`
- Orchestration epoch: `2026-09-08`
- Role: `domain-analyzer`
- Invocation status: **done**
- Scope: read-only semantic analysis of the authorized opt worktree and the
  designated R8 debug report. No product or remote files were changed.

## Decision

`req.mamba_last_track_seqlen is None` in extra-buffer mode means **no current
validated Mamba checkpoint boundary is available**. It must not be converted to
an ordinary zero-token boundary. The finished-cache operation has two legal
outcomes:

1. If no validated prior non-root boundary exists, fail closed: do not insert an
   empty radix key, do not emit `build_complete`, and do not register a session
   reference. Release the request's KV/Mamba resources and locks through the
   ordinary no-insert cleanup path.
2. If a validated prior non-root KV+Mamba boundary exists, it may be reused as
   the final identity. Reuse is conditional, not a fallback from token count.

If the product requires every finished request to create a final cache boundary,
the scheduler/model-forward owner must finalize a real Mamba checkpoint before
calling `cache_finished_req`. It may not manufacture the field from
`len(token_ids)`, a live slot id, or the root node. If it cannot establish that
checkpoint, outcome (1) remains the correct behavior.

The minimal immediate owner/action is the cache owner (`coder`, fresh task): make
the finished path honor its existing zero-effective-length contract, skip the
empty insert, and preserve root rejection. A guaranteed final-boundary change,
if desired, belongs to the scheduler/model-forward lifecycle owner, not to the
durability emitter or session-reference tracker.

## Terminology and actors

- **Finished request:** `req.finished_reason` is set. An abort is finished for
  resource release but is not a successful build identity.
- **Effective cache length:** the minimum of the request token span and all
  component truncation opinions. In extra-buffer mode Mamba contributes
  `req.mamba_last_track_seqlen`.
- **Mamba checkpoint boundary:** a sequence position for which the tracked
  ping-pong state is actually valid and corresponds to the KV prefix inserted
  at that position. `None` means unknown/unavailable; it is not an empty
  checkpoint.
- **Root node:** the tree's empty-key anchor. It is a structural match anchor,
  not a request/build identity.
- **Prior boundary:** a live, non-root tree node previously inserted at a
  nonzero Mamba/KV boundary for this same request/build context. `req.last_node`
  is only a candidate pointer; it is not provenance by itself.

Actors are separated by authority: the scheduler/batch-result path owns whether
forward actually completed a Mamba boundary; `UnifiedRadixCache` owns the final
KV/Mamba insertion and node identity; the trace emitter owns only publication
of an already validated non-root identity; session tracking may register only a
validated non-root leaf.

## Required invariants for prior-node reuse

All of these must hold; otherwise treat the candidate as absent:

1. The operation is an insertion (`is_insert=True`), the request is finished,
   and `finished_reason` is not `FINISH_ABORT`.
2. The candidate node resolves in the current tree arena, is not deleted or a
   forced-miss tombstone, is not the root, has a non-empty node id, and has a
   non-empty final KV hash.
3. The node has usable FULL KV data (`value` or valid `host_value`) **and**
   usable Mamba checkpoint data (`value` or valid `host_value`). Device absence
   alone is not disqualifying when HiCache host backup is the supported reuse
   path; actual execution must load it back before reading it.
4. Provenance proves that the node was produced by a prior nonzero cache insert
   at a real Mamba tracking boundary for this request/build. A bare
   `req.last_node`, matching token prefix, node id, or hash is insufficient.
   The Mamba checkpoint and KV boundary must refer to the same prefix end; do
   not infer this by blindly using `len(token_ids)`.
5. The node's trace context exactly equals the request's valid build context:
   schema `p0_durable.v3`, non-empty `session_id`, present
   `session_generation`, non-empty `build_rid`, no `warm_rid`, and
   `str(req.rid) == context["build_rid"]`. Ambiguous, stale-generation,
   foreign-build, or contextless candidates fail closed.
6. Session-reference registration, if enabled, uses that same validated node
   and current session generation. Root registration remains a no-op.

If only a host-side Mamba/KV copy remains, the semantic identity can remain
valid for HiCache reuse, but it is not an immediately readable device state;
the load-back path must be part of the actual consumer use case. If either side
of the KV/Mamba pair is absent, there is no reusable boundary.

## Confirmed evidence

- `mamba_component.py:684-720`: extra-buffer finished caching reads
  `req.mamba_last_track_seqlen`; `None` is changed to `0`, while the no-buffer
  path derives a length from the actual state and ReplaySSM flush boundary.
- `unified_radix_cache.py:1865-1897`: finished caching takes the minimum
  component length and always constructs/inserts the resulting key; zero thus
  reaches `UnifiedTreeCore` as an empty key.
- `unified_tree_core.py:911-937`: an empty key returns the root node; this is
  structural behavior, not evidence of a completed build.
- `unified_radix_cache.py:904-976`: the build emitter correctly requires a
  finished non-aborted insert, valid request context, non-root node, non-empty
  node id/hash, and exact node-context equality; root is explicitly rejected.
- `unified_radix_cache.py:1938-1994`: unfinished caching already skips insert
  when `effective_cache_len <= 0` and invokes component cleanup. The component
  contract in `tree_component.py:614-621` also describes `insert_result=None`
  as the no-insert cleanup case. The finished path does not yet honor the same
  contract.
- `batch_result_processor.py:1115-1149,1204-1253`: the scheduler records
  `mamba_last_track_seqlen` only for a completed/known real tracking boundary,
  then performs finish release at `:1157-1189`. This is the authoritative
  source for option (c); it cannot justify a synthetic value when no boundary
  completed.
- `unified_radix_cache.py:2039-2048`: unfinished inserts update `req.last_node`
  and record context, so a prior node can exist even after cleanup clears
  `mamba_last_track_seqlen`; the pointer alone does not prove Mamba-boundary
  provenance.
- `session_ref_tracker.py:54-79`: session refs already reject root and require
  a current session generation; this boundary must remain unchanged.
- `DEBUG-20260908-P0-R8-ROOT-NODE.md:9-23,42-75,94-122`: R8 directly ties the
  eight root suppressions to empty effective keys from missing extra-buffer
  Mamba tracking, and explicitly rejects allowing root identities or blind
  `req.last_node` fallback.

## Contradictions and semantic boundaries

1. **Implementation vs component contract:** finished caching inserts after a
   zero effective length, while unfinished caching and the component cleanup
   contract describe zero as a no-insert case. This is the actionable mismatch.
2. **Field meaning vs historical state:** `mamba_last_track_seqlen` is cleared
   after unfinished caching, so `None` can coexist with a valid earlier node.
   That does not make the current finished state valid; only explicit prior-node
   provenance can bridge the gap.
3. **Identity vs durability:** a valid non-root build identity does not claim
   storage durability or device residency. The existing emitter contract keeps
   those meanings separate; no Mamba/KV durability may be invented here.
4. **Cache reuse vs trace publication:** a node may be a cache match without
   being eligible for this request's build identity. Exact context and
   request-RID checks are required for publication.

## Edge cases

- Request shorter than the first Mamba checkpoint grid: no checkpoint; fail
  closed unless an independently validated earlier boundary exists.
- Finished abort, `is_insert=False`, skipped radix insertion, invalid context,
  or RID mismatch: release resources but emit/register nothing.
- Candidate evicted from device but backed by both valid host KV and host Mamba:
  identity may remain reusable through load-back; device-only checks are too
  strict, but missing either host/device side is a miss.
- Candidate deleted, forced-miss, ambiguous across contexts, stale across
  session generations, or root: fail closed.
- A non-empty request with an empty effective key is still not a valid build;
  input/output token count cannot authorize root identity.

## Followups

- `NEEDS_REROUTE: coder`: implement the narrow finished zero-length no-insert
  guard and preserve cleanup/lock release; add focused tests for no checkpoint,
  validated prior boundary, abort, unfinished, and context/RID mismatch.
- `NEEDS_REROUTE: scheduler` only if the product chooses option (c): establish
  and prove a real final Mamba boundary before cache release. This is separate
  from the minimal cache guard.
- `NEEDS_REROUTE: tester` after either change for the live R8-like lifecycle,
  asserting no root insertion/event and exactly one event for a validated
  non-root boundary.

## Open issues

1. The current source has no explicit field proving that `req.last_node` was
   inserted at a prior Mamba checkpoint rather than obtained by prefix match;
   a coder must not treat the pointer alone as sufficient.
2. R8 did not record the raw `mamba_last_track_seqlen`, prior `req.last_node`,
   or candidate component residency at finalization, so it cannot establish
   that a valid prior boundary existed for each request.
3. Whether host-only Mamba state is acceptable for the intended final identity
   needs the downstream cache consumer's explicit decision; the existing
   HiCache matcher/load-back path supports it, but immediate device readability
   would require a load-back precondition.

