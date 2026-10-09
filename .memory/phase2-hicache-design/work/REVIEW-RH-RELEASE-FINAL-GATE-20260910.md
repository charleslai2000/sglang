status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
evidence:
- VERIFIED: Current uncommitted product diff is limited to the six expected modified source/test files; unrelated untracked workspace material is not part of the diff.
- VERIFIED: The diff preserves strict level semantics in `ReadyHorizonPolicy.entry_cleared`: a SPEC_BUDGET level wake is only `current < entry.epoch_cursor`; a same-level 0 -> 0 transition is not causal without a release-event epoch.
- VERIFIED: `HiCacheController.speculative_release_epoch` is initialized once, and `UnifiedRadixCache.release_prefetch` increments it only after finding a live SPECULATIVE reservation. Missing reservations and duplicate releases return before mutation; DEMAND reservations do not increment it.
- VERIFIED: All inspected UnifiedRadixCache removal paths (finalize, hybrid discard, abort, revoke, and detach) call `release_prefetch`; reservation ownership is removed before speculative accounting. The 0 -> N -> 0 ABA path is therefore represented by monotonically increasing release events even when no scheduler snapshot samples N.
- VERIFIED: Scheduler snapshots the controller event count monotonically with `max`, carries it through `CausalEpochs`, records it only for SPEC_BUDGET negative entries, and uses it as an additional directional event/clear condition. Physical occupancy and DEMAND reservations remain separate from speculative accounting.
- VERIFIED: On a successful production Ready Horizon issue, `_prefetch_kvcache` applies `PREFETCH_ISSUED`, transitioning the request to RESTORING. The new scheduler code pops the prior negative entry, and the RESTORING state does not re-park it.
- VERIFIED: The final ABA regression test uses the production `UnifiedRadixCache.reserve_prefetch`/`release_prefetch` helper for both reservations, verifies inflight returns to zero and release epoch reaches 2, then wakes the parked request and checks the negative entry is absent.
- VERIFIED: `python3 -m py_compile` and `git diff --check` were reported passing by the implementation reports. The four dependency-light reservation tests were reported passing.
- UNVERIFIED: Full Ready Horizon scheduler tests were not executed because the local interpreter lacks pytest/orjson/msgspec; live runtime acceptance was not run.
findings:
[MEDIUM | HIGH CONFIDENCE] /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py:1180-1188
problem:
The final assertion intended to prove that a later unrelated event cannot duplicate the already-woken request is internally inconsistent with the test fixture. After the ABA wake, the test appends `_req("r3", NONE)` and calls `_ready_horizon_pass()`. That frontier change is itself a causal event, and r3 is a valid NONE/staging candidate. The fixture is count mode with ready low/high 2/4 and the mock issue function does not consume a budget or otherwise reject r3, so the pass necessarily attempts r3. The assertion `scheduler.issued == ["r1", "r2"]` therefore fails (the expected list is `["r1", "r2", "r3"]` under the shown fixture), rather than isolating whether r2 duplicated.
evidence:
- `_pass_scheduler` configures legacy count mode (`ready_host_watermark_low_count=2`, `ready_host_watermark_high_count=4`) and its `_issue` mock unconditionally appends every issued rid and returns ISSUED.
- In the final test, after r2 wakes, `scheduler.waiting_queue.append(_req("r3", NONE))` changes `waiting_frontier`, making `epoch_event` true. r1/r2 are RESTORING; r3 remains NONE with restore potential, so `staging_candidates` includes r3.
- `ReadyHorizonPolicy.refill_plan` has zero ready residents and a high watermark of 4, so it places r3 in `to_issue`; `_ready_horizon_pass` invokes the mock and appends r3.
impact:
This is a blocking acceptance/test defect: the final focused scheduler test cannot pass as written, and it does not provide the claimed one-release/one-attempt proof. The production stale-negative fix is not falsified by this finding, but the final gate cannot be approved on a test that is deterministically expected to fail.
recommended_correction:
Make the later event genuinely unrelated while preventing a new candidate from being issued (for example, append an ineligible state such as RESTORING/FRONTIER request, or adjust the fixture so r3 is outside the refill budget), then assert that r2 occurs exactly once rather than asserting that no other request can issue. Keep a separate assertion that the negative entry for r2 remains absent and the release epoch does not advance.
confidence: high
open_issues:
- Dependency-backed Ready Horizon scheduler execution remains pending; no runtime result can be claimed until an existing environment with pytest, orjson, msgspec, torch, and local sglang runs the focused tests.
- Live 3060 acceptance remains a downstream gate and was not run.
- No separate production defect was established in strict cursor handling, speculative-only release accounting, physical/demand ownership, or inspected cleanup routing.
summary:
Static review confirms the release-event implementation is centralized and directionally correct: strict level cursors remain intact, the monotonic epoch catches unsampled 0 -> N -> 0 cycles, and production speculative reservation release is exactly once and separate from DEMAND/physical accounting. However, the final regression test's unrelated-frontier assertion deterministically attempts r3 and then asserts that no request changed, so the final diff is not acceptance-ready.
verdict: REQUEST_CHANGES
