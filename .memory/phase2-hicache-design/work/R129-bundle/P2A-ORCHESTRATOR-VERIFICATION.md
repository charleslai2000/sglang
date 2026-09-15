# P2-A R129 — orchestrator independent verification + verdict

- task_id: `P2A-COLLECTION-20260912` (verification of R129)
- epoch: 2026-09-12
- tester report verified: `work/P2A-LIVE-COLLECTION-20260912-R129.md` sha256
  `f3e32ee54138e47ecf210fc02ea0d04826509a0de9f1841e2174e170526db17a` —
  **ACCURATE** (independently re-derived; see deltas below).
- build: R128 freeze (`work/R128-profile/…`), probe `SGLANG_P2A_TIMING_PROBE=1`.
- raw window independently hashed:
  `/mnt/data/nerun-dev/r129/window-36294-597400.log` sha256
  `a19fed9298341d69430308f24352390edee1d51b97b322d06032dc308b938132` (matches).

## Independent re-derivation (from the raw window, not the report's tables)

**Q3 — 27 `evt=storage_hit_query` records re-parsed:**
- `span = exit-enter`: min 12.418 s, p50 **17.777 s**, p95 20.847 s, max 22.613 s.
- `backend_lookup_ns`: min 12.416 s, p50 **17.773 s**, p95 20.839 s, max 22.610 s.
- `backend_lookup/span` ratio 99.93–100.00 % for every record.
- 0 negative spans, 0 records with `backend_lookup > span`, all `caller=async_prefetch`
  (`sync_decode`=0). 2 metadata HITS / 25 misses — the 2 hits still took
  15.345 s and 17.777 s. Matches the report.

**Q1 — 27 joinable `enqueue_mono_ns` ∩ `admission.v2` pairs (59 enqueue / 27 admission):**
- my percentiles: min 0.040 s, p50 1.694 s, p95 22.653 s, p99 37.588 s, max 40.667 s.
- (report: p95 33.108 / p99 39.866 — percentile-method difference only; sample
  count and p50/max agree.) 0 negatives.

**Q2 — 1 completed same-attempt pair** (`r129-s0-t2-081155:prefetch:2`,
`DEMAND_RETRY`): 16.567 s. 26 issue-without-`ready_host` attempts (not imputed).
Consistent with the report.

## ROOT-CAUSE MECHANISM (confirmed in source; strengthens the tester's verdict)

`SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE` defaults to **False**
(`environ.py:697`) and the frozen `launch-r112.sh` does not set it, so
`HiCacheFile` builds with `metadata_cache=None` (`hicache_storage.py:423`).
Then `_collect_existing_component_keys` (`hicache_storage.py:581-606`) takes the
`metadata_cache is None` branch:

```python
with os.scandir(self.file_path) as entries:      # L3 dir = 3,090,193 files
    for entry in entries:
        if entry.is_file() and entry.name in target_files:
            existing_files.add(entry.name)
```

i.e. a **full directory scan of the entire 3.09M-file L3 directory on every
storage query**, plus `entry.is_file()` per entry. That is the ~12–23 s cost.
The metadata-cache branch (otherwise taken) would use `metadata_cache.contains`
+ `os.path.exists` per key and skip the scan.

**Throughput corroboration:** 27 queries × 17.777 s ≈ 480 s spent inside the
single prefetch thread vs the 514 s run wall — the query thread was saturated
~93 % of the experiment. This is independent evidence that the query is the
workload bottleneck, not a one-off outlier.

## Answers to the three P2-A questions

1. **Is queue lead sufficient to cover the L3→L2 stage?** **No, not in general.**
   Q1 p50 = 1.694 s vs the completed Q2 stage 16.567 s; only the deep tail
   (p95 22.7 s / p99 37.6 s) covers it. (Per-request coverage join is blocked by
   a telemetry gap, below.)
2. **How long is the L3→L2 stage?** **≈16.6 s** (n=1 direct), and it is
   **dominated by the storage query**: the M3 query for that attempt was 15.345 s
   = 92.6 % of the stage; the Q3 population p50 is 17.8 s.
3. **Is the storage metadata query worth optimizing?** **YES — decisively
   architectural.** p99 = 22.3 s vs the `>=1 ms` optimization band (4 orders of
   magnitude). Cause: metadata cache disabled → O(#L3 files) `os.scandir` per query.

## Fail-closed gaps (recorded, not imputed)

- **Telemetry gap:** the completed prefetch-restore rid `r129-s0-t2-081155` has
  **no `admission.v2`**, so the contractual per-request Q1↔Q2 join has 0/1
  coverage; 32 of 59 rids have `enqueue_mono_ns` but no `admission.v2`.
- **Q2 coverage:** n=1 (26 non-completed attempts). Report's residual accepted.

## Infra note (accountability)

The tester's "external SIGTERM at 08:20:46" was **this orchestrator's
lock-release watcher** (`/mnt/data/nerun-dev/tmp/p2a-release-lock.sh`): per the
user's GPU-sharing directive, it stopped the server ~8 s after the R129 workload
driver exited, which raced the tester's optional supplemental run. The main run
(59 requests, full window) completed and is unaffected; the lock is now FREE and
the 3090 is available to other users.

## Probe hygiene

Per-mark `probe_ns` max: M1 33.4 µs, M2 11.7 µs, M3 4.3 µs — all `<< 1 ms`; no
measurement defect. Cross-checks: monotonic clock only; no negative spans.

## Explicit non-claims

- No product fix was made; the metadata-cache configuration lever is a candidate
  optimization only (a profile/config change requiring separate authorization).
- No claim that Q1↔Q2 per-request coverage holds (blocked by the `admission.v2`
  gap).
