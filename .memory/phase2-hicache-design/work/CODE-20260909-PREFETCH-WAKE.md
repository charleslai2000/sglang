# CODE-20260909-PREFETCH-WAKE

```text
status: done
task_id: CODE-3060-PREFETCH-WAKE-20260909
orchestration_epoch: 20260909-p4-queue
role: coder
branch: 3060-12g-qwen35-4b
base_commit: 277dd611001c31edcd3a8894213c5a44b00e9bd4
commit: 7caa438f623b5acd3f5c05183d0b083d27b337f5
```

## Finding

The diagnosis is confirmed. `DENIED_RATE` maps to `WAIT_CAPACITY` with
`PREFETCH_BUDGET`. After the host prefetch limiter became clear,
`_restore_wait_capacity_fits` still applied the final device admission-charge
predicate. With another large request holding device KV capacity, this kept
the waiter parked even though its next operation was only L3-to-host staging.

## Change

In `python/sglang/srt/managers/scheduler.py`, a
`PREFETCH_BUDGET` wake now returns eligible immediately after the existing
physical host prefetch-budget check passes. The re-issued prefetch still uses
the existing host allocation and prefetch admission path. Device capacity is
still enforced by the existing admission path after the restore reaches
`READY`; `DEVICE_QUOTA` waiters continue through the device-charge predicate.

Added focused coverage in
`test/registered/unit/managers/test_hicache_restore_prefetch_budget.py` for:

- rate-denied waiter held by the host prefetch budget, then released and
  re-issued while device capacity remains unavailable;
- device-quota waiter remaining blocked without device capacity.

No reservation/release code was changed. Exact-once ownership remains in the
existing unified cache reservation paths.

## Verification

- `python3 -m py_compile` passed for `scheduler.py`,
  `unified_radix_cache.py`, `cache_controller.py`, and the focused test.
- `python3 3090-dev/test_hicache_restore.py RestoreStateMachineTests CapacityWakeApplicabilityTests`
  passed: 44 tests.
- `git diff --check` passed before commit.
- The new scheduler test could not execute in this environment because pytest
  is unavailable and the system Python lacks the scheduler dependency
  `orjson`.
- No fresh remote runtime run was performed; runtime PASS is not claimed.

## Open issues / followups

- Run the focused scheduler regression in the project test environment with
  SGLang dependencies installed.
- Run the requested fresh 3060 remote queue reproduction separately before
  claiming runtime PASS.
- Pre-existing untracked `review/gates/` and `storage/` paths in the 3060
  worktree were not modified or committed.
