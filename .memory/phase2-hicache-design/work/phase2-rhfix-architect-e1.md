# Fix B Design Assumption vs Production RECOMPUTE Long Tail: Architectural Analysis

- status: **done**
- epoch: e1
- owner: architect
- task: Reconcile Fix B's design assumptions with production trace evidence; determine whether Fix B targets the correct root cause, and identify the true production slow-tail mechanism.

---

## Conclusion

**Fix B is targeting the wrong state machine path.** Its gate (`DEVICE_QUOTA_MAX_TIMEOUTS=2`, requiring 2+ T13 timeouts per episode) never fires in production because the production RECOMPUTE long tail is a **miss-driven wake-loop churn** (WAIT[DEVICE_QUOTA] -> RESTORING -> revoked:miss -> immediate re-WAIT, 13ms cycle), not a T13 timeout-driven loop. Fix B's gate is structurally incapable of intercepting the real pathology. The correct fix must target the miss-driven churn and the underlying capacity/headroom freeze.

---

## 1. Fix B Design Assumption vs Runtime Evidence

### 1.1 coder's design assumption (from code comments)

The code at `hicache_restore.py:173-197` and `scheduler.py:3160-3166, 4509-4522` states:

- The B-run pathology is a `WAIT[DEVICE_QUOTA] -> T13 timeout -> NONE (recompute) -> ADMISSION_DENY -> WAIT` loop.
- Fix B counts T13 timeouts per episode (`hicache_restore_device_quota_timeouts`).
- When `attempts >= DEVICE_QUOTA_MAX_TIMEOUTS (=2)`, the admission re-arm site refuses to re-enter `WAIT[DEVICE_QUOTA]`, forcing the request through the forward path (plain recompute when capacity frees).
- The episode counter resets on `restore_success` (a genuine forward step), so healthy chains are not starved.

### 1.2 Tester实测 trace evidence (cross 6 traces, authoritative)

From `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-rhfix-fixb-crosstest-tester-e1.md`:

| trace | max_timeouts_per_episode | total_timeouts | FixB_ENGAGED(>=2) |
|---|---|---|---|
| prod-RH-OFF (ab-a-off) | **1** | 12 | False |
| prod-RH-ON (ab-a-on) | **1** | 20 | False |
| runA-base-rhoff-20G | **1** | 4 | False |
| runB-opt-rhoff-20G | **1** | 3 | False |
| rhfix-bl-on (RHON-base) | **1** | 5 | False |
| rhfix-str-bl (RHON-base-30G) | **1** | 6 | False |

**Every trace has max_timeouts_per_episode = 1.** The Fix B gate (attempts >= 2) never triggers in any production or experimental trace.

### 1.3 Which narrative is correct?

- **coder's "B-run 9,102-miss WAIT->timeout->recompute->ADMISSION_DENY->WAIT loop"**: This describes a timeout-driven loop. The 9,102 figure comes from `restore_recompute cause=miss` (not timeout). The 20 timeouts are real but isolated single events. The "loop" is not a timeout loop -- it is a **miss loop**.
- **tester's "miss-driven fast wake-loop churn"**: Confirmed by trace evidence. Production slow requests have 0-1 timeouts, 2-40 misses, 2-65 dq_waits. The 13ms cycle is WAIT->RESTORING->revoked:miss->re-WAIT.

**Verdict (confirmed):** The tester's narrative is correct. The coder's comment conflates `restore_recompute` (which includes both timeout and miss causes) with a timeout-driven loop. The 9,102 miss recomputes are the dominant path, not the 20 timeouts.

### 1.4 Is Fix B's gate the correct trigger condition?

**No.** The production pathology is:
- `revoked:miss` (extent thrash invalidates restored keys) -> immediate re-WAIT[DEVICE_QUOTA]
- `WAIT_CAPACITY reason=DEVICE_QUOTA` -> host capacity still full, headroom frozen
- The request never hits T13 timeout (or hits it at most once per episode) because the cycle is too fast (13ms)

Fix B's gate requires `attempts >= 2` T13 timeouts per episode. Since production episodes have at most 1 timeout, the gate is structurally incapable of firing. Fix B is a solution in search of a problem that does not exist in production.

---

## 2. Production Slow Tail True Root Cause

### 2.1 Why device-hit requests still enter WAIT[DEVICE_QUOTA]

The capacity charge path (`scheduler.py:3728-3736`):

```python
charge = device_charge(
    len(req.full_untruncated_fill_ids),
    len(req.prefix_indices),
    max_new,
    self.page_size,
)
return charge < available_and_evictable_tokens(
    self.req_to_token_pool, self.tree_cache
)
```

Even when a request has a device hit (device_value is present), the admission gate (`_restore_wait_capacity_fits`) still evaluates `charge < available_and_evictable_tokens`. When the device pool is fully allocated (working set = pool size), `available_and_evictable_tokens` is near zero, and every new admission attempt fails regardless of whether the request has existing device state. The request then enters `WAIT[DEVICE_QUOTA]` (T6 path at `scheduler.py:4501-4529`).

The `_restore_potential_for` gate (`scheduler.py:4502`) checks `has_restore_potential`, which returns True if:
- `host_hit_length > 0` (host material exists), OR
- the request has an in-flight or registered restore intent, OR
- the anchor chain is L3-queryable

So a request that already has device material can still pass `_restore_potential_for` and enter the WAIT re-arm cycle, because the host-side staging or L3 anchor still exists.

**Key insight:** The WAIT[DEVICE_QUOTA] loop is not about "no device hit" -- it is about `available_and_evictable_tokens` being zero due to the full working set, combined with `_restore_potential_for` still being True (host material or L3 anchor exists). The admission gate rejects with NO_TOKEN, and the request re-enters WAIT[DEVICE_QUOTA].

### 2.2 Why recompute体量 is so large (12K-30K tokens)

The recompute体量 equals the full prompt + generation length that was backed up to L3. In the production trace, the slowest request (`6b675ea9`) had `new=20557, dev=9, stor=22948`. The 20K+ token recompute is the full KV chain being recomputed from scratch because the L3 restore failed (miss/revoked). This is not a bug in the recompute path itself -- it is the consequence of the WAIT loop repeatedly failing to restore, eventually timing out or hitting admission deny, and falling through to full recompute.

The recompute体量 is a symptom, not a cause. The cause is the repeated restore failure (miss due to extent thrash invalidating keys, or admission deny due to device quota).

### 2.3 Wake-loop churn trigger mechanism (13ms cycle)

The 13ms cycle is:
1. Request is in `WAIT[DEVICE_QUOTA]` (host capacity full, headroom frozen)
2. Per-pass capacity wake predicate (`_restore_wait_capacity_fits`) checks `available_and_evictable_tokens > charge` -- fails because working set = pool
3. T11/T12 wakes do not fire (capacity never fits)
4. Request stays in WAIT
5. On the next pass, the scheduler re-evaluates `_restore_potential_for` -- still True (host material or L3 anchor exists)
6. Admission gate rejects again (NO_TOKEN) -> `RestoreEvent.ADMISSION_DENY` -> back to WAIT[DEVICE_QUOTA]
7. The T13 clock is already armed from the first WAIT entry; if 60s elapses, T13 fires -> `ADMIT_RECOMPUTE` -> recompute

But in the fast churn path, T13 does NOT fire (or fires only once). Instead, the `revoked:miss` path (from extent thrash) or the `ADMISSION_DENY` path (from device quota) keeps the request cycling through WAIT->RESTORING->WAIT at the per-pass rate (13ms). The T13 timeout is a rare escape valve (20 times total across 6 traces), not the main loop driver.

The root cause of the churn is: **host headroom is frozen** (Fix A's target state), so `_restore_wait_capacity_fits` always fails, and the request never progresses past WAIT[DEVICE_QUOTA].

---

## 3. Fix A/B Architecture裁决

### 3.1 Fix B: 重设计 or 废弃?

**Fix B should be re-designed or abandoned as currently specified.**

- The gate (`DEVICE_QUOTA_MAX_TIMEOUTS=2`) never fires in production (max=1 across all 6 traces).
- The target path (2+ timeout WAIT->recompute->re-WAIT loop) does not exist in production. The real loop is miss-driven (WAIT->RESTORING->revoked:miss->re-WAIT), which is a capacity/headroom problem, not a timeout problem.
- Even if the gate were lowered to `MAX_TIMEOUTS=1`, it would only intercept the rare T13 timeout path, not the dominant miss-driven churn path.

**If Fix B is to be retained**, the gate must be re-targeted:
- The gate should detect the miss-driven churn pattern (e.g., consecutive `revoked:miss` or `ADMISSION_DENY` events within an episode, not T13 timeouts).
- Alternatively, Fix B should target the `WAIT[DEVICE_QUOTA]` exit directly: after N consecutive WAIT entries without a genuine forward step (READY/restore_success), force the request through the recompute forward path.

### 3.2 Fix A (host_release epoch 唤醒): 独立价值评估

Fix A's mechanism (monotonic `host_release` epoch, NO_HEADROOM waiter subscribes to this epoch) was **not exercised in the cross-validation traces**:

- The tester cross-validation (RH OFF, 6 traces) did not enable `--enable-ready-horizon` (RH OFF). Fix A is a Ready Horizon feature (requires RH ON).
- The tester's stress run (`str-fx2`, RH ON, fixed code) crashed with `assert device_value is not None` before Fix A's epoch-wake mechanism could be observed.
- The tester's clean-disk RH ON runs (`fx2-on`, `bl2-on`) showed no freeze, so Fix A's value cannot be isolated from the baseline in those runs.

**Fix A's independent value remains unproven in production traces.** Its design is sound (monotonic epoch avoids the transient-available-level flip-flop that causes the e7 spin), but it needs:
1. A production RH ON trace with headroom pressure to observe the NO_HEADROOM -> host_release -> epoch advance -> waiter wake -> progress chain.
2. A matching baseline (RH ON, unfixed) to confirm the freeze is absent with Fix A.

### 3.3 Production Slow Tail: 最小修复面

The production slow tail has two distinct mechanisms:

**A. Host headroom freeze (Fix A target):**
- `hicache_host_used_tokens = 97,370 / total = 98,305` (near-full)
- `_ready_host_headroom = available + ready_resident ≈ 0`
- `headroom_fits` gate fails for all speculative staging
- `NO_HEADROOM` park never clears (available level flips 0->100->0, never sustains past the decline cursor)
- Fix A's monotonic `host_release` epoch is the correct mechanism to break this freeze.

**B. Extent thrash + revoked:miss (filesystem GC / capacity churn):**
- Extent slots are repeatedly dropped and reused (thrash), invalidating restored keys
- `revoked:miss` causes immediate re-WAIT, adding to the churn
- This is the filesystem min_free/extent GC issue (already recorded as an independent defect)
- Fixing this requires either: (a) eliminating the thrash (better extent allocation), or (b) making the WAIT loop resilient to key invalidation (cache the restored data in host memory instead of re-restoring from L3 each time)

**Minimum fix recommendation:** Fix A (host_release epoch) is the highest-leverage fix for the production slow tail because it addresses the headroom freeze that gates all progress. Fix B should be re-designed or abandoned; the miss-driven churn will persist even with Fix B because the gate never fires. The filesystem GC thrash is a separate concern (independent defect).

---

## 4. Independent Defect Archive Confirmation

The defect `filesystem min_free/extent GC -> restore-key invalidation + recompute storm` remains **independent and should not be mixed with the Fix A/B work**.

Evidence from this analysis:
- The `revoked:miss` path (extent thrash invalidating restored keys) is a downstream symptom of the filesystem GC / extent churn.
- The production slow tail is primarily driven by the host headroom freeze (Fix A target), not by the extent thrash alone.
- The extent thrash amplifies the slow tail (more misses -> more recompute -> more WAIT cycles) but is not the root cause of the freeze.
- The `build_backup_spec assert device_value is not None` crash (str-fx2) is a separate backup path defect, also recorded independently.

**Recommendation:** Maintain the independent defect record. Do not mix filesystem GC fixes with Fix A/B.

---

## 5. Open Issues

1. **Fix A production validation needed:** Fix A's epoch-wake mechanism has not been observed in any production trace. A production RH ON trace with headroom pressure is required to confirm Fix A breaks the freeze.
2. **Fix B redesign required:** If Fix B is to be retained, the gate must be re-targeted from T13 timeout count to miss-driven churn pattern (e.g., consecutive ADMISSION_DENY or revoked:miss events per episode).
3. **Filesystem GC thrash:** The independent defect remains. Its interaction with the slow tail (amplification factor) is not yet quantified.
4. **`build_backup_spec` assert crash:** The str-fx2 crash is a separate backup path defect. Whether it is pre-existing or exposed by Fix A/B control-flow changes is undetermined (the crash is in `unified_tree_core.py`, not in patched code, but the crash only appears in the fixed code's capacity-exhaustion path).
5. **RH ON + clean disk baseline:** The tester's clean-disk RH ON runs showed no freeze, meaning the original B freeze requires either disk pressure or a specific capacity-exhaustion pattern not yet isolated.

---

## 6. Evidence Sources

- Tester cross-validation: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-rhfix-fixb-crosstest-tester-e1.md`
- Tester stress report: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-rhfix-tester-e1.md`
- Forensics report: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-rhono-forensics-tester-e1.md`
- Fix B code: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/hicache_restore.py:173-197`
- Fix B gate in scheduler: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:3160-3172, 4509-4529`
- Fix A code: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py:27-44, 277-340, 402-477`
- Capacity wake predicate: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:3672-3736`
- Admission deny path: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:4491-4530`
- `build_backup_spec` assert: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2030-2037`
