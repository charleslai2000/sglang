ENTRY: ACCEPT

# DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER

- Task ID: `DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER`
- Orchestration epoch: `2026-09-08-P0`
- Role: `debugger-deep`
- Invocation status: **done**
- Scope: read-only inspection of the authorized `sglang-3090-24g-opt` scheduler,
  Mamba, Unified cache and 3090-dev harness paths; read-only inspection of the
  named contract/gates/R8 reports.  The only write is this specialist report.

## Dispatch validation

Accepted.  The requested work is a hard causal reconstruction of a runtime
failure, with competing explanations and a bounded evidence target; it belongs
to `debugger-deep`.  It neither requires a product implementation nor a remote
run.  The available `docs/AGENTS.md` applies to Mintlify documentation work and
does not impose a conflicting instruction on the inspected product paths.

## Conclusion

R8 is best explained by a **lifecycle/provenance loss at the finalization
boundary**, not by a 55K workload that never crossed a legal Mamba checkpoint.

The build vehicle uses `max_tokens=12`.  R8 directly records extra-buffer
Mamba, page size one, and 2048-token prefill chunks.  The current Qwen3.5
configuration/default in this workspace has `mamba_track_interval=256`; R8's
preserved summary does not include a full resolved-argument record showing that
field.  Under that configuration, a prefill chunk creates a Mamba checkpoint candidate at its page-aligned
checkpoint grid; when that chunk is cached as unfinished, the Mamba component
donates/records that state and then deliberately clears the request-local
`req.mamba_last_track_seqlen`.  The subsequent at-most-12-token decode cannot
reach a 256-token decode tracking boundary, so it does not repopulate the
field before `release_kv_cache()` calls final `cache_finished_req()`.

At R8's historical finished boundary, `None` was converted to zero, producing
an empty radix key.  TreeCore returned root for that key, the finished path
overwrote `req.last_node` with root, and the V3 emitter correctly rejected root.
The failure is therefore not that root lacks a boundary; root is the visible
effect of finalization being asked to use a request-local *current* checkpoint
after its earlier valid checkpoint had been transferred and cleaned up.

This is not a claim that every R8 request had a surviving valid prior node.
R8 did not log the raw field, the prior node, component residency, or insert
result.  It is a source-and-workload-constrained conclusion.  The missing
direct observations are material and listed below.

## Producer/consumer chain and timeline

```text
vehicle build request (top-level session_id, max_tokens=12)
  -> Scheduler.handle_generate_request assigns session_generation
  -> ScheduleBatch.prepare_for_extend
       -> _mamba_radix_cache_v2_req_prepare_for_extend
          writes req.mamba_last_track_seqlen at a real prefill checkpoint
          and supplies the forward tracking mask/index
  -> model forward completes the tracked state
  -> cache_unfinished_req for each nonfinal prefill chunk
       -> MambaComponent.prepare_for_caching_req reads that sequence length
       -> UnifiedRadixCache.insert commits FULL+MAMBA at a nonempty key
       -> cache_unfinished_req records req.last_node/context
       -> MambaComponent.cleanup_after_caching_req(..., is_finished=False)
          clears req.mamba_last_track_seqlen
  -> short decode (0..12 tokens)
       -> BatchResultProcessor can write the field only on its tracking grid;
          no 256-token boundary is reached under the current/default config
  -> _handle_finish_state_updated_req
       -> release_kv_cache(..., is_insert=True)
       -> UnifiedRadixCache.cache_finished_req
       -> MambaComponent.prepare_for_caching_req sees None and returns 0
       -> [R8 historical code] insert(empty RadixKey)
       -> UnifiedTreeCore.begin_insert returns root
       -> req.last_node := root
       -> _t38c_emit_build_complete rejects root_node
       -> no build_complete / no usable final identity
```

R8 direct timeline, preserved from `DEBUG-20260908-P0-R8-ROOT-NODE.md`:

1. 08:41:26 UTC: Unified FULL+MAMBA tree starts with `page_size=1`.
2. 08:42:24--08:44:35: eight build requests prefill in 2048-token chunks to
   zero pending tokens.
3. 08:44:35: all eight build HTTP requests return 200; immediately afterward
   the engine records exactly eight `build_complete suppressed: root_node`.
4. Afterwards: the exact-R8 durable probe has 405 records and no
   `build_complete`; this is not a run-ID/tailer loss.  Cleanup later stopped
   the processes without deleting evidence, but no in-memory cache tree remains.

## `req.mamba_last_track_seqlen` lifecycle

### Writes and transfers

| Location | Effect | Relevance to R8 |
| --- | --- | --- |
| `managers/schedule_batch.py`, request reset/retraction path | Sets `None`. | A retraction can invalidate a current checkpoint, but R8 supplies no retraction evidence. |
| `ScheduleBatch._mamba_radix_cache_v2_req_prepare_for_extend` | When `extend_range.length >= mamba_checkpoint_grid(page_size)`, assigns the aligned real prefill checkpoint. | R8's 2048-token prefill chunks exceed the extra-buffer grid (`lcm(mamba_cache_chunk_size, 1)`; default fallback 64). This is the prefill producer. |
| `BatchResultProcessor._handle_finish_state_updated_req` | In non-lazy decode, writes `kv_committed_len - lookahead` only when the forward completed a Mamba boundary. | A 0..12-token completion cannot cross the current/default 256-token track interval. R8's exact resolved interval is missing. |
| `BatchResultProcessor._mamba_prefix_cache_update` / `_mamba_lazy_spec_update` | Writes `track_seqlen` only after an actual decode boundary/crossing. | Same reason under the current/default interval: no short-decode replacement boundary. |
| `SessionSlot.take_from_req` / `restore_to_req` | Transfers the field to/from a *streaming* session slot; `take_from_req` clears it from the request. | R8's top-level session-radix request is not streaming and falls through the wrapper, so this is not its route. |
| `MambaComponent.cleanup_after_caching_req(..., is_finished=False)` | Clears `req.mamba_last_track_seqlen` after unfinished caching. | This is the required, normal transfer/cleanup step that makes the final request-local field absent. |
| MLX-only paths and legacy `mamba_radix_cache.py` | Have additional assignments/clears. | Not selected by the CUDA Qwen3.5/Unified-cache R8 path. |

### Consumers

1. `MambaComponent.prepare_for_caching_req` is the decisive consumer.  In
   extra-buffer mode it reads the field.  For a finished request, `None` is
   normalized to `0`; for unfinished caching it returns `0` instead.
2. `UnifiedRadixCache.cache_unfinished_req` treats nonpositive effective length
   as no insert and executes cleanup.  Its prior nonzero insert is where a real
   node can exist.
3. R8's historical `cache_finished_req` lacked that no-insert guard.  It sent
   zero to TreeCore.  `UnifiedTreeCore.begin_insert` defines the zero-key result
   as root; it is not an identity or a Mamba checkpoint.
4. `_t38c_emit_build_complete` correctly rejects root before hash publication.
   `SessionRefTracker.register_session_ref` also rejects root.

## Competing hypotheses

| Hypothesis | Verdict | Falsification / evidence |
| --- | --- | --- |
| H1: The R8 workload never triggered a legal Mamba checkpoint. | **Rejected as the primary explanation (source/workload evidence); direct per-request telemetry absent.** | Extra-buffer prefill prepares a checkpoint for every extend whose length reaches the checkpoint grid. R8 has repeated 2048-token prefill chunks, page size 1, and its harness’s 55K history target. Even if a final tail were unusually short, earlier 2048 chunks meet the condition. The field’s being absent at finish therefore cannot itself mean no earlier checkpoint was produced. |
| H2: A legal checkpoint was generated, then lifecycle cleanup discarded the only request-local locator before finalization. | **Strongly supported, conditional only on the unpreserved R8 interval retaining the current/default value above 12.** | The unfinished path inserts the nonzero boundary and its Mamba cleanup explicitly clears the field. The vehicle limits build generation to 12 tokens; the current/default 256-token decode grid prevents a subsequent write. This predicts exactly `None -> 0 -> empty key -> root_node`, which is R8’s observed terminal sequence. |
| H3: Session-radix or streaming-session routing bypassed insertion or replaced a valid node with root. | **Rejected.** | Top-level `session_id` uses the normal `Req` path. `StreamingSession.try_cache_finished_req` returns false for non-streaming requests. Session-reference registration occurs after the result and does not call insert or rewrite it. |
| H4: A nonempty key was deduplicated to root, or page alignment made it empty. | **Rejected.** | `UnifiedTreeCore.begin_insert` chooses root only for `len(key)==0`; nonempty matching/insertion walks return a child. With page size one, alignment cannot erase a nonempty span. |
| H5: Repeated retraction/reset, rather than normal unfinished cleanup, cleared the field. | **Not established and unnecessary.** | A retraction reset can clear the field, but the R8 report records normal chunk completion and gives no retraction evidence. The normal cleanup mechanism alone fully predicts the outcome. |

## Current worktree versus R8

The current authorized worktree is dirty and now contains an uncommitted
provenance-oriented change in `UnifiedRadixCache`:

- `_t38c_record_mamba_boundary` records only a nonzero, newly committed,
  non-root FULL+MAMBA boundary with complete matching V3 context;
- `_t38c_finished_boundary_result` permits reuse only when that recorded
  boundary matches the live node, hash, request RID and context; and
- current `cache_finished_req` avoids empty-key insertion and asks that helper
  for an event/session-ref candidate.

This is consistent with the minimal remedy below and its focused fixture
contains the same no-root / validated-prior-boundary cases.  It is **not proof
that R8 deployed this code, that it was merged, or that it works in the R8
runtime**.  R8 predates the observed zero-length guard in the historical report,
and the dirty worktree prevents commit-based attribution.

## Minimal next owner/action

`NEEDS_REROUTE: coder` (fresh task) **only if the above provenance guard is not
already the exact revision to be shipped**.  The minimal product action is in
`UnifiedRadixCache`, not scheduler, tree core, emitter, session tracker or the
vehicle:

1. On each successful unfinished nonzero insertion, retain an explicit
   request/build-context-scoped record of the actual non-root FULL+MAMBA
   checkpoint (node ID, matching context/RID, final hash and real effective
   boundary).  Do not derive it from `len(tokens)` or from a bare `last_node`.
2. At a finished zero-effective-length boundary, skip the empty insert.  Emit
   and register only if that recorded candidate still resolves, remains
   non-root/non-tombstoned, retains usable FULL and MAMBA device-or-host data,
   and exactly matches context, request RID and final hash.  Otherwise release
   normally and emit nothing.
3. Preserve root rejection and the ordinary cleanup/lock-release path.

`NEEDS_REROUTE: tester` (fresh, separately authorized live task) after the
candidate revision is identified.  Add marker-gated scalar evidence for each
build: pre/post unfinished `mamba_last_track_seqlen`, effective cache length,
nonzero insert result/node/hash, boundary-record creation, final field/value,
candidate validation result, and final insert target.  Run the frozen R8 shape
(`max_tokens=12`) plus a variant that crosses one decode grid.  Acceptance is:
no root insertion/event without a candidate, and exactly one non-root V3 event
only with the validated recorded candidate.

## Evidence and artifacts

- R8 direct chronology and root theorem:
  `.memory/phase2-hicache-design/work/DEBUG-20260908-P0-R8-ROOT-NODE.md`.
- R8 cleanup/preservation record:
  `.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-S25-LIVE-R8-CLEANUP.md`.
- V3 producer contract and exact finalized-node requirement:
  `.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`.
- Mamba semantic contract and fail-closed prior-node invariants:
  `.memory/phase2-hicache-design/work/DOMAIN-20260908-P0-MAMBA-FINISH-LENGTH.md`.
- Accepted unit gates consulted: `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX1.md`,
  `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX2.md`, and
  `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md`.
- Source read: `schedule_batch.py`, `batch_result_processor.py`,
  `common.py`, `unified_radix_cache.py`, `unified_tree_core.py`,
  `mamba_component.py`, `streaming_session.py`, `session_ref_tracker.py`,
  `runtime_context.py`, `server_args.py`, and
  `3090-dev/p0_session_barrier_vehicle.py`.

## Open issues

1. R8 lacks direct scalar telemetry, so the last actual checkpoint sequence
   length, prior node ID/hash, and its device/host residency cannot be asserted
   per session from preserved logs.
2. No preserved in-memory tree exists after R8 cleanup, so a valid prior node
   cannot be retroactively validated for any of the eight requests.
3. The current dirty worktree includes the apparent cache-side remedy but has
   no task-specific commit or fresh runtime evidence.  It must not be reported
   as an R8 repair.
4. If product policy requires every finished request to create a *new* final
   boundary rather than reuse an earlier one, that is a different scheduler /
   model-forward lifecycle decision: it must force and prove a real Mamba
   checkpoint before release, never synthesize one from token length.
5. R8's complete resolved launch arguments (especially any override of
   `mamba_track_interval`) were not preserved in the supplied R8 report.  The
   next live probe must record that scalar before classifying the short decode
   as definitively below the active grid.

## Followups

- Preserve this as diagnosis, not a gate acceptance or implementation claim.
- Use the scoped coder action above for any absent/unmerged cache provenance
  change; use an independent tester for the discriminating live evidence.
