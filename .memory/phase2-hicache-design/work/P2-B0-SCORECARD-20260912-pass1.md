# P2-B0 scorecard — pass 1 (10 cells, extent L3, RH ON/OFF)

```yaml
schema: phase2-hicache-p2b0-scorecard-1
artifact_id: P2-B0-SCORECARD-20260912-PASS1
task_id: P2-B0-20260912
role: orchestrator (live measurement)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
status: PASS-1 (valid data; idle attribution pending vehicle fix + re-sample)
```

## 1. Setup

- Extent L3; launcher `launch-p2b0.sh` `89410fe8…b7b9`; profile = frozen 3090
  (`--max-total-tokens 65536`, `--max-mamba-cache-size 53`), only
  `--max-running-requests = C` varies; RH ON = base, RH OFF = base minus the
  four RH flags.
- Cells: `C in {1,4,5,6,8} x {RH-ON, RH-OFF}`, `H=6000`, prime=2, measure=8,
  `measure-seconds=240`. Driver `p2b0_driver.py` (streaming; `include_usage`;
  `return_cached_tokens_details`). 0 bad HTTP in every cell.
- Raw data: `/mnt/data/nerun-dev/p2b0/cell-<rh>-c<n>/`.

## 2. Workload shape (why aggregate output TPS is small)

Mean prompt ~27,750 tokens, mean output 32 tokens (prefill-dominated). Measured
prompt-token provenance from `sglext.cached_tokens_details`:

| Cell | device | host (L2) | storage (L3) |
| --- | --- | --- | --- |
| RH-ON C4 | 7,493 | 15,566 | 738 |
| RH-ON C8 | 5,602 | 3,582 | **10,942** |
| RH-OFF C8 | 7,275 | 3,039 | **11,109** |

At C8 about **39 % of prompt tokens are served from L3** — a genuinely
L3-loaded workload. `aggregate_output_tps` is a poor throughput proxy for this
shape (32-token outputs); prompt throughput at C8 ~= 27,750 x 0.238 ~= 6.6k
tok/s.

## 3. RH ON vs OFF

| C | RH | aggTPS | reqTPS | TTFT p50 (s) | TTFT p95 (s) | gpuIdle frac |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ON | 11.17 | 0.349 | 1.426 | 2.552 | 0.000 |
| 1 | OFF | 13.15 | 0.411 | 0.977 | 1.143 | 0.010 |
| 4 | ON | 16.93 | 0.529 | 4.212 | 8.496 | 0.017 |
| 4 | OFF | 18.30 | 0.572 | 4.203 | 10.386 | 0.000 |
| 5 | ON | **14.99** | 0.468 | 5.015 | **20.234** | 0.110 |
| 5 | OFF | 9.52 | 0.297 | 4.867 | 29.239 | 0.064 |
| 6 | ON | 8.67 | 0.271 | 6.270 | **41.498** | 0.351 |
| 6 | OFF | 8.63 | 0.270 | 5.338 | 47.571 | 0.000 |
| 8 | ON | **7.62** | 0.238 | 10.361 | 81.366 | 0.396 |
| 8 | OFF | 6.90 | 0.216 | 15.947 | 67.240 | 0.352 |

Observations (pass 1):

- RH has a small cost at C1/C4 (no pressure; ON slightly lower TPS).
- RH helps where pressure exists: **C5 +57 % aggTPS, C8 +10 %**; C6 neutral.
- **Stage tail (Q2 = ready - prefetch_issue, ms):**

| C | RH-ON p50 / p95 (n) | RH-OFF p50 / p95 (n) |
| --- | --- | --- |
| 4 | 639 / 833 (8) | 605 / 862 (7) |
| 5 | 1256 / 2002 (26) | 2467 / 4911 (18) |
| 6 | 1442 / 3684 (52) | 1530 / 7250 (47) |
| 8 | 1999 / 4098 (112) | 2224 / 8819 (114) |

  RH ON roughly halves the **p95** stage at C6/C8 — the headline RH benefit in
  this era. Note Q2 still includes host-slot/compute wait under concurrency, so
  it is the end-to-end stage latency, not pure storage IO.
- Scenario mix shifts with C: cold-L3 grows from 3 (C4) to 31 (C8) of the
  measure requests, which is what drives TTFT p95 up at high C.
- **GPU idle grows with C** (0 -> ~0.35-0.40). At C8 the GPU is idle a large
  fraction of the window despite 8 in-flight requests: the system is not
  compute-bound, it is cache/restore/staging-bound. This is the quantity the
  user wants attributed.

## 4. Pending in pass 1 (honest)

- `cache_induced_gpu_idle`: pass-1 sampler parsed `num_running_reqs` /
  `num_queue_reqs`, but the server exposes `sglang:num_running_reqs` /
  `sglang:num_queue_reqs` (`observability/metrics_collector.py:292-299`), so
  those columns were 0 and the metric is 0 by construction. **Fix in flight**
  (background coder) with a precise redefinition:
  `pending_work = running + queue > 0` AND `util < threshold`, plus a precise
  `restore_interval` variant derived from per-rid restore events. Historical
  cells will recompute the restore variant from logs + `gpu.csv`.
- `queue_lead_q1`: `admission.v2` is emitted only on the `AddReqResult.CONTINUE`
  branch (`scheduler.py:6821-6824`) and is therefore rare at
  `--max-running-requests = C` (2 occurrences vs 80 enqueues at C8). Reported as
  `not computable` for those cells, plus an available fallback proxy
  (`enqueue -> prefetch_issued`) once the fixed analyzer lands. This is a
  genuine telemetry gap, not a fabricated value.
- Reconciliation residual (`restore_wait/queue_wait/compute`): `not computable`
  per R71 §3.4 (no per-request duration seam). Only `decode` is computable.

## 5. `total_throughput`

`not computable` — authoritative definition pending (R71 option T4;
`plan.md:98`). MUST NOT be replaced by `aggregate_output_tps` or any derivative.

Status: pass-1 valid metrics frozen; idle attribution pending the vehicle fix
and, if needed, a re-sample of the 10 cells.
