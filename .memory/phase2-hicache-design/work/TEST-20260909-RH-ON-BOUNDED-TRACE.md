ENTRY: ACCEPT

# TEST-20260909-RH-ON-BOUNDED-TRACE

```text
status: done
task_id: T3060-RH-ON-BOUNDED-TRACE-20260909
orchestration_epoch: 20260909-rh-ab10
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 102147, 127.0.0.1:30000
ready_horizon: ON (enable_ready_horizon=True, frontier 8, speculative fraction 0.6)
verdict: COMPLETE bounded replay; timeout rows have explicitly missing response fields
```

## Verdict and scope

The identical bounded RH-ON replay completed for all five client requests under the
required 180-second timeout. `z` returned HTTP 200 in 88.201206 seconds. `x`, `y`,
`w`, and `q` reached the terminal client timeout at approximately 180 seconds.

This is a complete bounded replay, but not a complete successful-response telemetry
set: response status, response wall time, and response device/host/storage fields are
missing for the four timeout rows and are not interpreted as zero. Request-correlated
probe and service evidence was available to the extent emitted by the running
service. No restart, kill, seed change, cache clear, code change, 3090 access, or
additional request was performed by this task.

## Preflight and post-run invariants

Preflight: `2026-09-09T14:40:11.493993304+08:00`.

- PID `102147` was alive and listening on `127.0.0.1:30000`; `/health` returned
  HTTP 200.
- The command line contained the retained RH-OFF profile plus
  `--enable-ready-horizon`, `--ready-horizon-frontier-n 8`, and
  `--hicache-prefetch-speculative-fraction 0.6`.
- `/proc/102147/environ` contained the exact seed directory
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Seed before replay: `du -sb` = `23051071488` bytes; regular files = `550080`.
- Pre-request offsets:

  ```text
  /tmp/sglang3060-rh-on-restart-20260909.log  29418 bytes, 88 lines
  /tmp/t38c-probe.log                         154056556 bytes, 177098 lines
  ```

All five clients were terminal by about `2026-09-09 14:44:32 +08:00`; the harness
then stopped waiting. A quick post-run check at
`2026-09-09T14:48:11.282856233+08:00` found PID `102147` alive, `/health` HTTP 200,
and the seed unchanged at `23051071488` bytes / `550080` regular files. Immediate
post-run log offsets captured during collection were:

```text
/tmp/sglang3060-rh-on-restart-20260909.log  48360605 bytes, 287484 lines
/tmp/t38c-probe.log                         255836854 bytes, 289138 lines
```

## Exact workload

The remote harness used five concurrent workers and a barrier. The only changed
batch prefix was `TEST20260909RHONBOUNDED`; batch ID was
`1788936092647977306`. For each `ch` in `x,y,z,w,q` it sent:

```python
{"rid": f"TEST20260909RHONBOUNDED_{ch}_1788936092647977306_{time.time_ns()}",
 "text": (ch + " ") * 55000,
 "sampling_params": {"temperature": 0, "max_new_tokens": 1}}
```

The endpoint was `POST http://127.0.0.1:30000/generate`, with client timeout exactly
180 seconds. Correlation used fixed-string RID matching and bounded aggregation over
the service and probe logs; no fragile heredoc was used.

## HTTP outcomes

| suffix | RID | terminal outcome | client wall seconds | response cache fields |
|---|---|---|---:|---|
| `x` | `TEST20260909RHONBOUNDED_x_1788936092647977306_1788936092648331858` | client `TimeoutError` | 180.103960 | missing; not zero |
| `y` | `TEST20260909RHONBOUNDED_y_1788936092647977306_1788936092649957633` | client `TimeoutError` | 180.103648 | missing; not zero |
| `z` | `TEST20260909RHONBOUNDED_z_1788936092647977306_1788936092651529085` | HTTP 200 | 88.201206 | `cached_tokens=54976`, device `0`, host `0`, storage `54976` |
| `w` | `TEST20260909RHONBOUNDED_w_1788936092647977306_1788936092653117774` | client `TimeoutError` | 180.023263 | missing; not zero |
| `q` | `TEST20260909RHONBOUNDED_q_1788936092647977306_1788936092654689299` | client `TimeoutError` | 180.105445 | missing; not zero |

The successful response had `prompt_tokens=55001`, one output token, and
`finish_reason.type=length`. Its response body reported `cached_tokens_details` of
device `0`, host `0`, storage `54976`, backend `HiCacheFile`.

## Per-RID correlated evidence

For every RID, the probe emitted a storage query with
`query_suffix_len=55000`, `kv_hit_pages=54976`, `storage_hit_count=54976`, and
`sidecar_hits.kv=54976`, `sidecar_hits.mamba=54976`. These are explicit storage
query values, not inferred zeros.

| RID suffix | probe/device-host evidence | RH / host-ready evidence | scheduler and restore evidence |
|---|---|---|---|
| `x` | 49 KV `pc_get_v2` batches captured before collection ended, totaling `kv_hits=49152` / `n_keys=50176`; no Mamba sidecar or `pc_l3_host` event emitted. HTTP device/host fields missing. | No RH eligibility, prediction, staging, explicit L3-to-Host start/end, `materialized`, or `ready_host` event emitted. | Admission `can_run=0` 63394 times and `can_run=1` once. One prefetch issued; 121 `WAIT` dispositions with `reason=denied_rate_limit`; `WAIT_CAPACITY reason=PREFETCH_BUDGET`; two capacity retry records. Prefetch I/O finished at `49152`, then client disconnect cleanup; no restore success/ready/finalize. No recompute or hybrid discard observed. |
| `y` | No `pc_get_v2` KV or Mamba sidecar result and no `pc_l3_host` event emitted. HTTP device/host fields missing. | No RH eligibility, prediction, or RH staging event emitted. One later `ready_stage` record reported `state=RESTORING ready=0`; no `ready_host` or materialized event. | Admission `can_run=0` 63321 times. 121 rate-limit WAITs plus `WAIT_CAPACITY/PREFETCH_BUDGET`; one capacity retry and host-allocation wait (`reason=HOST_ALLOC`). First prefetch revoked `miss_reason=alloc_failed` with storage hit `54976`; subsequent termination cleanup was also observed. One timeout recompute; no restore success or hybrid discard. |
| `z` | 54 KV batches totaling `kv_hits=54976`; one Mamba sidecar record with `hit_pages.mamba=1`; one `pc_l3_host` record `completed_tokens=54976`, `requested_tokens=55000`. HTTP device/host/storage = `0/0/54976`. | No RH eligibility, prediction, or explicit staging event. No explicit `l3_to_host_start/end`, `materialized`, or `ready_host` event; service emitted `restore_ready` and `restore_state=READY`. | Admission `can_run=0` 33127 times; no `can_run=1` record was emitted. One prefetch issued; `prefetch_io_finished=54976`, finalize `54976`, restore disposition `PARTIAL 54976/55000 reason=shortfall`, restore success and ready. No wait-budget retry/failure, recompute, or hybrid discard. |
| `w` | No `pc_get_v2` KV or Mamba sidecar result and no `pc_l3_host` event emitted. HTTP device/host fields missing. | No RH eligibility, prediction, staging, explicit L3-to-Host start/end, materialized, or `ready_host` event emitted. | Admission `can_run=0` 63227 times. 121 rate-limit WAITs plus `WAIT_CAPACITY/PREFETCH_BUDGET`; one capacity retry and host-allocation wait (`reason=HOST_ALLOC`). One prefetch revoked `miss_reason=alloc_failed` with storage hit `54976`; one timeout recompute. No restore success or hybrid discard. |
| `q` | No `pc_get_v2` KV or Mamba sidecar result and no `pc_l3_host` event emitted. HTTP device/host fields missing. | No RH eligibility, prediction, staging, explicit L3-to-Host start/end, materialized, or `ready_host` event emitted. | Admission `can_run=0` 63267 times. 121 rate-limit WAITs plus `WAIT_CAPACITY/PREFETCH_BUDGET`; one capacity retry and host-allocation wait (`reason=HOST_ALLOC`). One prefetch revoked `miss_reason=alloc_failed` with storage hit `54976`; one timeout recompute. No restore success or hybrid discard. |

The logs emitted no explicit RH-eligible, RH-prediction, or RH-staging event for any
RID. The only `ready_stage` record was the post-timeout `y` record above, with
`ready=0`. Therefore the requested RH-eligible host-ready-before-admission rate is
**not emitted / not computable**; it is not `0%`. Likewise, no synchronous-storage
wait event was emitted for any RID, and this absence is not interpreted as zero wait.

## RH-OFF versus RH-ON

The comparison baseline is `TEST-20260909-RH-OFF-BOUNDED-TRACE.md`, using the same
five suffixes, prompt construction, barrier, and 180-second client bound.

| suffix | RH-OFF outcome / wall s | RH-ON outcome / wall s | exact comparison |
|---|---:|---:|---|
| `x` | timeout / 180.019736 | timeout / 180.103960 | both bounded timeouts; ON +0.084224 s |
| `y` | timeout / 180.102502 | timeout / 180.103648 | both bounded timeouts; ON +0.001146 s |
| `z` | HTTP 200 / 109.507534 | HTTP 200 / 88.201206 | ON faster by 21.306328 s, 19.5% |
| `w` | HTTP 200 / 49.094363 | timeout / 180.023263 | OFF completed; ON timed out |
| `q` | timeout / 180.079970 | timeout / 180.105445 | both bounded timeouts; ON +0.025475 s |

| aggregate | RH-OFF | RH-ON |
|---|---:|---:|
| HTTP 200 | 2/5 | 1/5 |
| client timeouts | 3/5 | 4/5 |
| mean wall time of successful responses | 79.300949 s | 88.201206 s |
| storage query hit pages per RID | 54976 for all 5 | 54976 for all 5 |
| explicit RH-eligible host-ready-before-admission rate | not emitted in OFF | not emitted in ON |

Under this trace, RH-ON produced a 21.306-second improvement for the one directly
comparable successful suffix, `z`, but it did not materially improve the overall
bounded outcome: successful responses fell from 2/5 to 1/5, timeouts rose from 3/5
to 4/5, and the successful-response mean increased because `w` regressed to a
timeout. The observed four RH-ON timeout rows remained dominated by rate-limit and
host-allocation waits. Thus the evidence does **not** establish a material overall
reduction in storage wait or TTFT for this five-way trace; it establishes only a
suffix-specific `z` TTFT improvement.

## Evidence classification

- Product defect: this tester run does not establish a causal defect. It observed
  bounded timeouts, capacity/host-allocation waits, and missing RH telemetry.
- Test defect: none established. The five workers used the required barrier,
  workload, and exact 180-second timeout; every client reached a terminal state.
- Infrastructure issue: none observed. SSH, HTTP, fixed-string correlation,
  health, process, seed, and storage checks completed.
- Missing evidence: response-level fields for four timed-out RIDs; explicit RH
  eligibility/prediction/staging; explicit L3-to-Host start/end; explicit
  materialized/ready_host; and synchronous-storage wait telemetry. These are
  missing fields/events, not zero values.

## Artifacts, followups, and open issues

Artifacts/evidence:

- This report.
- RH-ON restart log: `/tmp/sglang3060-rh-on-restart-20260909.log`.
- Request-correlated probe: `/tmp/t38c-probe.log`.
- Captured client output for all five RIDs, including exact terminal status and wall
  time.
- Pre/post process, health, seed-count, log-offset, and fixed-string correlation
  outputs in the task execution record.

Summary: complete bounded RH-ON replay. One request completed successfully, four
timed out at the mandated bound. Storage hit evidence was present for all five;
only `z` reached a successful client response and emitted complete KV/Mamba/L3-host
success telemetry. RH eligibility and the requested host-ready-before-admission
rate were not emitted.

Followups: none within this Task ID. Further replay, diagnosis, or telemetry work
requires a fresh Task ID.

Open issues:

- Four timeout rows cannot support response-level TTFT/device/host/status fields.
- RH eligibility/prediction/staging and synchronous-storage wait events were not
  emitted, so their rates are not computable.
- The service continued asynchronous cleanup/recompute logging after some client
  disconnects; those events are reported as emitted telemetry and are not treated as
  additional client requests.

```text
status: done
artifacts: TEST-20260909-RH-ON-BOUNDED-TRACE.md; RH-ON restart/probe log paths; captured five-RID client output
evidence: bounded 180s replay; complete terminal outcomes; fixed-string RID correlation; unchanged seed; healthy PID; HTTP 200 post-check
summary: complete RH-ON bounded replay; z improved versus OFF, but overall timeout/completion outcome regressed and RH rate was not emitted
followups: none; new replay or diagnosis requires fresh Task ID
open_issues: timeout rows lack response fields; RH eligibility/prediction/staging and synchronous wait telemetry missing
```
