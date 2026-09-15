# RH Pressure Acceptance — contract (frozen 2026-09-12, user-authorized)

Status: FROZEN by user ruling (2026-09-12, Option A) after R-HBA1 closed as
behavioral PASS. Grading protocol: every statement labelled
`FACT` / `INFERENCE` / `OPEN` / `DECISION`; conclusions change only by
`原结论 X; 新证据 Y; 因此修正为 Z`.

## 1. The single question (frozen)

`FACT` (R-HBA1): at C1 with a sufficient lead, both RH-ON and RH-OFF reach the
same hidden/restored/no-recompute state because RH-OFF carries the upstream
`EAGER_RH_OFF` prefetch at enqueue (`scheduler.py:6068-6072`). C1 therefore
cannot separate them.

> Under resource competition and queueing (C4/C5/C6/C8, fixed device KV pool),
> does RH-ON horizon-aware staging beat the RH-OFF enqueue-time eager prefetch
> on: earlier `ready_host`, less `avoidable_recompute`, lower TFTT, lower
> `cache_induced_gpu_idle`, and higher `request_tps`/completion?

`DECISION`: this is an **effectiveness** line, NOT a correctness gate. Neither
arm is "no prefetch"; the differentiator is *when/which* prefix is staged
(horizon-aware vs eager-at-enqueue) under contention. Failure to separate is a
valid outcome, reported as such — never fabricated into a PASS.

## 2. Scope and authority

* Reuses the P2-B0 frozen measurement profile (extent L3, FP8 KV,
  `--max-total-tokens 65536`, `--max-running-requests=C`, `--max-mamba-cache-size
  53`, CUDA graphs off). No product-code change. G1 restart-rebuild and
  CUDA-graph/TPS optimization are OUT OF SCOPE.
* Cells: `C in {4,5,6,8} x {RH-ON, RH-OFF}`. Workload `H = 6000` tokens/session
  so `C*H <= 65536` (concurrency is the only axis). `C6` is optional/secondary;
  the primary frozen re-sample scope is `{C4,C5,C8}`.
* Metric naming (binding, carried from P2B0 §10): emit `aggregate_output_tps`,
  `request_tps`, `effective_compute_tps`, `served_context_tps`; NO
  `total_throughput`. Cached prefix tokens never count as input compute.
  Any `queue_lead_q1` fallback is a separately named `prefetch_lead_proxy`.

## 3. Metrics (with seam)

| metric | definition | seam |
|---|---|---|
| `ready_host` timing | `ready_mono - prefetch_issue_mono` per rid | probe M2 + `evt=ready_host` |
| `avoidable_recompute` | `max(0, D_req - cached_total)` inside D_req | `sglext.cached_tokens_details` |
| TFTT | `B_first - A_last` (streaming) | client |
| `cache_induced_gpu_idle_engine` | idle fraction while `running+queue>0` | `nvidia-smi` timeline + `/metrics` `sglang:num_running_reqs`/`sglang:num_queue_reqs` |
| `cache_induced_gpu_idle_restore` | idle fraction inside per-rid `[prefetch_issue, ready_host]` | `gpu.csv` + monotonic marks |
| throughput | §2 naming | client streaming + `/metrics` decode counter |

`FACT` (known seam gaps, must be reported not fabricated): `admission.v2` is rare
at C>1 (`AddReqResult.CONTINUE` only) so `queue_lead_q1` is often
`not computable`; `restore_wait/queue_wait` reconciliation lacks a per-request
duration seam.

## 4. Acceptance

`DECISION`: the pressure verdict is a **direction-consistency** judgement, not a
single pass/fail:

* `PASS (RH adds value)` — at C5 and/or C8, RH-ON shows: `ready_host` earlier
  and/or fewer WAIT_CAPACITY stalls; `avoidable_recompute` no worse;
  `cache_induced_gpu_idle` lower **and** moving in the same direction as the
  `request_tps`/completion uplift.
* `NO SEPARATION` — metrics within noise at every C; RH's incremental value is
  not demonstrated at this profile (honest, reportable outcome).
* `NEGATIVE` — RH-ON materially worse on idle or throughput under pressure.

Minimum `>= 40` completed requests per cell, else the cell is `under-sampled`.
Correctness side-condition (from R-HBA1): measured hits must show no full-prefix
recompute and 0 bad HTTP.

## 5. Out of scope

Product/code/test change; the manufactured "true no-prefetch" control (rejected
by user, Option B); C1 re-run; CUDA-graph/quantization/kernel TPS work; G1.
