# RH Pressure Acceptance — VERDICT (2026-09-12)

```yaml
schema: rh-pressure-verdict-1
task_id: RH-PRESSURE-20260912
contract: work/RH-PRESSURE-ACCEPTANCE-CONTRACT-20260912.md sha b9bb2e17...8919
launcher: launch-p2b0m.sh sha 33d0cb99fc14b69ef41e8c1b41c345a4cefe12ddcfb82cc8a2fa61283bee0c72
evidence: run1 (ON first) + run2 (OFF first) + run3 (position-balanced on,off,off,on)
runs: /mnt/data/nerun-dev/p2b0/{run1,run2,run3}/
status: VERDICT — PARTIAL: idle benefit at C8, NO reproducible throughput benefit
```

Grading `FACT`/`INFERENCE`/`OPEN`/`DECISION`. Conclusion changes only by
`原结论 X; 新证据 Y; 因此修正为 Z`.

## 1. The measured question

Under resource competition/queueing (C4/C5/C8), does RH-ON horizon-aware staging
beat the RH-OFF enqueue-time eager prefetch on: earlier `ready_host`, less
`avoidable_recompute`, lower TFTT, lower `cache_induced_gpu_idle`, higher
throughput?

## 2. Pooled evidence (order- and position-balanced)

Each arm aggregates independent cells across runs; distributions matter, not
point estimates. `agg` = `aggregate_output_tps`; `idleE` =
`cache_induced_gpu_idle_engine`.

| C | arm | n | agg mean±sd | agg range | idleE mean±sd | idleE range |
|---|---|---|---|---|---|---|
| 4 | ON | 4 | 11.10 ± 3.86 | [6.56, 15.22] | 0.274 ± 0.139 | [0.105, 0.423] |
| 4 | OFF | 4 | 12.67 ± 3.23 | [7.89, 15.01] | 0.243 ± 0.205 | [0.110, 0.548] |
| 5 | ON | 2 | 11.04 ± 3.67 | [8.45, 13.63] | 0.297 ± 0.102 | [0.224, 0.369] |
| 5 | OFF | 2 | 11.88 ± 1.60 | [10.75, 13.02] | 0.268 ± 0.107 | [0.193, 0.344] |
| 8 | ON | 4 | 10.21 ± 2.19 | [7.98, 12.98] | **0.326 ± 0.091** | **[0.208, 0.425]** |
| 8 | OFF | 4 | 8.55 ± 0.22 | [8.23, 8.69] | **0.456 ± 0.021** | **[0.426, 0.475]** |

`FACT` (C8 idle — robust): ON idle `[0.208, 0.312, 0.359, 0.425]`, OFF idle
`[0.426, 0.457, 0.465, 0.475]`; **ON max (0.425) < OFF min (0.426)** — complete
separation. Direction is consistent in run1 (-0.040), run2 (-0.116), run3
(-0.182): RH-ON lowers cache-induced GPU idle at C8 under all three designs.

`FACT` (C8 throughput — NOT reproduced): ON agg `[7.98, 9.04, 10.83, 12.98]` vs
OFF `[8.23, 8.61, 8.67, 8.69]`; distributions **overlap** and the per-run
direction flips (run1 ON lower, run2 ≈equal, run3 ON higher). => no reproducible
throughput uplift.

`FACT` (C4/C5 — no separation): both `agg` and `idleE` distributions overlap
heavily across arms; C4 per-run direction flips with execution order (run1 ON
-53 %, run2 ON +67 %, run3 -14 %). Effect is inside the non-RH noise.

## 3. Verdict

`DECISION` (contract §4 requires idle-down **AND** throughput up in the same
direction):

* **C8: idle benefit YES, throughput benefit NOT DEMONSTRATED** => not a PASS.
  RH-ON does what it claims (stages earlier, the GPU waits less), but the freed
  idle is NOT converted into higher throughput at this profile — the workload is
  not throughput-limited by the cache-wait that RH removes.
* **C4/C5: NO SEPARATION** vs the eager prefetch.
* Overall: **RH incremental effectiveness at this profile = NOT DEMONSTRATED
  (partial: robust idle reduction at C8 only).** This is an honest reportable
  outcome, NOT converted into a PASS.

`INFERENCE`: since both arms prefetch (RH-off eager at enqueue, RH-on at the
horizon pass), and the eager path issues strictly earlier, RH's window is only
material at the highest pressure C8, where it does cut GPU idle — but the
bottleneck there is not the GPU-idle interval, so throughput is unchanged.

## 4. FACT — methodology corrections (both graded)

1. **Growing context (harness defect).** 原结论 (P2B0 §9 / pass-1 scorecard):
   "fixed per-session history H=6000 so concurrency is the only variable".
   新证据 `p2b0_driver.py:505-513`: the measure loop appends a fresh ~800-word
   delta plus the previous output every turn, so context grows (~18k+ tokens by
   turn 12) and `C x H <= 65536` breaks. 因此修正为: the P2B0 driver is a
   growing-context workload, not a fixed-H concurrency sweep; `aggTPS` is not
   comparable across different `MEAS`, and the pool-overflow regime was analysed
   as-is. Harness defect, not product defect.
2. **Non-stationary environment dominates single cells.** 原结论 (implicit):
   one cell per (C,RH) is enough. 新证据: identical (C,RH) cells differed by up
   to ~2x, correlating with launch-time ambient host RAM (~20 GiB -> slow vs
   ~24-26 GiB -> fast) and with execution position (non-monotonic in time). This
   reversed the C4 sign between run1 and run2. 因此修正为: RH-vs-OFF must be
   judged on pooled, order/position-balanced distributions, never single cells.

## 5. What would settle a definitive magnitude

`OPEN`: a randomized replicated design (many short cells, random arm order,
regression on ambient RAM/time as covariates) could size the C8 idle effect
precisely, but the throughput question is already answered in the negative for
this profile: idle is removed without a throughput change. A definitive
*throughput* effect would require a profile where the critical path is the
cache-wait (e.g., storage-latency-bound L3 cold load), not the present one.

## 6. Out of scope / unchanged

Product code; the manufactured no-prefetch control (rejected, Option B); CUDA
graph/TPS optimization; G1 restart-rebuild.
