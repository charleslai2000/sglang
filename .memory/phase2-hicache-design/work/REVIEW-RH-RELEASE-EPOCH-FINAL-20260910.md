status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
evidence:
- VERIFIED: The final product diff is limited to the six expected source/test files; unrelated untracked workspace material was not included in the reviewed diff. `git diff --check` passed.
- VERIFIED: `python3 -m py_compile` passed for all four modified product modules and both modified test files.
- VERIFIED: Dependency-light exact-once tests passed: four tests ran and passed for first SPECULATIVE release, duplicate release, missing reservation, and DEMAND release.
- VERIFIED: `UnifiedRadixCache.release_prefetch` is the sole owner of speculative release accounting. It returns before mutation for missing/already released reservations, removes the ownership record before accounting, decrements `inflight_speculative_tokens`, and increments `speculative_release_epoch` only for `PrefetchKind.SPECULATIVE`.
- VERIFIED: Static call-site audit found all inspected ongoing-prefetch removal paths route through `release_prefetch`: finalize, hybrid discard, abort, revoke, and detach. Demand reservations do not advance the release epoch.
- VERIFIED: Strict level semantics remain `current < entry.epoch_cursor`; release-event wake is a separate directional check (`current release epoch > entry.release_epoch_cursor`). A literal 0 -> 0 level transition without a release event remains non-causal.
- VERIFIED: Scheduler snapshots the controller release counter monotonically and records a release cursor only for SPEC_BUDGET parks. Physical occupancy, demand reservations, NO_L3, and NO_HEADROOM ownership remain separate.
- VERIFIED: The new ABA test uses production `reserve_prefetch`/`release_prefetch` for a complete 0 -> N -> 0 cycle and asserts the first wake. The reservation tests assert first-release +1, duplicate/no-reservation unchanged, and DEMAND unchanged.
- UNVERIFIED: Full Ready Horizon scheduler tests could not execute because the local interpreter lacks `orjson` (and the earlier report also records missing pytest/msgspec); live 3060 acceptance was not run.
summary:
Static review confirms the release epoch has centralized ownership, exactly-once speculative-only increments, strict current-versus-cursor level handling, and physical/demand separation. The production helper and all inspected cleanup routes are wired correctly. One acceptance-level stale/duplicate-event test gap remains, and the final gate should not be approved until it is closed and dependency-backed tests run.
findings:
[MEDIUM | HIGH CONFIDENCE] /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py:1181-1188
problem:
The asserted “no second issue” pass is vacuous rather than a duplicate-event test. After the first wake at fake time 10, the test immediately calls `_ready_horizon_pass()` again with the same frontier and unchanged epochs. `epoch_event` is false and the five-second safety interval is not elapsed, so `should_refill` returns before candidate eligibility or the stale negative entry is exercised. The test therefore does not prove that the already-consumed release event cannot cause another issue when a later unrelated event or safety reconciliation causes another pass.
evidence:
- `test_ready_horizon_unit.py:1177-1188` advances the clock only before the first wake, then performs the second pass immediately; it introduces neither a later causal event nor a safety-interval expiry.
- `scheduler.py:4666-4677` gates the immediate second pass out when the snapshot is unchanged and the safety interval is not due.
- `scheduler.py:4715-4720` reads any existing negative entry, while `scheduler.py:4774-4907` does not explicitly consume it after a successful mocked issue; `_park_ready_decline` assigns entries at `scheduler.py:4940-4953`.
- `ready_horizon.py:373-377` keeps an old SPEC_BUDGET entry cleared once the release epoch is above its old cursor. In the test, `r2` is deliberately left in `NONE`, so a later frontier event could make it eligible again without another release.
impact:
The test demonstrates only that the event gate suppresses an immediate no-event pass. It does not establish the requested stale/duplicate-event and one-release/one-attempt behavior under a later pass while the candidate remains otherwise eligible. In the real issue path a successful prefetch normally transitions the request to RESTORING, so this is primarily an acceptance-coverage gap; the test's mock intentionally removes that protection and must exercise the intended invariant explicitly.
recommended_correction:
Extend the real-path ABA test after the first wake by keeping the candidate otherwise eligible, trigger a later unrelated causal event (or advance the safety interval) without advancing `speculative_release_epoch`, and assert no second issue. If the intended contract is one attempt per release event even when a candidate remains in `NONE`, make the negative-entry lifecycle explicit (consume/refresh it after the successful attempt) and assert that lifecycle; otherwise adjust the test to model the production state transition and separately test stale-event rejection. Keep the existing immediate-pass assertion as a separate event-gate check.
confidence: high
open_issues:
- Focused Ready Horizon scheduler tests remain unexecuted due the missing `orjson`/pytest/msgspec dependency environment; the exact four reservation tests did pass.
- Live 3060 runtime acceptance and no-repeat behavior in a dependency-complete environment remain unverified.
- No separate product defect was established in release counter ownership, strict level comparison, speculative-only accounting, or inspected cleanup call-site routing.
verdict: REQUEST_CHANGES
