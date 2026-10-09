# DEBUG3060-RH-READY-RELEASE-20260910

status: done

## Invocation binding

- task_id: `TASK-20260910-RH-READY-RELEASE`
- invocation_id: `INV-20260910-DEBUG-RH-READY-RELEASE-R1`
- epoch: `20260910-r5`
- role/capability: `debugger-deep` / L2
- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (`pwd` matched before reads)
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs: `HANDOFF-2026-09-10-RH-SPEC-BUDGET.md`, `DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- memory_report: this file
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- native event channel: degraded; `mcp__codex_tui__send_message_to_thread` was not exposed in this invocation, so no lifecycle event could be sent. Shared-memory report is the evidence channel.

## Conclusion

**No cache-mode release-timing patch is required.** In cache mode, the speculative reservation is already released at the cache material finalizer, before the terminal handoff that the scheduler consumes to set `RestoreState.READY`/emit `ready_host`, and therefore before admission. Releasing it at admission would be incorrect: it would retain a staging-only budget charge while the request is already usable in Host and prevent the causal `SPEC_BUDGET` wake for another queued request.

The exact cache-mode success release point is `UnifiedRadixCache._handle_prefetch_result` immediately after the host insert/transfer commit (or dropped-material cleanup) and anchor unlock, at `unified_radix_cache.py:5746`, before removing `ongoing_prefetch`, decrementing physical occupancy, and publishing terminal `finalized` at lines 5747-5752.

Workspace note: after the diagnosis probes, the worktree contained an uncommitted buffer-mode addition at `unified_radix_cache.py:5683-5695` which calls `release_prefetch(..., "finalize")` after `stage_completed_prefetch`, plus a test import. I did not create, modify, or revert those product changes. Under the current issue path, buffer mode does not call `reserve_prefetch` (`5508-5520`), so this added buffer-mode call is presently an idempotent no-op for speculative accounting. It neither explains nor fixes cache-mode `SPEC_BUDGET` behavior; its future-purpose semantics need ordinary implementation review.

## Causal chain and invariant

1. A Ready-Horizon speculative cache-mode issue charges two separate quantities at issue:
   - physical `prefetch_tokens_occupied` at `unified_radix_cache.py:5511`;
   - speculative `inflight_speculative_tokens` through `reserve_prefetch` at lines 5516-5520 and 5118-5121.
2. On a successful cache-mode finalization, the host material is inserted/committed first (`5690-5743`). Only then does line 5746 call `release_prefetch(req_id, "finalize")`.
3. `release_prefetch` removes the one reservation record and subtracts the speculative amount only when its kind is `SPECULATIVE` (`5134-5143`). A repeated call is a no-op, so all removal paths preserve exactly-once accounting.
4. The finalizer then removes the active prefetch, decrements physical occupancy, and records terminal `finalized` (`5747-5752`). The scheduler later consumes that terminal, applies `FINALIZED -> READY`, releases the scheduler-local claim, and emits `ready_host` (`scheduler.py:3952-3992`). Admission is later in the scheduling loop (`6226-6301`).
5. Thus the required invariant is:

   `SPECULATIVE reservation exists iff the cache-mode prefetch is active and not terminally finalized/revoked/aborted/discarded/detached; READY host residency and physical occupancy are different ownership domains.`

For a parked B with cursor `N`, A's successful finalization changes `spec_budget N -> M` (`M < N`, normally zero). `ReadyHorizonPolicy.entry_cleared` uses strict `<` (`ready_horizon.py:361-366`), so the next causal RH pass can issue B once. The committed retrigger change (`4f41f5bab5`) correctly captures B's cursor after A's issue, not from the pre-issue snapshot.

## Competing hypotheses

| Hypothesis | Result | Evidence |
|---|---|---|
| Release belongs at A admission. | Rejected. | Cache finalizer releases at 5746; scheduler cannot set READY or admit until after terminal publication and reconciliation. Delaying it would block B despite A already being host-ready. |
| Release belongs when the cache prefetch material finalizes. | Confirmed. | Material commit precedes `release_prefetch`; terminal/READY/admission follow it. `test_finalize_path_releases_speculative_reservation` passes locally against the real finalizer harness. |
| `prefetch_tokens_occupied` is the same budget and should also release at READY. | Rejected. | It is physical occupancy. Cache mode decrements it in the same finalizer after the speculative release; buffer mode deliberately holds bounce occupancy through H2D completion (`buffer_mode/pipeline.py:696-750, 926-950`) and has no speculative reservation at all. The uncommitted buffer-mode `release_prefetch` call is therefore a no-op today. |
| A `ready_host` event for B proves A's reservation was released by B admission. | Unsupported / causal ordering false. | `ready_host` contains no counter snapshot. B can be READY while a distinct A is still active; A's reservation is tied to A's own terminal path, never B's admission. No designated raw 8192 trace was supplied to bind A/B IDs, counter snapshots, and terminal/admission ordering. |

## Exactly-once audit

- Success finalizer: `release_prefetch(..., "finalize")` at `5746`.
- Hybrid discard: `release_prefetch(..., "hybrid_discard")` at `5926`.
- Abort: `release_prefetch(..., "abort")` at `6180`.
- Revoke: `release_prefetch(..., "revoke")` at `6314`.
- Detach cleanup: `storage_attachment.py:378` with an exception-safe second idempotent call at `392`.
- Buffer-mode staged-abort returns before the cache helper only because buffer-mode issues never create a speculative reservation (`5510-5520`); it releases its physical bounce separately. The current uncommitted buffer-finalize call is likewise idempotent/no-op under that contract.

No double-release path was found: all paths converge on a helper that returns when no live reservation exists (`5134-5138`). The reservation map deletion is the once-only linearization point.

## Why the prior RH trace behaved as reported

The supplied 55K RH-ON evidence proves a different defect: B was parked with cursor `0` before A's issue, then A finalized and released `54999 -> 0`; strict `0 < 0` did not wake B. This is the stale-cursor defect fixed by commit `4f41f5bab5`, not a release-at-admission defect. The source and the focused remote regression (`2 passed`) support this distinction.

The purported 8192 trace observation is missing its raw ordered artifact from the designated inputs. It cannot prove that A remained `SPEC_BUDGET`-held *until B admission*. If its ordering is accurate, the only source-consistent interpretation is that A had not reached A's own terminal finalizer yet; B's ready/admission event cannot retain or release A's reservation.

## Regression oracle

1. Cache-mode success lifecycle: issue speculative A for `N`; make the real finalizer commit host material; before scheduler terminal consumption/admission assert reservation absent and `inflight_speculative_tokens` decreased by `N`; then assert READY and admission leave it unchanged.
2. A/B RH lifecycle: issue A, park B at post-issue cursor `N`, finalize A to `0`, run one event pass, and assert B gets exactly one RH issue. A second unchanged pass must not issue B again.
3. Strictness guard: `cursor=0/current=0` remains parked; `cursor=N/current=0` wakes. This prevents the unsafe `<=` workaround.
4. Terminal fanout: success finalizer, revoke, abort, hybrid discard, and detach each reduce the reservation exactly once; calling cleanup again leaves the counter at zero.
5. Mode split: buffer mode must retain `prefetch_tokens_occupied` while staged/H2D is active, while `inflight_speculative_tokens` stays zero throughout; cache mode must release both at cache finalization, not admission.
6. Live proof, if authorized separately: emit or capture rid-keyed `spec_budget` immediately before/after `release_prefetch`, then correlate A terminal, B negative cursor/wake, B `ready_host`, and B admission. Existing `ready_host` telemetry alone is insufficient for this counter-order proof.

## Verification performed

- Read source and reconstructed ordering across cache finalization, scheduler reconciliation, admission, and buffer-mode staging.
- AST/call-site audit found five cache reservation release reasons and the detach safety net.
- Local dependency-free finalizer harness test passed: `test_finalize_path_releases_speculative_reservation`.
- The selected local reservation suite was not fully runnable: 5 of 14 tests error because the current test harness does not initialize `_t38c_request_contexts`; one detach test skips without torch. These failures are test-fixture compatibility gaps, not evidence against the finalizer ordering. Earlier remote evidence records the two SPEC_BUDGET focused tests as `2 passed`.
- Final worktree inspection found unrelated-or-concurrent uncommitted edits in `unified_radix_cache.py` (8 additions/1 deletion) and `test_ready_horizon_unit.py` (one import). They were preserved; no product file was changed by this diagnosis.

## Artifacts

- Source: `python/sglang/srt/mem_cache/unified_radix_cache.py:5106-5143`, `5508-5521`, `5690-5752`, `5921-5934`, `6165-6220`, `6303-6542`.
- Scheduler: `python/sglang/srt/managers/scheduler.py:3874-3992`, `6226-6301`.
- Buffer-mode contrast: `python/sglang/srt/mem_cache/buffer_mode/pipeline.py:696-750`, `771-950`.
- Existing regression: `3090-dev/test_prefetch_budget_split_unit.py:280-402`; retrigger tests at `3090-dev/test_ready_horizon_unit.py:1035-1097`.

## Followups

- No product release-timing change should be made.
- A test owner should add the lifecycle oracle that explicitly brackets cache finalization, READY, and admission; repair the `_t38c_request_contexts` fixture before using the local budget suite as a gate.
- If the 8192 trace claim must be accepted or rejected empirically, obtain its raw rid-correlated telemetry; do not infer counter ownership from `ready_host`/admission ordering alone.

## Open issues

- Missing evidence: raw 8192 trace, A/B RID mapping, and rid-keyed speculative-counter snapshots were not in the authorized inputs.
- The local reservation harness has five current initialization errors (`_t38c_request_contexts` absent) and one skipped detach test due to missing torch; no full local gate is claimed.
