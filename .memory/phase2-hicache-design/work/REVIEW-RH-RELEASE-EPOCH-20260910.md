status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
evidence:
- VERIFIED: `HiCacheController` initializes `speculative_release_epoch` at cache_controller.py:373-376. The counter is owned by the controller and is not conflated with either physical occupancy or speculative inflight level.
- VERIFIED: `UnifiedRadixCache.release_prefetch` is the single speculative reservation release helper at unified_radix_cache.py:5123-5144. It returns before mutation when no reservation exists, marks/removes the reservation before accounting, decrements `inflight_speculative_tokens`, and increments the release epoch only for `PrefetchKind.SPECULATIVE`. All inspected ongoing-prefetch removal paths route through this helper: finalize, hybrid discard, abort, revoke, and detach.
- VERIFIED: the level comparison remains strict at ready_horizon.py:369-377 (`cur < entry.epoch_cursor`); the new event signal is separate and directional (`current release epoch > parked cursor`). Thus 0 -> 0 without a release event does not clear a zero-cursor park.
- VERIFIED: Scheduler snapshots the controller event counter monotonically at scheduler.py:5019-5023 and includes it in both causal snapshots (scheduler.py:4803-4810 and 5028-5035). SPEC_BUDGET parks alone record `release_epoch_cursor` (scheduler.py:4940-4951); NO_L3/NO_HEADROOM and physical-only paths retain their existing ownership/separation.
- VERIFIED: `epoch_event` and `entry_cleared` consume the release event only as a SPEC_BUDGET wake signal (ready_horizon.py:369-377 and 568-576). Demand/physical reservations do not advance the event because the increment is guarded by `reservation.kind is SPECULATIVE`.
- VERIFIED: focused tests cover strict zero behavior and an unsampled level ABA shape (test_ready_horizon_unit.py:513-540 and 1106-1143), post-issue cursor capture (1066-1104), and physical-only non-parking (1145-1169). Existing reservation-path tests cover idempotent release and the five cleanup routes, but do not assert the new epoch value.
- VERIFIED: implementation report records `py_compile` and `git diff --check` success; dependency-backed pytest and live 3060 acceptance were not run.

summary:
Static review finds the release-epoch implementation semantically aligned with the original unsampled SPEC_BUDGET ABA defect. Ownership is centralized, speculative release increments are exactly-once in the helper, current level strictness is preserved, physical-only and demand accounting stay separate, and stale release events are consumed as monotonic causal events rather than as a level comparison. One acceptance-level test-scope gap remains, so the patch is not fully review-approved.

findings:
[MEDIUM | VERIFIED] test_ready_horizon_unit.py:1106-1143 and 3090-dev/test_prefetch_budget_split_unit.py:279-405
problem: The new end-to-end ABA test manually increments `cc.speculative_release_epoch` and verifies one issue after a release, but it does not exercise the real `UnifiedRadixCache.release_prefetch` helper for the new counter. It also does not run a subsequent pass with the candidate still eligible and no new release to prove that the same release event cannot cause a second issue. The existing exactly-once reservation tests verify the speculative level returns to zero and the reservation map is emptied, but never assert release-epoch `+1` on first release and unchanged on duplicate/demand release.
evidence: test_ready_horizon_unit.py:1135-1143 mutates the fixture level and epoch directly, while test_prefetch_budget_split_unit.py:292-311 checks only counters/map state after duplicate and DEMAND releases. The production helper at unified_radix_cache.py:5135-5144 is the code that actually provides exactly-once epoch semantics.
impact: A future regression could leave the level/cursor tests green while incrementing the event on a duplicate, incrementing it for DEMAND, or failing to increment it in one terminal path; the wake test would not detect it. A future repeated pass could also retrigger if entry/state handling changes, because no assertion currently isolates the one-event/one-attempt contract.
recommended_correction: Add a source-backed reservation test that calls `reserve_prefetch` + `release_prefetch` twice and asserts the release epoch changes exactly once, and a DEMAND counterpart asserting no change. Extend the ABA scheduler test (or a dedicated policy/pass test) to perform a second pass after the first wake with no new release and assert no second RH issue, while keeping the candidate otherwise eligible.
confidence: high

open_issues:
- Focused pytest could not be executed in the reported shell because pytest/msgspec were unavailable; only static source review and the reported compile checks are available.
- The live 3060 blocker+A/B trace remains unverified; this review does not claim runtime RH acceptance or performance improvement.
- No additional product defect was established within the requested release-epoch scope.

verdict: REQUEST_CHANGES
