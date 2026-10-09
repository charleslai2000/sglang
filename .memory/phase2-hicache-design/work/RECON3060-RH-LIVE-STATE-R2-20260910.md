# 3060 Ready-Horizon live-state recon — R2

Scope: read-only remote inspection only. No remote/repository mutations, process control, deployment, or trace launch were performed by this worker.

## Decision

**Do not launch a new live blocker+A/B trace now.** A concurrent noninteractive SSH actor was actively driving a long-context two-request Ready-Horizon trace during this inspection, and its service telemetry advanced through the target RH lifecycle. The actor then externally terminated/relaunched the service, so the trace is **just-run/interrupted rather than demonstrably cleanly complete** from the readable artifacts. Coordinate with that actor and preserve/review the existing telemetry before considering another run.

Most relevant evidence:

- `/tmp/sglang3060-rh-fix-4f41f5.log` — continuously appended during inspection; contains RH state and admission evidence.
- `/tmp/t38c-probe.log` — continued growing through 05:51:40 CST (4,279,678 bytes at final stat).
- `/tmp/b15-probe.log` — last write 05:50:56 CST (1,946,024 bytes at final stat).
- `/hy-tmp/hicache-restore-r3/` — 12G HiCache restore namespace, files last written 05:47:36 CST.

## Observed service state

### Initial service snapshot (approximately 05:49–05:51 CST)

- Health: HTTP `200`, three consecutive checks.
- SGLang master: PID `173342`, started `Thu Sep 10 05:39:03 2026`.
- Command line:

```text
/root/sglang-env-3060-4b/bin/python -m sglang.launch_server --model-path /hy-tmp/models/Qwen3.5-4B-AWQ --tokenizer-path /hy-tmp/models/Qwen3.5-4B-AWQ --host 127.0.0.1 --port 30000 --tp-size 1 --mem-fraction-static 0.82 --max-running-requests 1 --max-total-tokens 65536 --chunked-prefill-size 2048 --max-prefill-tokens 16384 --kv-cache-dtype fp8_e4m3 --enable-hierarchical-cache --hicache-host-memory-mode cache --hicache-ratio 2.0 --hicache-write-policy write_through --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-storage-backend file --hicache-storage-prefetch-policy wait_complete --hicache-storage-backend-extra-config {"hicache_storage_pass_prefix_keys":true} --hicache-prefetch-speculative-fraction 0.6 --cuda-graph-backend-decode full --cuda-graph-backend-prefill breakable --cuda-graph-bs-decode 1 --cuda-graph-bs-prefill 4 8 16 32 --enable-ready-horizon --ready-horizon-frontier-n 8
```

- RH-on/c1 profile confirmation: `--enable-ready-horizon`, `--ready-horizon-frontier-n 8`, and `--max-running-requests 1`; hierarchical HiCache with file storage backend, `wait_complete` prefetch policy, and supplied extra config.

### Final service snapshot (approximately 05:52 CST)

- The original deploy log records an externally initiated `SIGTERM` at `05:51:52`, graceful exit at `05:51:56`, and `kill_process_tree ... parent_pid=173342` at `05:51:57`.
- A new same-command-line SGLang master, PID `176538`, started at `Thu Sep 10 05:52:00 2026`.
- Final three health checks were all `000` while PID 176538 was still initializing. This is a startup observation, not a service-failure diagnosis.

### Deploy/commit lineage

- The original PID start time exactly aligns with the reported restart time and `/tmp/sglang3060-rh-fix-4f41f5.log` begins SGLang initialization at 05:39:16.
- The log reports first health `200` at 05:40:06 and `The server is fired up and ready to roll!` at 05:40:04.
- The process uses `/root/sglang-3060-12g-hicache`, matching the stated deployed checkout.
- The checkout is not a Git repository and the readable deploy log has no literal `4f41f5`/Git line. Thus the process-to-deploy time/log lineage and RH profile match are observed; cryptographic verification of the exact source commit from the remote host is **not established**.

## Deploy-log excerpts

`/tmp/sglang3060-rh-fix-4f41f5.log` had 12,802 lines at the first read and was 8,968,973 bytes while the trace was active (it is a live server log, so counts changed during inspection).

Head (representative):

```text
[2026-09-10 05:39:16] Attention backend not specified. Use flashinfer backend by default.
[2026-09-10 05:39:18] server_args={... 'mem_fraction_static': 0.82, 'max_running_requests': 1, 'max_total_tokens': 65536, 'chunked_prefill_size': 2048, 'max_prefill_tokens': 16384, ...}
[2026-09-10 05:39:43] Load weight end. elapsed=4.09 s, type=Qwen3_5ForConditionalGeneration, quant=compressed-tensors, avail mem=7.77 GB, mem usage=3.85 GB.
[2026-09-10 05:39:46] KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 65536, K size: 0.50 GB, V size: 0.50 GB
[2026-09-10 05:40:04] The server is fired up and ready to roll!
[2026-09-10 05:40:06] INFO: 127.0.0.1:53694 - "GET /health HTTP/1.1" 200 OK
```

Tail captured shortly after trace activity:

```text
[2026-09-10 05:51:50] ... evt=admission.v2 ... rid=HEALTH_CHECK_... can_run=true
[2026-09-10 05:51:52] SIGTERM received. signum=None frame=None. Draining requests and shutting down...
[2026-09-10 05:51:56] Gracefully exiting... Remaining number of requests 0. Remaining requests remaining_rids=[].
[2026-09-10 05:51:57] ERROR: Traceback ... SystemExit: 0
[2026-09-10 05:51:57] kill_process_tree called: parent_pid=173342, include_parent=False, pid=173342
```

The `SystemExit`/`CancelledError` tail follows the intentional SIGTERM; it is not evidence of an OOM or overlay-full error.

## Concurrent blocker+A/B horizon-trace evidence

### Active driver/liveness during inspection

At the first liveness capture:

```text
PID 175796  sshd: root@notty     started Thu Sep 10 05:48:44
PID 175825  /root/sglang-env-3060-4b/bin/python -   started Thu Sep 10 05:48:45
```

- PID `175825` had cwd `/root/sglang-3060-12g-hicache` and was parented directly by the noninteractive SSH session. It was the only non-SGLang external Python process.
- It disappeared before a later process capture, consistent with the concurrently observed trace/restart transition. A different `root@notty` SSH session appeared around the service restart.
- No assertion is made about the remote actor's identity or intent beyond these observed process facts.

### Proof of active trace and RH progression

Live growth check over five seconds:

```text
/tmp/t38c-probe.log: 3,706,687 -> 3,707,685 bytes (05:50:16 -> 05:50:20)
/tmp/b15-probe.log: 1,939,108 bytes, last modified 05:49:46 during that interval
```

Subsequent final stats:

```text
/tmp/t38c-probe.log       05:51:40  4,279,678 bytes
/tmp/b15-probe.log        05:50:56  1,946,024 bytes
/tmp/sglang3060-rh-fix-4f41f5.log 05:51:40 8,968,973 bytes
```

The current deploy log contains a two-request frontier at about 55K tokens:

```text
05:49:23  rid=234194... frontier_rank=1 frontier_n=2 ... spec_budget=55164
05:49:23  rid=edf50c... frontier_rank=2 frontier_n=2 ... spec_budget=55164
05:49:25  ... spec_budget=0; rid=234194... restore_state=WAIT_CAPACITY, wait_reason=HOST_ALLOC
05:49:46  ... host_release=1, spec_budget=0
05:49:58  ... host_release=2, spec_budget=0
05:50:06  ... host_release=3, spec_budget=0
05:50:34  evt=ready_host rid=234194... attempt_id=...:prefetch:2 issue_origin=DEMAND_RETRY completed_kv_tokens=55104 restore_state_after=READY finalize_result=accepted
05:50:34  evt=rh_preadmission_decision rid=234194... restore_state_before=READY ... host_release=4, spec_budget=0
05:50:56  evt=admission.v2 rid=234194... ready_host_observed=true can_run=true
```

This demonstrates that one participant woke/retried after speculative budget release, became Host-ready, had a READY preadmission state, and was admitted with `ready_host_observed=true`.

However, the second request (`edf50c...`) has an observed line:

```text
[2026-09-10 05:50:26] [P2A] evt=restore_recompute rid=edf50c... cause=timeout final_storage_survivability=host
```

Therefore, from this read-only snapshot, the required clean acceptance claim that *the specifically intended request B* avoided both `cached=0` and full-history recompute is **not established**. Request labels A/B are not present in the readable process/log evidence, and the trace was interrupted by a concurrent service restart. Do not treat the existing observations as a fully clean, complete acceptance artifact without the concurrent driver's own driver/join output.

### Existing older artifacts

Newest relevant entries before the active run:

```text
/tmp/sglang3060-rh-horizon-r1/on.log   last write 05:39:00, 338,832 bytes
/tmp/sglang3060-rh-horizon-r1/off.log  last write 04:28:43, 3,320,889 bytes
/tmp/sglang3060-rh-queue-r1/on.log     last write 04:26:46, 68,595 bytes
/tmp/t38c-durable-trace                directory mtime 04:08:31
```

The `horizon-r1/on.log` and `queue-r1/on.log` tails show a prior intentional SIGTERM/SystemExit shutdown, not a currently active run.

No `/root/evidence*` or `/root/sglang3060*` evidence namespace matching the requested recent window was found. `/hy-tmp/hicache-restore-r3` was actively touched at 05:47:36, but it is a HiCache storage namespace rather than a named driver/join-report directory.

## Disk, memory, and OOM sanity

Observed:

```text
/       overlay       30G total, 17G used, 14G available, 54% used
/hy-tmp /dev/nvme0n1  50G total, 50G used, 196K available, 100% used
memory: 125Gi total, 102Gi available; swap 0
memory PSI: avg10/avg60/avg300 = 0.00 for both some/full
kernel OOM/overlay/no-space grep: no matching lines returned
inodes: 4% used on both mounts
/hy-tmp/hicache-restore-r3: 12G
```

**Important operational condition:** `/hy-tmp` is filesystem-full (196K free), even though no kernel OOM/overlay-full event was found and `/` has 14G free. This worker performed no cleanup or corrective action.

## Classification

- **Was a blocker+A/B horizon trace running?** Yes, during the main inspection interval (live SSH Python driver, growing probe/server logs, 55K two-request RH telemetry).
- **Is it currently still running?** The observed driver exited and the original server was SIGTERM'd/relaunched; no active external Python driver remained in the final process capture.
- **Was it already cleanly completed?** Not proven. The trace shows strong partial/near-acceptance evidence for one request, but also a `restore_recompute` for the other request and an interruption/restart before a readable driver/join conclusion.
- **Should a new trace be launched now?** No. Treat this as a concurrent just-run/interrupted trace and coordinate with the actor; the single GPU is also in a service-restart state and `/hy-tmp` is full.

## Evidence commands (read-only)

- SSH health retries with `curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:30000/health`
- `ps -eo pid,ppid,lstart,etimes,args` for SGLang, Python, SSH, and driver lineage
- `head`, `tail`, line-oriented `grep`, `stat`, and `find` over the designated `/tmp`, `/root`, and `/hy-tmp` artifact locations
- `df -h`, `df -hi`, `free -h`, `/proc/pressure/memory`, and read-only `dmesg` query

status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/RECON3060-RH-LIVE-STATE-R2-20260910.md
evidence:
- Remote health/process/log/probe/artifact/disk snapshots summarized above.
summary:
- A concurrent actor ran a live ~55K two-request RH trace, which reached Host-ready and RH admission for one request; it then exited/restarted the service. Do not launch another trace without coordination. The clean complete B-specific acceptance remains unproven from read-only artifacts.
followups:
- Obtain the concurrent actor's driver/join output and correlate A/B identities with request IDs before acceptance determination.
- Wait for/recheck the replacement master after its initialization window, without colliding with the actor.
- Treat /hy-tmp 100%-full status as a stop condition for any future trace that might write HiCache data; remediation requires explicit authorization and an executor.
open_issues:
- Exact source-commit identity cannot be cryptographically established because the remote checkout is non-Git and the deploy log contains no literal commit reference.
- No readable completed driver/join artifact establishes the no-cached=0/no-full-history-recompute condition for the intended request B.
- Replacement PID 176538 was not yet healthy at the final snapshot.
