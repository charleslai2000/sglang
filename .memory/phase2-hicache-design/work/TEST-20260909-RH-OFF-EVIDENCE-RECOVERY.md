ENTRY: ACCEPT

# TEST-20260909-RH-OFF-EVIDENCE-RECOVERY

```text
status: done
task_id: T3060-RH-OFF-EVIDENCE-RECOVERY-20260909
orchestration_epoch: 20260909-rh-ab8
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060
bounded_batch: 1788934855379755042
ready_horizon_during_trace: OFF
verdict: COMPLETE; existing bounded RH-OFF evidence recovered and independently verified
```

## Scope and safety

I read the repository `AGENTS.md` and the tester profile before verification. I used
the explicit key `/home/dev-codex/.ssh/sglang_3060_ed25519` for read-only SSH checks.
I did not restart or kill a service, stop a harness, send `/generate` traffic, modify
code, alter/clear seed storage, or access the 3090. The only local write from this
dispatch is this report.

The incomplete prior report `TEST-20260909-RH-OFF-TRACE.md` was present and explicitly
partial. The bounded report `TEST-20260909-RH-OFF-BOUNDED-TRACE.md` was initially absent
from the directory listing, then appeared during this verification at 14:30:28 and
matched the remote batch and RIDs below. Its client-output claims were cross-checked
against the preserved service/probe logs rather than accepted without inspection.

## Commands and observed baseline

Focused read-only commands used included:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 -o BatchMode=yes \
  -o StrictHostKeyChecking=no root@i-1.gpushare.com 'ps/pstree, ss, curl /health,
  /proc/100040/cmdline and environ, stat/find/du storage, grep/JSON event parsing'
```

The actual checks inspected the remote process tree (including harness matches),
`/tmp` log paths with mtime/size, health, storage, request RIDs, and correlated
service/probe events. No bounded harness process remained after the run.

Before and after the bounded replay, the protected seed/storage snapshot was:

```text
du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 = 23051071488 bytes
regular files = 550080
```

At the time of the replay, PID `100040` listened on `127.0.0.1:30000`, its command
line had `enable_ready_horizon=False` by omission of RH flags, and its environment
contained:

```text
SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
```

## Client outputs and per-RID telemetry

The bounded harness used five concurrent requests with text length 55,000, one output
token, and a 180-second per-request timeout. All five reached a terminal client state:

| suffix | RID terminal result | client wall time | correlated telemetry |
|---|---|---:|---|
| `w` | HTTP 200; `cached_tokens=54976`, device 0, host 0, storage 54976; `prompt_tokens=55001`; finish `length` | 49.094363 s | one storage query (`query_suffix_len=55000`, KV/storage hits 54976, KV/Mamba sidecar hits 54976); 55 KV probe batches; one host completion; service partial restore 55000 -> 54976, I/O finished, restore success/ready/finalize |
| `z` | HTTP 200; `cached_tokens=54976`, device 0, host 0, storage 54976; `prompt_tokens=55001`; finish `length` | 109.507534 s | same storage-query fields; 55 KV probe batches; one host completion; service partial restore 55000 -> 54976, I/O finished, restore success/ready/finalize |
| `x` | client `TimeoutError` at the 180-second bound; no response fields | 180.019736 s | one storage query with KV/storage/Mamba hits 54976; 244 prefetch/outcome probe records and no KV-batch/host-response records; service recorded rate-limit waits, `HOST_ALLOC`, capacity retry, revoke `alloc_failed`, and `restore_recompute cause=timeout` |
| `y` | client `TimeoutError` at the 180-second bound; no response fields | 180.102502 s | one storage query with KV/storage/Mamba hits 54976; 244 prefetch/outcome probe records and no KV-batch/host-response records; service recorded rate-limit waits, `HOST_ALLOC`, capacity retry, and revoke `alloc_failed` |
| `q` | client `TimeoutError` at the 180-second bound; no response fields | 180.079970 s | one storage query with KV/storage/Mamba hits 54976; 244 prefetch/outcome probe records and no KV-batch/host-response records; service recorded rate-limit waits, `HOST_ALLOC`, capacity retry, and revoke `alloc_failed` |

All five probe records had `pc_prefetch_enter` gate values `matched_len=0`,
`match_end=55000`, `suffix_len=55000`, and exactly one `pc_storage_query` with:

```text
query_suffix_len=55000
kv_hit_pages=54976
storage_hit_count=54976
sidecar_hits.kv=54976
sidecar_hits.mamba=54976
```

Independent raw-log counts also matched the report: service admission records were
`w=32135`, `z=66194`, `x=119997`, `y=119862`, `q=119921`; successful `w/z` each had
one `restore_success` and one `restore_ready`, while timeout rows had no successful
restore record. The service log contains the expected client-disconnect/abort records
after the three bounded client timeouts.

These observations establish bounded replay evidence, not a successful-response
latency baseline for `x`, `y`, or `q`; missing response fields remain missing and are
not treated as zero.

## Post-run checks

The preserved post-run checks completed before the later external service state change:

- PID `100040` remained alive and `/health` returned HTTP 200 at approximately
  14:24:22 and again at 14:30:20.
- Storage remained exactly `23051071488` bytes and `550080` regular files.
- The post-preflight log-delta fatal scans reported no `Traceback`, `AssertionError`,
  `OOM`, `ImportError`, `FileNotFoundError`, or `Killed` matches.
- The final service/probe logs preserved the five RIDs and the telemetry summarized
  above.

## External state change after evidence capture

At 14:37:24, after the bounded run and post-run checks, the service log recorded:

```text
SIGTERM received. signum=None frame=None. Draining requests and shutting down...
Gracefully exiting... Remaining number of requests 0.
```

I did not issue this signal. PID `100040` exited around 14:37:27. A health request
during the shutdown race returned an empty reply, followed by connection refused. The
full-log traceback found afterward is the graceful-shutdown `SystemExit: 0`/
`CancelledError` sequence, not a bounded-replay fatal event.

An external supervisor then launched PID `102147` at approximately 14:37:28. Its
command line includes `--enable-ready-horizon --ready-horizon-frontier-n 8
--hicache-prefetch-speculative-fraction 0.6`, so the current service is RH-ON, not
the RH-OFF process used for this trace. A read-only health check on PID `102147`
returned HTTP 200, and storage remained `23051071488` bytes / `550080` files.

## Evidence classification

- Product defect: none established by this recovery task. The trace records capacity
  waits, allocation-failed revokes, and three bounded client timeouts; causal diagnosis
  is outside this tester dispatch.
- Test defect: none in the bounded replay. The configured client timeout was 180 s and
  timeouts were terminal outcomes.
- Infrastructure issue: the later external SIGTERM/relaunch changed the live service
  from RH-OFF to RH-ON after evidence capture. This is not attributed to this task.
- Missing evidence: successful-response fields for `x/y/q` are unavailable by design
  because those clients timed out; their probe KV-batch/host-response records were not
  emitted. This does not invalidate the bounded trace, but prevents treating those rows
  as successful latency observations.

## Completion

```text
status: done
artifacts: TEST-20260909-RH-OFF-EVIDENCE-RECOVERY.md; existing bounded report; remote restart/service/probe logs
evidence: five terminal bounded outcomes; per-RID storage and service telemetry; unchanged seed; post-run health; clean pre-shutdown fatal scan
summary: complete RH-OFF bounded evidence recovered and independently verified; no new load issued
followups: any RH-ON comparison, RH-OFF restoration, replay, or causal debugging requires a fresh Task ID
open_issues: external restart changed the current live service to RH-ON; timeout rows lack response-level fields
```
