# phase2-fixb-strip — coder e1

status: done

## Summary
Stripped the Fix B DEVICE_QUOTA timeout-count control logic from the production path as an independent cleanup commit on top of HEAD (30a5a3698a), per the user's final option B: production carries only the P1 structural epoch/generation re-arm gate, not the falsified timeout-count budget. History untouched; original P1 `74246bb90f` left as-is.

## Deliverable 1 — cleanup commit hash + precise diff
Commit: **`3c71553a20`** `revert(hiscache): strip Fix B DEVICE_QUOTA timeout-count gate from production path`
Parent: 30a5a3698a. Local only, not pushed. 5 files, +5/-135.

**Production control-flow stripped (exactly the dispatched scope):**
- `python/sglang/srt/managers/scheduler.py`:
  - :228 removed `device_quota_degraded,` import
  - T13 timeout handler: removed `if req.hicache_restore_wait_reason is DEVICE_QUOTA: ...timeouts += 1` accumulation
  - restore_success handler: removed `req.hicache_restore_device_quota_timeouts = 0` reset
  - T6 branch: removed the `if not device_quota_degraded(...)` wrapper; `_apply_restore_event(ADMISSION_DENY, rearm_allowed=miss_rearm)` now applied unconditionally, gated only by `miss_rearm_allowed`
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`: removed `DEVICE_QUOTA_MAX_TIMEOUTS = 2` and `device_quota_degraded()` (+ docstring)
- `python/sglang/srt/managers/schedule_batch.py`: removed `self.hicache_restore_device_quota_timeouts: int = 0` field

**Tests:**
- `3090-dev/test_hicache_restore.py`: deleted `DeviceQuotaBoundedDegradationTests` class (5 tests testing falsified Fix B logic); removed `DEVICE_QUOTA_MAX_TIMEOUTS` and `device_quota_degraded` imports
- `3090-dev/test_hicache_restore_scheduler_feed.py`: removed both `hicache_restore_device_quota_timeouts=0` field constructions

## Deliverable 2 — T6 branch final form (epoch gate alone)
`python/sglang/srt/managers/scheduler.py` (~4547): on NO_TOKEN with restore material, the branch now does only:
```python
miss_rearm = miss_rearm_allowed(
    req.hicache_restore_miss_epoch,
    self.tree_cache.l3_publish_epoch(),
    req.hicache_restore_miss_generation,
    getattr(req, "session_generation", None),
)
self._apply_restore_event(req, RestoreEvent.ADMISSION_DENY, rearm_allowed=miss_rearm)
```
Semantics unchanged for the P1 cases:
- MISS_RECOMPUTE + epoch unchanged + generation matches -> miss_rearm=False -> ADMISSION_DENY refuses re-WAIT -> forward recompute
- epoch advanced or generation changed -> miss_rearm=True -> re-arm into WAIT[DEVICE_QUOTA]

## Deliverable 3 — unit test results (post-strip)
Run: `PYTHONPATH=<repo>/python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py`

- `test_hicache_restore.py` + `test_hicache_restore_scheduler_feed.py`: **95 passed** (16 warnings)
- `test_ready_horizon_partition.py` + `test_ready_horizon_unit.py` + `test_storage_regression.py` + `test_p3_warmtree_hol.py` + `test_prefetch_budget_split_unit.py`: **215 passed** (23 warnings)
- `test_drain_reentry.py` + `test_writeback_reserve_unit.py` + `test_backup_spec_assert_fix.py` + `test_fbe_flush_before_evict.py` + `test_capacity_model_unit.py`: **64 passed, 5 failed** — the 5 failures are all in `test_drain_reentry.py` (`_FakeTreeCore` missing `get_component_devi...`), a mock-attribute error in a file untouched by this task. Verified identical 5 failures on a clean HEAD worktree (30a5a3698a) -> **pre-existing, out of scope**.

P1 miss-epoch gate tests confirmed present and green: `test_miss_stays_sticky_across_admission_denies`, `test_miss_rearm_override_clears_sticky`, `test_miss_forward_ready_ends_sticky`, and the `StickyMissRearmGateTests` (no_miss_epoch / same_epoch_not_rearmable / epoch_advanced / generation_changed / generation_none_never_overrides / idempotent_across_repeats).

## Deliverable 4 — no leftover control-flow references (grep evidence)
Repo-wide (`python/` + `3090-dev/`):
- `device_quota_degraded` -> 0 hits (grep exit 1)
- `DEVICE_QUOTA_MAX_TIMEOUTS` -> 0 hits (grep exit 1)
- `hicache_restore_device_quota_timeouts` -> 0 hits (grep exit 1)

## Deliverable 5 — forward-progress argument (epoch gate alone)
After stripping the timeout-count budget, T6's forward-progress is carried solely by the P1 epoch/generation re-arm gate:

1. A request parked in MISS_RECOMPUTE (L3-prefix proven missing this episode) has its re-arm into WAIT[DEVICE_QUOTA] refused while the L3 publish epoch is unchanged and the generation matches. It therefore cannot re-enter the WAIT -> T13 timeout -> recompute -> ADMISSION_DENY -> WAIT loop for a prefix that is provably still missing: each ADMISSION_DENY with miss_rearm=False releases it as a plain recompute (the forward path), never re-parking. This is the same loop breaker the Fix B cap attempted, but driven by real negative evidence (a proven miss on an unchanged cache), not by a "N consecutive failures" heuristic.
2. When the cache genuinely changes — l3 publish epoch advances (a later publish may now really cover the prefix) or the session generation changes (identity differs, so prior negative evidence no longer applies) — the sticky miss clears, miss_rearm becomes True, and the request is allowed to re-enter WAIT[DEVICE_QUOTA]. This is exactly the re-armable path the Fix B counter could never model (it had no notion of cache-state change; it only counted timeouts).
3. Because re-arm only happens on a real epoch/generation change, and refusal releases to recompute (which is always a forward step), no timeout-count budget is needed: the gate is event-driven and self-correcting. Removing the cap cannot weaken forward progress — it removes a secondary budget that was orthogonal to (and could not distinguish) real cache change, which the epoch gate handles precisely.

Constraint check: no "N consecutive failures degradation" heuristic introduced. too_short (7155cd8973), P3 (30a5a3698a), P0, Fix A logic untouched. History not rewritten; P1 `74246bb90f` intact.

## Artifacts
- Cleanup commit `3c71553a20` (local, not pushed) on `3090-24g-opt`
- Modified files: python/sglang/srt/managers/scheduler.py, python/sglang/srt/managers/scheduler_components/hicache_restore.py, python/sglang/srt/managers/schedule_batch.py, 3090-dev/test_hicache_restore.py, 3090-dev/test_hicache_restore_scheduler_feed.py

## Evidence
- `git log --oneline -2` -> `3c71553a20` on `30a5a3698a`
- pytest: 95 passed (hicache restore pair), 215 passed (related suites); 5 pre-existing `test_drain_reentry.py` mock-attribute failures reproduced identically on clean HEAD worktree
- grep: 0 hits for device_quota_degraded / DEVICE_QUOTA_MAX_TIMEOUTS / hicache_restore_device_quota_timeouts in python/ + 3090-dev/

## Followups
- `test_drain_reentry.py` 5 failures are pre-existing and unrelated (mock missing `get_component_devi...`) — recommend a separate dispatch to fix the fake if in scope
- Downstream integration/production-candidate verification of the stripped control path -> tester

## Open issues
- None for this task
