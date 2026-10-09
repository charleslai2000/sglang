# DEBUG-20260908-P0-R8-ROOT-NODE

Task ID: `DEBUG-20260908-P0-R8-ROOT-NODE`  
Epoch: `2026-09-08`  
Role: `debugger-deep`  
Invocation status: **done — NEEDS_REROUTE: coder** for any code change; a fresh
`tester` task is required for a live reproduction.

## Finding

R8's eight `root_node` suppressions were not caused by the session-radix
reference path bypassing `UnifiedRadixCache.insert`.  Each was a real final
`cache_finished_req(..., is_insert=True)` insertion with an **empty effective
key**.  With R8's `page_size=1`, the UnifiedTreeCore can return root as the
insert result only when the key length is zero.  The effective length was
reduced to zero by the Mamba extra-buffer component's missing
`req.mamba_last_track_seqlen`, not by the approximately 55K input length.

This is an instrumentation/finished-cache semantic mismatch: the finished
path calls `insert` even for `effective_cache_len == 0`, while the unfinished
path expressly returns before inserting in that case.  The emitter correctly
rejects the resulting root as non-identifying.  No `build_complete` can then
be emitted and the vehicle remains at its initial 405 durable records.

## R8 timeline (direct evidence)

Remote run ID: `p0-s25-v43-fix2-live-20260908T003948Z`.

| UTC time | Observation | Evidence |
| --- | --- | --- |
| 08:41:26 | Unified tree starts with FULL and MAMBA components; server has `page_size=1`. | `engine.log:... Init Unified Radix Cache`; logged server args |
| 08:41:39–08:41:43 | Four `invalid_request_context` suppressions occur during startup/health traffic, before the session build fleet; they are not the later root result. | `engine.log:678,687,690,694`; the log identifies `HEALTH_CHECK_*` requests around these entries. |
| 08:42:24–08:44:35 | The eight active session builds are prefilled in 2048-token chunks. The final batch reaches `pending-token: 0`. | `engine.log` final prefill entries 958–977 |
| 08:44:35 | The last build HTTP request returns 200, followed immediately by exactly eight `T38C build_complete suppressed: root_node` lines. | `engine.log:978–986` |
| after 08:44:35 | No `build_complete` exists in the durable log. `/tmp/t38c-probe.log` remains exactly 405 lines, all with the exact R8 run ID; it contains only two storage submissions/persistences and no build-complete record. | remote `grep`/`wc` inspection; event aggregation |

The log also records `enable_session_radix_cache=True` and
`mamba_radix_cache_strategy='extra_buffer'`.  The trace contains session and
generation/build-RID context for s00000–s00007, so loss of the supplied run ID
or a tailer failure is not the explanation for these eight suppressions.

## Source-level causal chain (direct evidence)

1. `release_kv_cache` calls `cache_finished_req` with
   `is_insert=True` unless the request is aborted or explicitly skips radix
   insertion (`python/sglang/srt/mem_cache/common.py:202–222`).

2. The native top-level `session_id` route constructs a normal `Req` and gives
   it a session generation (`managers/scheduler.py:2634–2748`).  It does not
   construct the older streaming-session object.  Accordingly,
   `UnifiedRadixCache.cache_finished_req` first asks the embedded
   `StreamingSession`, whose handler returns `False` unless
   `req.session is not None and req.session.streaming`
   (`session/streaming_session.py:130–131,305–311`).  R8 therefore continues
   through the normal UnifiedRadixCache finished path.

3. That finished path invokes every component's
   `prepare_for_caching_req`, uses the minimum returned value as
   `effective_cache_len`, truncates `token_ids`/`kv_indices`, then always
   constructs a `RadixKey` and calls `self.insert` (`unified_radix_cache.py:1860–1899`).
   It has no `effective_cache_len <= 0` early return.

4. In R8's extra-buffer Mamba configuration,
   `MambaComponent.prepare_for_caching_req` sets
   `cache_len = req.mamba_last_track_seqlen`.  On a finished request, `None`
   becomes `0` and is returned (`unified_cache/components/mamba_component.py:684–720`).
   FULL has no truncation opinion; therefore this zero becomes the finished
   path's effective cache length.

5. `UnifiedTreeCore.begin_insert` returns an `InsertResult` whose
   `last_device_node` is root when `len(key)==0` (`unified_tree_core.py:911–937`).
   For every nonempty key, the walk can only target an existing/new non-root
   child (`:996–1100`).  Because R8 uses page size one, page alignment cannot
   change a nonempty token span into an empty key.  Thus the observed root
   result proves the effective finished key was zero length.

6. The finished cache caller records that result as `req.last_node`, then
   invokes `_t38c_emit_build_complete` (`unified_radix_cache.py:1908–1927`).
   The emitter deliberately rejects root before a hash lookup or durable
   write (`:904–962`).  Session-reference registration happens afterwards
   (`:1930–1937`) and itself returns without registering root
   (`unified_cache/session_ref_tracker.py:55–78`).

## Competing hypotheses

| Hypothesis | Result | Basis |
| --- | --- | --- |
| Session-radix directly bypasses insert or replaces its result with root. | Rejected. | Native session requests fall through the streaming wrapper; session refs are attached only after the finished result. No session-ref function calls insert or rewrites `result.last_device_node`. |
| The cache was disabled. | Rejected. | Disabled insert returns an `InsertResult` without a node, which would take the emitter's `missing_node` branch, not `root_node`; R8 initialized the Unified tree and emitted cache activity. |
| A nonempty key was fully deduplicated and therefore returned root. | Rejected. | The tree walk returns the matched child as target. Root is only selected by `begin_insert`'s zero-key branch. |
| The 55K prefill did not really complete. | Rejected as the cause of root. | R8 logged all chunks to zero pending tokens and eight HTTP 200s before the simultaneous suppressions. Completion does not guarantee a valid Mamba checkpoint boundary, however. |
| `mamba_last_track_seqlen` was absent at finalization. | Strongly supported; direct effective-zero proof plus exact component behavior. | The root theorem proves `effective_cache_len=0`; in the logged extra-buffer FULL+MAMBA configuration, the Mamba component is the only source that can produce zero from a nonempty finished request. The raw field value was not instrumented, so its `None` value is an explicit inference rather than a separately logged observation. |

## Required minimal follow-up

**Owner: coder (fresh task).**  Do not solve this by allowing root build
identities.  Keep the existing emitter rejection of root, unfinished, abort,
and invalid/mismatched context.

The owner should make the finished path obey the same zero-effective-length
contract as `cache_unfinished_req`:

1. If `effective_cache_len <= 0`, do not call `insert` with an empty key and
   do not attempt a build-complete emission from that synthetic root result.
2. To emit a legitimate finalized identity, retain or explicitly obtain the
   last **non-root, validated cache node** produced by a prior nonzero chunk
   for this request. Emit only when it still resolves, has a nonempty final
   hash, belongs to the same trace context/build RID, and the request is
   finished, non-aborted, and inserting. If no such candidate exists, emit
   nothing: no false positive is preferable to inventing an identity.
3. Register the session reference only for that same validated non-root node;
   preserve the current root no-op in `register_session_ref`.
4. Add a focused test matrix for (a) extra-buffer + no tracked boundary,
   (b) extra-buffer + a tracked non-root chunk, (c) abort, (d) unfinished
   chunk, and (e) context/RID mismatch. The expected result in (a) is no
   root insert and no build event; in (b) it is exactly one non-root event.

The prior-chunk fallback is intentionally conditional. R8's stopped process
does not leave an inspectable in-memory tree, so this investigation cannot
prove that each request had a still-valid prior non-root node at finalization.
A blind fallback to `req.last_node` would create the very root/stale/foreign
identity false positives the emitter is designed to prevent.

## Artifacts and evidence

- Source inspected read-only: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/{common.py,unified_radix_cache.py,unified_cache/unified_tree_core.py,unified_cache/session_ref_tracker.py,unified_cache/components/mamba_component.py}`, plus scheduler and streaming-session routing.
- Remote evidence inspected read-only: `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8/{engine.log,run-id}` and `/tmp/t38c-probe.log` on the authorized target.
- No source, remote evidence, storage, or runtime state was modified; no run was launched.

## Open issues

1. **Missing direct field telemetry:** R8 did not record
   `mamba_last_track_seqlen`, `effective_cache_len`, the pre-finish
   `req.last_node`, or the returned insert target. The causal conclusion is
   source-constrained, but a future narrow probe should record only these
   scalar/node-ID facts.
2. **No legitimate fallback proven:** whether a validated prior non-root node
   exists for all eight R8 requests is unknown after cleanup. It must be
   checked live before a coder chooses a fallback design.
3. **R7 comparison is non-causal:** R7's unusable run-ID/tailer makes its
   larger storage-event count unsuitable as evidence that session radix itself
   caused R8's root outcome.

## Followups

- `NEEDS_REROUTE: coder` for the narrowly scoped finished-zero and validated
  non-root-candidate contract above.
- After implementation, `NEEDS_REROUTE: tester` for an authorized live R8-like
  run with the scalar probe and exact build/storage identity assertions.
