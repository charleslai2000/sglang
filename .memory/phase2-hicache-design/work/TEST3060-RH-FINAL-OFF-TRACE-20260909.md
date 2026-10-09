ENTRY: ACCEPT

# TEST3060-RH-FINAL-OFF-TRACE-20260909

status: done
task_id: T3060-RH-FINAL-OFF-TRACE-20260909
orchestration_epoch: 20260909-rh-ab35
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 107356, 127.0.0.1:30000
revision_input: 6edf69ce29fe2598fba51c94a99315239cf1a8c8
ready_horizon: OFF (enable_ready_horizon=False)
completeness: incomplete for the requested RH schema set; all emitted per-RID evidence was collected

## Scope

Only the authorized remote HTTP workload and read-only process, log, probe, and
storage inspection were performed. No restart/kill, code or gate change, seed
clear/alteration, or 3090 access was performed. The only local write was this
report.

The dispatch-named TEST3060-RH-OFF-BOUNDED-TRACE.md was absent at the supplied
path. The exact prior protocol was recovered from the related
TEST-20260909-RH-OFF-TRACE.md artifact: five concurrent barrier-synchronized
suffixes x,y,z,w,q; prompt (ch + " ") * 55000; temperature 0;
max_new_tokens=1; POST /generate; client timeout 180 seconds; fresh batch
prefix TEST3060RHFINALOFFTRACE.

## Preflight and post-run evidence

Preflight command: read-only SSH to i-1.gpushare.com:27460 using the supplied
key, then health curl, ps/proc/107356 inspection, selected environment
inspection, seed du/find, and launch/probe stat/wc.

Preflight timestamp: 2026-09-09T17:24:59.387261643+08:00.

Preflight evidence:

- HTTP health 200; PID 107356 alive.
- Command included max-running-requests=1, file backend,
  wait_complete, restore timeout 180, random seed 586963985.
- server_args included enable_ready_horizon=False and max_running_requests=1.
- SGLANG_SEED=586963985, PYTHONHASHSEED=586963985, CUDA_VISIBLE_DEVICES=0.
- Seed path: /hy-tmp/hicache-qwen35-4b-p4-retry-20260909.
- Seed before: 23051071488 bytes, 550080 regular files.
- Launch offset before: /tmp/sglang3060-rh-final-20260909.log,
  35987 bytes / 124 lines.
- Probe offset before: /tmp/t38c-probe.log, 255983324 bytes / 289505 lines.

Post-run command: read-only health curl, ps/proc inspection, seed du/find,
launch/probe stat/wc, and fatal scan over the post-offset deltas using:

    tail -n +125 /tmp/sglang3060-rh-final-20260909.log | grep -Ei 'traceback|assert|out.of.memory|cuda.*error|fatal|killed|segmentation|oom'
    tail -n +289506 /tmp/t38c-probe.log | grep -Ei 'traceback|assert|out.of.memory|cuda.*error|fatal|killed|segmentation|oom'

Post-run timestamp: 2026-09-09T17:30:37.699619277+08:00.

Post-run evidence:

- HTTP health 200; PID 107356 remained alive with unchanged command.
- Seed after: 23051071488 bytes, 550080 regular files.
- Launch offset after: 72752656 bytes / 432751 lines.
- Probe offset after: 256630073 bytes / 291120 lines.
- Fatal scan: no matches in either post-offset delta.

Remote artifacts remain at:

- /tmp/sglang3060-rh-final-20260909.log
- /tmp/t38c-probe.log

## Exact run and HTTP outcomes

Batch ID: 1788946027793484104. All requests started at approximately
2026-09-09T17:27:07.803+08:00 and were terminal by 17:30:07.908+08:00.

| suffix | RID | terminal outcome | wall seconds | response |
|---|---|---|---:|---|
| x | TEST3060RHFINALOFFTRACE_x_1788946027793484104_1788946027795490402 | client TimeoutError | 180.098683 | response fields missing; not zero |
| y | TEST3060RHFINALOFFTRACE_y_1788946027793484104_1788946027797542992 | client TimeoutError | 180.102028 | response fields missing; not zero |
| z | TEST3060RHFINALOFFTRACE_z_1788946027793484104_1788946027798613937 | HTTP 200 | 52.335297 | prompt 55001, completion 1, cached 54976 = device 0, host 0, storage 54976 |
| w | TEST3060RHFINALOFFTRACE_w_1788946027793484104_1788946027800286904 | client TimeoutError | 180.103363 | response fields missing; not zero |
| q | TEST3060RHFINALOFFTRACE_q_1788946027793484104_1788946027801299149 | HTTP 200 | 108.869150 | prompt 55001, completion 1, cached 54976 = device 0, host 0, storage 54976 |

The two HTTP 200 responses had e2e latencies 52.326514 seconds (z) and
108.749959 seconds (q), one output token, and length finish reason.

## Per-RID telemetry

All five RIDs emitted exactly one storage query:

    query_suffix_len=55000
    kv_hit_pages=54976
    storage_hit_count=54976
    sidecar_hits.kv=54976
    sidecar_hits.mamba=54976

| RID | KV/Mamba probe | issue and wait/alloc/retry evidence | restore/readiness/admission |
|---|---|---|---|
| x | No pc_get_v2 KV/Mamba result or pc_l3_host emitted. | Initial attempt ...:prefetch:1, origin EAGER_RH_OFF. 122 prefetch entries: 1 eager, 121 DEMAND_RETRY; 121 declined_rate_limited, 1 issued. 121 WAIT/denied_rate_limit; HOST_ALLOC wait attempt ...:3; capacity retry revoked_alloc_failed; revoke storage_hit=54976/requested=55000/miss_reason=alloc_failed. No I/O finalize, recompute, or hybrid_discard. | No ready_host or rh_admission.v2. Plain admission can_run=0: 113564. |
| y | No pc_get_v2 KV/Mamba result or pc_l3_host emitted. | Initial attempt ...:prefetch:1, origin EAGER_RH_OFF. 122 entries: 1 eager, 121 DEMAND_RETRY; 121 declined_rate_limited, 1 issued. HOST_ALLOC wait attempt ...:1; capacity retry revoked_alloc_failed; revoke storage_hit=54976; restore_recompute cause=timeout, final_storage_survivability=host. No hybrid_discard. | No ready_host or rh_admission.v2. Plain admission can_run=0: 113586, can_run=1: 1. |
| z | 54 KV pc_get_v2 records totaling 54976; one Mamba sidecar record hit_pages.mamba=1; pc_l3_host completed_tokens=54976/requested_tokens=55000. | Initial attempt ...:prefetch:1, origin EAGER_RH_OFF. Restore PARTIAL 55000/54976 reason=shortfall; I/O finished/finalized 54976. No HOST_ALLOC wait/retry, recompute, or hybrid_discard. restore_hybrid_finalize accepted, KV 54976/54976, Mamba 1/1. | rh_ready_host.v1 emitted: attempt ...:prefetch:1, completed_kv_tokens=54976, required_aux_pools=[mamba], completed_aux_units={mamba:1}, RESTORING to READY, accepted. rh_admission.v2 emitted with same attempt, ready_host_observed=true, can_run=true. Plain admission can_run=0: 29680. |
| w | No pc_get_v2 KV/Mamba result or pc_l3_host emitted. | Initial attempt ...:prefetch:1, origin EAGER_RH_OFF. 122 entries: 1 eager, 121 DEMAND_RETRY; 121 declined_rate_limited, 1 issued. HOST_ALLOC wait attempt ...:2; capacity retry revoked_alloc_failed; revoke storage_hit=54976; no I/O finalize, recompute, or hybrid_discard. | No ready_host or rh_admission.v2. Plain admission can_run=0: 113573. |
| q | 54 KV pc_get_v2 records totaling 54976; one Mamba sidecar record hit_pages.mamba=1; pc_l3_host completed_tokens=54976/requested_tokens=55000. | Initial attempt ...:prefetch:1, origin EAGER_RH_OFF. Restore PARTIAL 55000/54976 reason=shortfall; I/O finished/finalized 54976. No HOST_ALLOC wait/retry, recompute, or hybrid_discard. restore_hybrid_finalize accepted, KV 54976/54976, Mamba 1/1. | rh_ready_host.v1 emitted: attempt ...:prefetch:1, completed_kv_tokens=54976, required_aux_pools=[mamba], completed_aux_units={mamba:1}, RESTORING to READY, accepted. rh_admission.v2 emitted with same attempt, ready_host_observed=true, can_run=true. Plain admission can_run=0: 61402, can_run=1: 1. |

No rh_preadmission.v1 record or decision was emitted for any RID. No
ready_stage.v2 record was emitted for any RID. No hybrid_discard event was
emitted. Missing is not zero.

## ON-comparison readiness

The exact five-way workload is ready for an RH-ON replay using the same 55K
payload, barrier, fresh prefix, 180-second bound, and RID correlation. The OFF
evidence supports comparison of client outcomes, wall times, storage query
hits, sidecar/restore events, allocation/retry behavior, and emitted
rh_ready_host.v1/rh_admission.v2.

It is not exact evidence for a ready-horizon preadmission comparison because
OFF emitted neither rh_preadmission.v1 nor ready_stage.v2. An ON replay must
preserve these OFF absences as missing and must not infer a preadmission rate.

## Classification, followups, and open issues

- Product defect: none established; no causal conclusion is made.
- Test defect: none in this run; timeout was exactly 180 seconds.
- Infrastructure issue: none observed; health, PID, storage, log/probe, and
  fatal checks completed.
- Missing evidence: rh_preadmission.v1, ready_stage.v2, hybrid_discard, and
  response fields for x/y/w.

Followups require a fresh Task ID: run the same bounded workload with RH-ON,
preserving missing values as missing. Any schema-specific acceptance requires a
fresh task and corresponding evidence source.

artifacts: this report; remote launch/probe log paths; captured five-RID harness output
evidence: pre/post health/PID/args/seed/offsets; exact five-way 55K run; per-RID storage, sidecar, restore, allocation, retry, recompute, readiness, and admission evidence; fatal scan
summary: RH-OFF bounded baseline completed under the required 180-second protocol; emitted telemetry collected, but required RH preadmission/ready-stage schemas were not emitted
followups: fresh Task ID for RH-ON replay or schema-specific evidence
open_issues: missing rh_preadmission.v1 and ready_stage.v2; three timed-out response fields missing; no causal diagnosis
