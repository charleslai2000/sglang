ENTRY: ACCEPT

status: done
task_id: T3060-RH-FINAL-ON-TRACE-20260909
orchestration_epoch: 20260909-rh-ab41
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 112337, 127.0.0.1:30000
revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
ready_horizon: ON (enable-ready-horizon, frontier 8, speculative fraction 0.6)
completeness: incomplete for the mandatory storage/RH join fields; bounded HTTP replay complete

## Summary

The identical five-way bounded RH-ON replay completed all five requests with HTTP
200 within the 180-second client bound. This is a complete workload replay, but
the required RH/storage evidence is incomplete: all five emitted only
`rh_preadmission.v1 decision=exclude reason=no_restore_potential`; none emitted a
joinable `decision=issue` with a non-null attempt ID, `ready_stage.v2`,
`rh_ready_host.v1`, or test-RID `rh_admission.v2`. The post-run probe range had
no request-correlated storage-query records, so KV/Mamba storage hits, storage
wait, and the RH ready-host rate are not computable and are never treated as zero.

## Scope and protocol

The run used five concurrent workers synchronized by a barrier, suffixes
`x,y,z,w,q`, prompt `(ch + " ") * 55000`, temperature `0`,
`max_new_tokens=1`, `POST /generate`, a fresh prefix
`TEST3060RHFINALONTRACE`, and a per-request timeout of exactly 180 seconds.

Batch ID: `1788948522295757187`.

All five workers started at `2026-09-09T18:08:42.303200` through
`18:08:42.304936+08:00`; the final response arrived at
`2026-09-09T18:11:12.442206+08:00`. No second load, restart, kill, seed change,
cache clear, code/gate change, or 3090 access was performed.

## Pre/post invariants

Preflight confirmation: `2026-09-09T18:08:13.016892450+08:00`.

- `/health` was HTTP 200; PID `112337` listened on `127.0.0.1:30000`.
- The command line contained revision-pinned RH-ON settings:
  `--enable-ready-horizon --ready-horizon-frontier-n 8
  --hicache-prefetch-speculative-fraction 0.6`, with
  `--max-running-requests 1`, file storage, `wait_complete`, and restore timeout
  180.
- `SGLANG_SEED=586963985`, `PYTHONHASHSEED=586963985`,
  `CUDA_VISIBLE_DEVICES=0`; seed path was
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Seed before: `23051071488` bytes and `550080` regular files.
- Pre-run offsets: launch log line 87 / `42518` bytes; probe line 291157 /
  `256648825` bytes. Post-delta scans therefore start at launch line 88 and
  probe line 291158.
- Pre-run broad fatal scan: 4 launch-log matches and 0 probe matches; all four
  were pre-existing health `rh_preadmission` lines whose `headroom` field
  contains the substring `oom`, not fatal events.

Final snapshot: `2026-09-09T18:14:54.373785708+08:00`.

- `/health` remained HTTP 200; PID `112337` and its command line remained alive
  and unchanged.
- Seed after: `23051071488` bytes and `550080` regular files.
- Final offsets: launch log line 722 / `252794` bytes; probe line 293057 /
  `258488377` bytes.
- The broad requested fatal scan returned 77 launch-log matches caused by the
  substring `oom` inside telemetry field `headroom`; the token-boundary fatal
  scan returned 0 matches in both complete post-delta ranges. No traceback,
  assertion, CUDA error, fatal marker, kill, segmentation, or actual OOM was
  observed.

Remote artifacts remain at:

- `/tmp/sglang3060-f629-rh-on-20260909.log`
- `/tmp/t38c-probe.log`

## HTTP outcomes

| suffix | RID | outcome | client wall seconds | e2e latency seconds | response fields |
|---|---|---|---:|---:|---|
| x | `TEST3060RHFINALONTRACE_x_1788948522295757187_1788948522297891278` | HTTP 200 | 59.650295 | 59.491703 | prompt 55001, completion 1, cached_tokens 0, cached_tokens_details null |
| y | `TEST3060RHFINALONTRACE_y_1788948522295757187_1788948522299312390` | HTTP 200 | 89.824507 | 89.546684 | prompt 55001, completion 1, cached_tokens 0, cached_tokens_details null |
| z | `TEST3060RHFINALONTRACE_z_1788948522295757187_1788948522300360236` | HTTP 200 | 120.024966 | 119.625797 | prompt 55001, completion 1, cached_tokens 0, cached_tokens_details null |
| w | `TEST3060RHFINALONTRACE_w_1788948522295757187_1788948522301474684` | HTTP 200 | 150.137297 | 149.618333 | prompt 55001, completion 1, cached_tokens 0, cached_tokens_details null |
| q | `TEST3060RHFINALONTRACE_q_1788948522295757187_1788948522302473703` | HTTP 200 | 29.692047 | 29.682186 | prompt 55001, completion 1, cached_tokens 0, cached_tokens_details null |

All responses had one output token with length finish reason. `cached_tokens=0`
is an actual HTTP response field; it is not used as a substitute for the
missing storage-query evidence. No TTFT field or TTFT timestamp was emitted;
the recorded `e2e_latency` and client wall time are the available response-time
measurements, not a separately observed TTFT.

## Per-RID telemetry

The launch log was correlated by the primary `rid=` field in the post-run range.
Every RID had only `rh_preadmission.v1` decisions of `exclude`, with reason
`no_restore_potential`; there were zero `decision=issue` records and therefore
zero non-null issue attempt IDs. No `ready_stage.v2`, `rh_stage.v2`,
`rh_ready_host.v1`, or test-RID `rh_admission.v2` record was present.

| suffix | preadmission decisions | plain admission can_run | required storage/RH fields | waits/alloc/retries/recompute/hybrid_discard |
|---|---|---|---|---|
| x | 2 exclude; no issue | 0: 1, 1: 25 | storage query, KV/Mamba, ready-stage, ready-host, and admission.v2 missing | no request-correlated records emitted; not computable, not zero |
| y | 13 exclude; no issue | 0: 1, 1: 26 | same mandatory fields missing | not computable, not zero |
| z | 24 exclude; no issue | 0: 1, 1: 26 | same mandatory fields missing | not computable, not zero |
| w | 35 exclude; no issue | 0: 1, 1: 26 | same mandatory fields missing | not computable, not zero |
| q | 1 exclude; no issue | 0: 1, 1: 0 | same mandatory fields missing | not computable, not zero |

The exact post-run probe range (line 291158 onward) contained no occurrence of
the five RIDs and no `query_suffix_len`, `kv_hit_pages`, `storage_hit_count`,
`sidecar_hits`, `pc_get_v2`, or `pc_l3_host` records. Consequently:

- KV hit, Mamba/aux hit, L3/Host actual KV+aux, and storage wait are missing for
  all five RIDs; they are not zero.
- No RH issue attempt was observed, so no attempt-correlated ready-stage or
  admission join can be formed.
- Strict observed eligible denominator (`decision=issue` with non-null
  `attempt_id`) is `0`; the requested ready-host-before-admission rate is
  `not_computable`/undefined (`0/0` is not reported as 0%). The broader eligible
  set cannot be reconstructed without the missing storage/RH fields.

## Direct comparison with TEST3060-RH-FINAL-OFF-TRACE-20260909.md

| suffix | OFF result / wall seconds | ON result / wall seconds | direct observed difference |
|---|---:|---:|---|
| x | timeout / 180.098683 | HTTP 200 / 59.650295 | ON completed within bound; 120.448388 s less client wall time than OFF timeout |
| y | timeout / 180.102028 | HTTP 200 / 89.824507 | ON completed within bound; 90.277521 s less client wall time than OFF timeout |
| z | HTTP 200 / 52.335297 | HTTP 200 / 120.024966 | ON 67.689669 s slower |
| w | timeout / 180.103363 | HTTP 200 / 150.137297 | ON completed within bound; 29.966066 s less client wall time than OFF timeout |
| q | HTTP 200 / 108.869150 | HTTP 200 / 29.692047 | ON 79.177103 s faster |

Completion count changed from OFF `2/5` HTTP 200 and `3/5` timeouts to ON `5/5`
HTTP 200 and `0/5` timeouts. Mean client wall time over all ON completions was
`89.865822` seconds; the OFF successful-response mean was `80.602224` seconds
(only `z` and `q` were successful within the OFF bound). This is a direct
runtime observation, not a causal attribution to RH.

OFF reported `54976` KV/storage hits and one Mamba sidecar hit per RID. ON did
not emit the corresponding request-correlated storage records, so exact
storage-hit and storage-wait comparison is `not_computable`; ON response
`cached_tokens=0` must not be promoted to a storage-query miss claim.

## Interpretation and classification

RH did not produce an observed RH preadmission issue or ready-host path in this
run: every preadmission decision excluded the request as having no restore
potential. Therefore the improved bounded completion count and the per-suffix
wall-time changes cannot establish RH TTFT improvement. The observed serialized
roughly 30-second completion spacing, `max-running-requests=1`, and repeated
plain admission records show the remaining capacity/queue constraint in the
runtime. The required explicit wait/allocator/retry telemetry was not emitted,
so no stronger causal diagnosis is made here.

- Product defect: not established by this independent runtime run; only emitted
  behavior and missing evidence are reported.
- Test defect: the workload protocol and 180-second bound were correct. A
  procedural scope deviation occurred in the first preflight: a temporary
  `/tmp/codex-health-body` file was created and removed to capture health output.
  It left no residual file and did not touch service, launch/probe logs, seed,
  or storage. Subsequent captures were read-only.
- Infrastructure issue: none observed; health, PID, process arguments, seed
  counts, log/probe offsets, and token-boundary fatal scans completed.
- Missing evidence: request-correlated storage queries, KV/Mamba hits, storage
  waits, issue attempts, ready-stage/ready-host/admission.v2 joins, and
  request-correlated wait/alloc/retry/recompute/hybrid-discard events.

artifacts: this report; `/tmp/sglang3060-f629-rh-on-20260909.log`; `/tmp/t38c-probe.log`; captured five-RID HTTP output in the task execution record
evidence: final revision marker; pre/post health/PID/args/seed/offsets; exact five-way barrier-synchronized 55K replay; per-RID response and wall/e2e timing; post-delta telemetry scans; direct comparison with TEST3060-RH-FINAL-OFF-TRACE-20260909.md
summary: bounded RH-ON replay complete with 5/5 HTTP 200; mandatory RH/storage join incomplete and rate not computable; no RH TTFT attribution established; queue/capacity serialization remained observable
followups: fresh Task ID required for diagnosis, another load, or telemetry repair/replay
open_issues: missing mandatory RH/storage telemetry; initial preflight temporary-file scope deviation, with no residual or product/storage impact
