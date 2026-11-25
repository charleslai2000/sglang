# G5-RCA — Gemma 4 C-8 fixed-final evidence review (2026-11-23)

## Verdict

**RCA status: evidence-complete for the available fixed-final artifacts; performance acceptance remains NO-GO.** The strongest supported diagnosis is severe host/device cache-capacity and restore/admission pressure, coincident with falling active batch size and low GPU utilization. This is a high-confidence bottleneck class, not a wall-clock attribution: available evidence does not quantify what fraction of lost throughput was caused by host allocation, device quota, CPU scheduling, or asynchronous L3 I/O. No contract-level implementation defect was established; no production source was changed and no new workload was run.

The fixed-final run is not a valid C-8 performance result: the wrapper records `bench_exit=124`, 780/800 requests, and an empty `capacity-at-end.metrics`; there is no completed performance summary or full output correctness gate. Do not derive a pass or a comparable throughput number from it.

## Evidence identity and boundaries

- Run: `/data/sglang-hicache/gemma4/runs/20261123T-g1-c8-gc-fixed-final/`
- Run source identity: `7ea2670bd27399ac5d522f184cf65e72e03df548` (from `source-identity.json` / manifest); repository HEAD at RCA: `9f9b95eca1dc58ad6746f7aec5975ef1e3295e29`. The latter is the later documentation closeout commit, not the code revision served.
- Manifest: FP8 E5M2, context 131072, `max_running=32`, device KV capacity 139264, CUDA graph bs32, HiCache host target 8 GiB, Extent file 32 GiB. See the run manifest for the complete settings.
- Client request-metrics contain 780 records, received from 07:08:06.860 to 08:06:08.938 UTC (about 58 minutes). The 780 records present are finished client requests; they do not account for the 20 missing requests.
- `perf.jsonl` is absent in this fixed-final directory (the similarly named historical run has one). `capacity-at-end.metrics` is zero bytes. Therefore no complete summary/output validation can be reconstructed.
- A search of the inspected Gemma-4 run tree and workspace found no `.nsys-rep`, `.qdrep`, `.ncu-rep`, SQLite profiler database, or usable GPU kernel trace for this run. GPU utilization sampling is not a kernel-time attribution.

## Request-path evidence, grouped by request receipt time

The 780 request records were split into equal thirds of the observed receipt-time span; these are descriptive windows, not independent controlled trials. Token-source shares use `l1+l2+l3+newly_prefilled` in the corresponding records as denominator.

| Receipt window | Records | E2E mean / p50 / p90 (s) | Enqueue→admission mean / p50 / p90 (s; records with both monotonic stamps) | L1 / L2 / L3 / new-prefill token share |
|---|---:|---:|---:|---:|
| Early, 07:08–~07:27 | 464 | 118.7 / 61.8 / 292.7 | 67.7 / 15.9 / 166.0 (178) | 9.9% / 38.5% / 13.9% / 37.7% |
| Middle, ~07:27–~07:47 | 172 | 282.9 / 85.4 / 835.9 | 184.6 / 21.4 / 706.4 (102) | 4.8% / 53.6% / 24.9% / 16.7% |
| Tail, ~07:47–08:06 | 144 | 146.2 / 48.0 / 528.8 | 109.6 / 13.8 / 540.5 (88) | 10.1% / 64.6% / 16.8% / 8.5% |

The admission monotonic stamps exist for only 368/780 requests; these percentiles apply only to that instrumented subset. Admission-to-prefill-finish stamps can cross the request-metric wall-clock boundary / be recorded in separate clock domains; the raw join produced an impossible negative mean in the early subset, so those values are deliberately excluded from attribution. They must not be interpreted as forward latency. The separate `prefill_finished_time` and `forward_entry_time` client fields also do not supply the full scheduler/restore path.

The cache-source distribution shifts from substantial newly prefilling early (37.7%) to more L2/L3 reuse in the middle and tail, while E2E and admission tails remain very high. Thus a higher hit share did not imply prompt service under this contention. This is consistent with shared capacity/admission pressure, but does not by itself distinguish restore transfer time from queueing or batch scheduling.

## Contemporaneous capacity and GPU evidence

The 7,191 valid pool-series samples cover about 3,600 seconds, at roughly 0.5-second cadence. Equal thirds of that sampled runtime show:

| Runtime third | Mean host HiCache use (tokens) | Mean KV available; minimum | Mean queued / running requests | Extend + decode forward-time delta / window; combined duty |
|---|---:|---:|---:|---:|
| First ~20 min | 172,214 (max 185,958) | 8,524; min 0 | 26.4 / 15.8 | 474.2 + 128.1 s / 1,199.6 s; 50.2% |
| Middle ~20 min | 179,726 (max 185,858) | 3,833; min 0 | 31.7 / 7.7 | 357.4 + 110.1 s / 1,199.7 s; 39.0% |
| Last ~20 min | 180,045 (max 185,858) | 6,338; min 0 | 22.6 / 5.5 | 292.5 + 160.2 s / 1,199.5 s; 37.7% |

Host pool was frequently near its 186,012-token effective limit; device free KV reached zero in every window. The middle period combines the largest queue, fewest running requests, lowest available KV, and worst request latency. Forward execution counters are cumulative device-forward execution time, not exclusive wall-clock attribution; summing extend and decode duties can be affected by overlap and does not identify the remaining idle interval's cause.

GPU samples independently show low utilization rather than sustained compute saturation: mean utilization about 30% early and 13–19% in later windows, with zero-utilization samples comprising 27–59% depending on the window (per `gpu-samples.csv`). NVML utilization is sampled/coarse and cannot identify why the GPU was idle.

## Restore and storage-path evidence

`server.log` P2A records show these `WAIT_CAPACITY` entry counts by runtime period (the period boundaries follow the server-log runtime split):

| Period | HOST_ALLOC | DEVICE_QUOTA | PREFETCH_BUDGET | FRONTIER |
|---|---:|---:|---:|---:|
| Early | 378 | 883 | 114 | 32 |
| Middle | 527 | 516 | 69 | 22 |
| Tail | 221 | 168 | 19 | 7 |

The matching prefetch-revoke records include allocation failures in the same 378/527/221 pattern and cache misses 991/330/156. These are repeated state/event observations, not unique requests or independent elapsed time. HOST_ALLOC records carry lifecycle `wait_id`; pairing wait to grant yields 1,156 granted wait episodes, about 52,092 request-seconds in aggregate (mean 45.1 s, median 46.7 s, p90 72.7 s, p99 93.6 s, max 100.1 s). The telemetry's 1,126 initial park records and larger grant-episode count differ because retries/lineage create multiple episodes. Request-seconds overlap across requests and must not be added to wall time or reported as throughput loss.

DEVICE_QUOTA has abundant per-RID WAIT observations (1,567 entries in the prior event reduction) but no equivalent validated single-lifecycle start→terminal duration join in the artifacts reviewed here. The entries indicate denied restore/admission opportunities, not their exclusive elapsed-time contribution. L3 extent logs report approximately 12,064 reads and 10,688 writes; byte totals previously reduced were about 172.3 GB KV reads, 56.0 GB KV writes and 33.8 GB SWA writes. Counts/bytes are not latency measurements, and there is no kernel/I/O profiler join to establish L3 blocking time.

End counters show L1/L2/L3/new prompt tokens about 0.84M/5.14M/1.63M/1.68M, prefetched 11.75M, load-back 7.84M, backup 6.56M, evicted 9.86M, avoidable recompute 0.56M and dropped tokens zero. These cumulative counters establish activity, not cost. The unfinished run also lacks a reliable final scrape.

## R60/R61 comparison disposition

The frozen R60 primary evidence located in `.memory/phase2-hicache-design/work/P0-C-PROFILE-FREEZE-20260911-R60.artifacts/r60_evidence.txt` is for an RTX 3060 / Qwen3.5-4B-AWQ service at `9213ee01d90ba3925e7fe928e80cc41354ee4fff`, not this RTX 3090 / Gemma 4 E4B workload. R61 is an independent review of that R60 capacity freeze, not a matching Gemma-4 C-8 trace. The Gemma-4 historical R60 throughput figures in the earlier closeout are secondary report values (0.4063/0.3931/0.3575 req/s); the underlying raw directory needed for a common re-reduction was not found in the inspected run tree. R61 lifecycle artifacts are partial and include `SOURCE_GATE_L2:0/1`, not a complete performance run. Consequently, no valid paired throughput delta or per-RID cross-run causal comparison can be claimed.

## Relevant implementation locations reviewed (served source revision)

- `python/sglang/srt/managers/scheduler.py:3860-3922`: HOST_ALLOC wait record creation and lifecycle IDs.
- `python/sglang/srt/managers/scheduler.py:4105-4320`: restore-state reconciliation, timeout/capacity wake, and retry path.
- `python/sglang/srt/managers/scheduler.py:5764-5887`: per-reason capacity wake predicate, including HOST_ALLOC and DEVICE_QUOTA checks.
- `python/sglang/srt/managers/scheduler.py:6829-6881` and `6941-6985`: waiting-queue iteration, WAIT_CAPACITY skip, and device-quota denial state handling.
- `python/sglang/srt/mem_cache/unified_radix_cache.py:7003-7045` and nearby callsites: pending-prefetch revoke handling; HOST_ALLOC wake telemetry is emitted at the cache/scheduler handoff near line 5757.

Reviewing these paths found no demonstrated mismatch between the logged wait transitions and the implemented bounded wake/retry behavior. These locations identify the relevant mechanisms; they are not asserted as root-cause defects.

## Causal assessment

1. **High confidence: capacity/restore/admission is a material bottleneck class in this run.** Supporting evidence converges: near-saturated host HiCache, recurrent zero KV headroom, sustained long queue with shrinking running batch, explicit HOST_ALLOC and DEVICE_QUOTA waits/allocation failures, and admission/E2E latency tails coinciding with the middle high-pressure interval.
2. **Moderate confidence: this pressure is a major explanation for the low observed GPU duty and incomplete service rate.** Device-forward duty declines as running requests shrink, but sampled utilization and forward counters do not isolate host wait, admission logic, CPU scheduling, L3 I/O, or other gaps. No percentage allocation is justified.
3. **Not established: L3 storage I/O is the dominant delay.** Read/write volume is high, but no operation-level duration or GPU-kernel causal join exists.
4. **Not established: a scheduler deadlock or a specific code defect.** The run timed out incomplete, but the observed waits have terminal HOST_ALLOC grants and repeated state transitions; missing requests alone do not prove a permanent wait/deadlock. No exact contract violation was tied to an RID and timestamp.
5. **No change proposed to eviction, ownership, or admission policy in this report.** Such changes would be architectural and require a separate evidence-backed minimal design and Owner approval.

## Gaps and next action

The available fixed-final artifacts support a bounded diagnosis, not the requested quantitative loss decomposition. Missing evidence: full C-8 completion and correctness, terminal metrics scrape, comparable same-hardware/source/config R60/R61 raw traces, valid per-RID DEVICE_QUOTA duration lineage, synchronized scheduler/CPU and H2D/D2H/L3 operation durations, and kernel-level GPU trace. Do not launch another full C-8 under the current no-repeat constraint. If the Owner authorizes further RCA, the minimum useful next input is recover the exact historical Gemma4 raw run bundle and its source/config identities; if that is unavailable, request a narrowly scoped, approved observation plan before any new run. No code change is recommended from present evidence.
