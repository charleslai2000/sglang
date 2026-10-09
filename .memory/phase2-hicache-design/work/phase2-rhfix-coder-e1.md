# phase2-rhfix-coder-e1 — HiCache Ready Horizon Fix A/B + telemetry hygiene

> Implementer: coder agent, epoch 1
> Date: 2026-09-06
> Repo / branch / baseline: `sglang-3090-24g-opt` @ `3090-24g-opt`, from `fac8ccb4cf`
> (dispatch ruling: work in the existing opt worktree, main branch, no push, frozen baseline untouched)

## status: done

All three deliverables implemented, unit-verified at HEAD, committed separately, working
tree clean. Push NOT performed (not authorized).

## artifacts

Commits (on top of `fac8ccb4cf`, frozen baseline untouched):

1. `036fb89451` — **telemetry hygiene** (1 file)
   - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: single-key
     `set()` now calls `_log_extent_write("kv", None, [storage_key], [value])` on success,
     matching `batch_set` / `batch_set_v1` / `batch_set_v2` (telemetry parity).
2. `e0e83b11a1` — **Fix A** (3 files)
   - `python/sglang/srt/managers/scheduler_components/ready_horizon.py`
   - `python/sglang/srt/managers/scheduler.py` (A-hunks only)
   - `3090-dev/test_ready_horizon_unit.py`
3. `3bca0989f4` — **Fix B** (4 files)
   - `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
   - `python/sglang/srt/managers/schedule_batch.py`
   - `python/sglang/srt/managers/scheduler.py` (B-hunks only)
   - `3090-dev/test_hicache_restore.py`

## evidence

### Fix A: NO_HEADROOM waiter wakes on resource-release epoch; no permanent freeze

Design: NO_HEADROOM now subscribes to a NEW monotonic `host_release` causal epoch
(fifth), not the transient `host_headroom` level. The scheduler bumps `host_release`
each time the epoch snapshot observes `pool.available_size()` GREW since the last pass
(`_ready_horizon_epochs`, scheduler.py ~3508). By construction a growth is a genuine
capacity-releasing event (host residency freed / ready eviction / working-state
release); the refill's own traffic only ever lowers the level, so it cannot self-trigger.
The release counter never recedes when the working set re-consumes freed pages — the
B-run permanent-freeze root cause was the level `0→100→0` flip that could never sustain
past the decline cursor. `epoch_event` also fires on a `host_release` advance so a
release at a flat level re-runs the refill check. The 1s `SAFETY_FUSE_S` doubles as the
re-probe debounce (requirement f: repeated wakeup bounded).

Consistency: module docstring / `subscribed_epoch` / `entry_cleared` / `epoch_event` /
`policy_epoch_value` / `init_ready_horizon` + `_ready_horizon_epochs` all updated.

### Fix B: DEVICE_QUOTA bounded degradation; forward progress; no WAIT/recompute/WAIT

Design: the state machine's T13 row already degrades to `ADMIT_RECOMPUTE` (it cannot
itself produce a WAIT/recompute/WAIT cycle). The observed loop was the ADMISSION-DENY
re-arm re-entering `WAIT[DEVICE_QUOTA]` after each timeout. Fix B adds a per-episode
timeout counter (`Req.hicache_restore_device_quota_timeouts`, incremented in the T13
handler for DEVICE_QUOTA waiters), an explicit bound `DEVICE_QUOTA_MAX_TIMEOUTS = 2`
with `device_quota_degraded()`, and a gate at the admission re-arm site: once the cap is
reached, the re-arm is refused and the request proceeds as a plain recompute when
capacity frees (forward path). The counter resets on a genuine restore hit
(restore_success), so a healthy chain needing several capacity waits across its life is
not starved. Correctness preserved: we never admit into a full pool — we stop choosing
to WAIT instead of recomputing (the no-progress the cap exists to break).

### Tests run (all at HEAD, working tree clean)

Target tests added:
- `test_ready_horizon_unit.py` (Fix A): `test_no_headroom_cleared_only_by_host_release`,
  `test_no_headroom_not_cleared_by_level_only_when_release_stalls`,
  `test_host_release_counter_advance_is_event`,
  `test_host_release_counter_stall_releases_only_once`,
  `test_no_headroom_park_wakes_on_release_epoch_not_level` (pass-level end-to-end),
  `test_release_counter_monotonic_survives_reconsumption` (pass-level monotonicity).
- `test_hicache_restore.py` (Fix B): `DeviceQuotaBoundedDegradationTests` (5 tests:
  timeout→ADMIT_RECOMPUTE never WAIT; below-cap allowed; at-cap refused; cap finite;
  full lap sequence stops after exactly `DEVICE_QUOTA_MAX_TIMEOUTS`).

Full relevant suite at HEAD:

```
PYTHONPATH=<repo>/python /home/charles/sglang-venv/bin/python -m pytest \
  3090-dev/test_hicache_restore.py \
  3090-dev/test_ready_horizon_unit.py \
  3090-dev/test_hicache_restore_scheduler_feed.py \
  3090-dev/test_ready_horizon_partition.py \
  3090-dev/test_writeback_reserve_unit.py \
  3090-dev/test_capacity_model_unit.py \
  3090-dev/test_prefetch_budget_split_unit.py \
  3090-dev/test_drain_reentry.py \
  3090-dev/test_fbe_flush_before_evict.py \
  3090-dev/test_storage_regression.py \
  -q
=> 346 passed, 23 warnings
```

Target subset only: `14 passed, 120 deselected`.
Note: torch emits sm_61 CUDA-unsupported warnings on this box (GT 1030); all tests pass
(cpu-only state-machine paths).

## summary

- Fix A: speculative stage can no longer enter a permanent NO_HEADROOM freeze; the
  NO_HEADROOM waiter subscribes to the monotonic host_release epoch, wakes on genuine
  capacity-releasing events, is debounced by the safety fuse, and speculative staging
  still never evicts / never encroaches on working-set reserve (M2 headroom gate
  unchanged).
- Fix B: DEVICE_QUOTA waits are bounded per episode; after the cap, the admission
  re-arm is refused and the request takes the recompute forward path — the
  `WAIT → timeout → recompute → ADMISSION_DENY → WAIT` loop is broken without faking
  success on working-set exhaustion and without depending on thrash-invalidated L3.
- Telemetry: single-key `set()` is metered like all batch paths.
- Three independent commits with clear messages; no push; frozen baseline commits and
  the main-branch history before `036fb89451` untouched.

## followups

- Integration / GPU A-B / 2h soak verification belongs to tester (out of coder scope).
- Consider a follow-up unit that exercises the scheduler-side Fix B gate via
  `test_hicache_restore_scheduler_feed.py`-style feeding once integration confirms the
  B-run loop shape (current gate coverage is via the pure helper + pass-level tests).

## open_issues

- None at coder/unit level. The `host_release` counter's ground-truth is
  `available_size()` growth observed by the epoch snapshot (per-pass); it is monotonic
  by construction but is bounded in practice by how often a release's level rise is
  observed before re-consumption — under a full working set this still yields one
  probe per release, which the fuse additionally bounds (requirement f). If tester's A/B
  ever shows the counter saturating, the counter source can be swapped without touching
  the subscription semantics.