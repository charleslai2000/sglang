# Deep Review Gate: HOST_ALLOC allocability epoch

## Dispatch and revision

- Task ID: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer-deep`
- Branch: `3060-12g-qwen35-4b`
- Reviewed revision: `37cdf219e29aa61dca6ba19023f547c72153e076`
- Scope: read-only review of the target repository; this report is the only
  artifact written.
- Invocation status: `done`
- Verdict: `REJECT`
- Expert Gate: not signaled; the blocking findings are directly evidenced.

The full seven-file commit diff, authoritative architecture/intake/novelty
artifacts, coder/debug/test reports, and prior gates were reviewed. No product
code, remote host, storage, or 3090 state was modified.

## Blocking findings

### F-01 — P1 — HOST_ALLOC can still complete a positive hit through an arbitrary crop

`UnifiedRadixCache._try_alloc_storage_hit` still falls through from failed full
allocation/reclaim to a smaller page-aligned allocation at
`python/sglang/srt/mem_cache/unified_radix_cache.py:6140-6159`. For a KV-only
operation, `_storage_hit_crop_is_safe` returns true, `alloc_len` is lowered to
the currently available capacity, and `operation.storage_hit_count` is mutated
to that shorter span.

This contradicts the authoritative contract's full-span-only retry
(`ARCH-20260909-HOST-ALLOC-EPOCH.md`, sections 5.1, 5.4, 5.5, and 6): one
normal `alloc(full) -> evict -> alloc(full)` attempt must either complete the
validated span or report non-miss `HOST_ALLOC`. The Mamba trailing-sidecar guard
prevents this specific crop in the target Qwen3.5 hybrid case, but the retained
KV-only path still violates the required full-span/KV-only compatibility
contract and is covered by the requested adversarial check.

Disposition: reject until the HOST_ALLOC/full positive-hit path cannot lower the
frontier; preserve genuine miss classification separately.

### F-02 — P1 — Auxiliary rollback frees do not advance the auxiliary generation

`HostPoolGroup.resolve_host_transfers` rolls back already allocated side-pool
slots on a later auxiliary allocation failure (`python/sglang/srt/mem_cache/pool_host/group.py:161-185`).
The candidate's controller callback in
`hybrid_cache_controller.py:566-577` reports only the primary `kv` free.
Therefore a sequence such as KV allocation, successful Mamba allocation, then a
later auxiliary failure frees Mamba capacity without incrementing the Mamba
generation. A waiter blocked on Mamba requires a newer Mamba generation, so the
KV-only callback cannot wake it; it can remain parked until T13 even though its
blocked auxiliary pool changed.

The same asymmetry is visible in the retraction path at
`unified_radix_cache.py:3879-3889`, where `resolve_host_transfers` may roll back
auxiliary allocations but the caller bumps only KV. The target Mamba backup path
reaches `HybridCacheController.write` through
`unified_radix_cache.py:4053-4056`.

Disposition: reject until rollback/free notification is per pool (or is emitted
by the owning pool-group boundary) and a hybrid regression proves that a KV
generation cannot satisfy an Mamba-blocked cursor.

### F-03 — P1 — Lock-release generation bumps produce logging exceptions

`_bump_changed_host_allocability` calls `_bump_host_allocability` without a
`returned_units` argument (`unified_radix_cache.py:3645-3658`). The callee then
formats that default `None` with `%d` (`unified_radix_cache.py:3630-3643`).
Every effective lock-release-to-evictable transition therefore increments the
generation but emits a Python `--- Logging error ---` and
`TypeError: %d format: a real number is required, not NoneType`.

Reproduction used the dependency-free harness with a minimal cache object. The
observed output included the logging traceback at line 3630 and ended with
`generation 1`. This is not merely cosmetic: it violates the observational
telemetry/no-log-flood requirement and can discard the required change record
under ordinary host-lock churn.

Disposition: reject until lock-release telemetry accepts an explicit nullable
unit representation or supplies a valid count, with a configured-handler test.

## Additional confirmed defects and gate deficiencies

### F-04 — P2 — Direct cancellation/timeout cleanup leaves stale FIFO entries

The direct queue-removal paths `_abort_on_queued_limit`,
`_abort_on_waiting_timeout`, and `abort_request` remove requests and release
cache state (`scheduler.py:4422-4424`, `4453-4470`, `6379-6384`) but do not call
`HostAllocWakeArbiter.remove`. `_reconcile_restore_states` returns immediately
when the waiting queue is empty (`scheduler.py:3291-3299`), so an idle scheduler
does not prune those RIDs. The later selector eventually removes stale entries,
but cancellation/timeout cleanup is not immediate and can retain unbounded stale
FIFO metadata during idle periods.

Disposition: fix all direct removal paths or centralize removal; add cancellation
and timeout cleanup assertions. This is non-blocking relative to F-01--F-03 but
violates the explicit cursor cleanup contract.

### F-05 — P1 — Existing dependency-free harness regresses on the new operation-field assumption

The new alloc-failure metadata path unconditionally reads
`operation.pool_transfers` at `unified_radix_cache.py:6035`. The maintained
dependency-free fixtures use the documented duck-typed operation shape without
that optional field. Both of these tests now error with
`AttributeError: 'types.SimpleNamespace' object has no attribute 'pool_transfers'`:

- `3090-dev/test_drain_reentry.py:1021-1050`
- `3090-dev/test_hicache_restore.py:973-988`

Production `CacheOperation` does define the field, so this finding is an
interface/test-compatibility regression rather than proof that every production
operation lacks it. It nevertheless blocks acceptance because the available
focused regression corpus no longer executes the alloc-failure and flag-off
paths.

Disposition: preserve the optional-operation compatibility or update the
authoritative harness together with the implementation, then rerun the affected
tests.

### F-06 — P2 — Telemetry does not implement the authoritative schema

The architecture requires schema/version, monotonic and wall timestamps,
worker/rank, causal RID/trace context, current/captured generations, wait
deadline, and the per-pool allocation/reclaim fields. The candidate's plain
`logger.info` records at `unified_radix_cache.py:3630-3643` and
`scheduler.py:3207-3250` / `3387-3398` omit multiple required fields and do not
emit a stable schema record. No secret leakage was found, and telemetry is not
used as fit authority, but the required observational contract is incomplete.

Disposition: complete the schema or explicitly revise the authoritative gate
before acceptance.

## Checks that passed or were not falsified

- Cache generation state is cache-owned, uses a monotonic Python integer, and
  includes a reset instance identity check in the scheduler cursor.
- Reservation release itself does not bump generations; generic scheduler passes
  and the legacy paced miss marker are not used as HOST_ALLOC wake sources.
- The HOST_ALLOC capacity predicate no longer requires `available_size >= full`
  before invoking the authoritative allocation path.
- `revoked_alloc_failed` is mapped to non-miss `DENIED_ALLOC`; the reviewed code
  does not arm genuine-miss evidence for that terminal.
- Mamba/SWA trailing-sidecar crop protection and all-or-nothing hybrid finalization
  are present. The concern in F-01 is the remaining KV-only lower-frontier path,
  not evidence that Mamba trailing pages are currently cropped.
- No evidence was found that telemetry controls fit, wake, hit, or success.

## Plausible risks not used as the verdict

- The generation state has no explicit lock. The source comments and current
  reconciliation model claim scheduler-thread ownership, so this is not a
  confirmed defect; it becomes a blocking issue if controller/free callbacks can
  execute concurrently with scheduler snapshot reads.
- No post-fix live 3060 run was available. The prior live trace is useful for
  reproducing the original liveness gap but cannot validate this revision's
  runtime integration, distributed rank behavior, or log volume.

## Unsupported concerns explicitly not counted

- There is no evidence that KV-only generation currently satisfies an
  Mamba-blocked cursor; the source predicate requires every blocked domain to
  advance. F-02 is instead the separate confirmed omission of the Mamba bump
  during rollback.
- There is no evidence of secret leakage in the new telemetry fields.
- There is no evidence that genuine L3 misses are mapped to `HOST_ALLOC`; the
  reviewed terminal mapping preserves the miss path. The retained KV-only crop
  is a full-span violation, not a miss-classification finding.

## Executed evidence

| Check | Result |
| --- | --- |
| `git rev-parse HEAD` and full diff/stat | PASS; revision matched the dispatch; 7 files, 803 insertions, 20 deletions |
| `git diff --check HEAD^ HEAD` | PASS |
| Dependency-free `py_compile` for all seven changed Python files | PASS |
| Pure `HostAllocWakeArbiter` FIFO/vector smoke | PASS |
| Lock-release telemetry reproduction | FAIL as F-03; generation advanced but logging raised the `%d`/`None` traceback |
| `PYTHONPATH=python:test python3 -m unittest registered.unit.managers.test_hicache_host_allocability -v` | BLOCKED at collection by missing `orjson` |
| `3090-dev/test_hicache_restore.py` | 92 tests; 91 passed, 1 error from the new `pool_transfers` assumption |
| `3090-dev/test_drain_reentry.py` | 31 tests; 13 errors. Several are stale harness surfaces, including the direct new `pool_transfers` failure and new `_storage_prefetch_failures` fixture initialization gap. |
| `3090-dev/test_hicache_restore_scheduler_feed.py` with `PYTHONPATH=python` | BLOCKED at collection by missing `orjson` |
| Focused registered test under real dependencies | Not executable: `orjson`, pytest, and torch are unavailable |

No live post-fix 3060 run was available in the authorized read-only scope. The
prior live evidence remains pre-fix and cannot establish acceptance of this
revision.

## Open issues and follow-ups

1. Correct F-01 through F-03 before requesting another gate review; F-04 through
   F-06 should be resolved or explicitly adjudicated.
2. Install/restore the repository's declared test dependencies under a fresh
   Task ID, then run the full focused scheduler/cache suite and hybrid rollback
   matrix.
3. Obtain separately authorized live 3060 evidence for unlock-to-evictable,
   queued KV release, queued Mamba release, KV-only, Ready Horizon OFF, timeout,
   cancellation, and repeated failed-grant fairness cases.

Final disposition: `REJECT`.
