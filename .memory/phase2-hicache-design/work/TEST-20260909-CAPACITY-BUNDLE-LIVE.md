ENTRY: ACCEPT

# TEST-20260909-CAPACITY-BUNDLE-LIVE

```text
status: done
task_id: TEST-20260909-CAPACITY-BUNDLE-LIVE
orchestration_epoch: 20260909-P4
role: tester
target: root@i-1.gpushare.com:27460, PID 82493, 127.0.0.1:30000
verdict: FAIL for complete capacity-semantics acceptance
```

## Scope and evidence boundary

Only the live 3060 service was exercised. I made one five-request concurrent
HTTP batch and read the supplied engine/probe logs and storage metadata. I did
not touch the 3090, modify product code, restart the service, or clear/delete
storage. No durability, Ready Horizon, or fleet claim is made.

The dispatch-specified key path was absent in this environment:
`/home/dev-codex/workspaces/3rdparty/sglang_3060_ed25519`. The existing key
used for the same authorized host was
`/home/dev-codex/.ssh/sglang_3060_ed25519`; this path discrepancy is recorded
as an infrastructure assumption.

## Exact commands and timestamps

Repository instructions were read from `/home/dev-codex/workspaces/nerun-dev/AGENTS.md`.

Read-only preflight at `2026-09-09T08:17:16.779122198+08:00`:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'date --iso-8601=ns; ps -p 82493 -o pid=,ppid=,stat=,etime=,lstart=,cmd=;
   curl -sS -o /dev/null -w "%{http_code} exit=%{exitcode}\n" \
     --connect-timeout 3 --max-time 10 http://127.0.0.1:30000/health;
   stat -c "%n bytes=%s mtime=%y" /hy-tmp/hicache-qwen35-4b-p4-retry-20260909;
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -xdev -type f | wc -l;
   du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909;
   stat -c "%n bytes=%s mtime=%y" /tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log /tmp/t38c-probe.log'
```

The exact remote request harness was Python `urllib` over SSH stdin. It sent
five workers concurrently to `http://127.0.0.1:30000/generate`; for each
`ch in "xyzwq"` the payload was:

```python
{
    "rid": f"TEST20260909CAPBUNDLELIVE_{ch}_{time.time_ns()}",
    "text": (ch + " ") * 55000,
    "sampling_params": {"temperature": 0, "max_new_tokens": 1},
}
```

Batch start was `2026-09-09T08:17:49.684137+08:00`; batch end was
`2026-09-09T08:22:20.166848+08:00`; harness wall time was `270.482792 s`.
The harness used `urlopen(..., timeout=360)`, recorded monotonic HTTP wall
time, status, response JSON, and did not write a remote file.

The exact SSH invocation form was:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'python3 -' <<'PY'
# the Python harness above was supplied on stdin; it used five
# ThreadPoolExecutor workers and urllib.request.urlopen to /generate
PY
```

The final read-only check ran at `2026-09-09T08:25:10.046955440+08:00`:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'date --iso-8601=ns; ps -p 82493 -o pid=,stat=,etime=,cmd=;
   curl -sS -o /dev/null -w "%{http_code} exit=%{exitcode}\n" \
     --connect-timeout 3 --max-time 10 http://127.0.0.1:30000/health;
   du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909;
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -xdev -type f | wc -l;
   stat -c "%n bytes=%s mtime=%y" /tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log /tmp/t38c-probe.log'
```

## Runtime/storage baseline

- PID `82493` was alive, port health was `200`, and the launch profile had
  `max-running-requests=1`, `max-total-tokens=65536`, HiCache file backend,
  `wait_complete`, retry `1/120`, and restore timeout `180`.
- Pre-batch storage at `08:17:16`: `du -sb=23051071488` bytes and
  `550080` files.
- Post-batch storage at `08:25:10`: `du -sb=23051071488` bytes and
  `550080` files.
- Storage size/file count were unchanged by this batch. The service remained
  alive and health `200` after the run.

## Per-request HTTP verdicts

All five requests returned HTTP 200, `prompt_tokens=55001`, one completion
token, and `finish_reason=length`. HTTP 200 is not treated as a restore pass.

| ch | request ID | start → end (+wall s) | cached tokens | device / host / storage | verdict |
|---|---|---|---:|---|---|
| y | `TEST20260909CAPBUNDLELIVE_y_1788913069689581227` | 08:17:49.690782 → 08:18:35.448417 (+45.757691) | 54976 | 0 / 0 / 54976 (`HiCacheFile`) | PASS: restore success |
| z | `TEST20260909CAPBUNDLELIVE_z_1788913069691700839` | 08:17:49.692954 → 08:19:23.408777 (+93.715884) | 54976 | 0 / 0 / 54976 (`HiCacheFile`) | PASS: restore success |
| q | `TEST20260909CAPBUNDLELIVE_q_1788913069696975490` | 08:17:49.697761 → 08:21:20.013625 (+210.315924) | 0 | response details `null` | FAIL: positive hit timed out, then full-history result |
| x | `TEST20260909CAPBUNDLELIVE_x_1788913069685953293` | 08:17:49.687189 → 08:21:50.082045 (+240.394927) | 0 | response details `null` | FAIL: positive hit timed out, then full-history result |
| w | `TEST20260909CAPBUNDLELIVE_w_1788913069693584953` | 08:17:49.694796 → 08:22:20.165636 (+270.470910) | 0 | response details `null` | FAIL: positive hit timed out, then full-history result |

For q/x/w, `cached_tokens=0` is the final HTTP accounting after the restore
timeout; the event/log join below is the authoritative evidence of the
positive L3 query and failed capacity path.

## Request-correlated engine/probe evidence

The supplied engine log was
`/tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log` and
the supplied probe was `/tmp/t38c-probe.log`. The following event summary was
computed by read-only parsing of those files after the batch.

### y and z: successful KV+Mamba restore

Both requests had one `pc_storage_query` with:
`query_suffix_len=55000`, `kv_hit_pages=54976`, `storage_hit_count=54976`,
and `sidecar_hits={"kv":54976,"mamba":54976}`. Each issued one prefetch,
performed 55 KV `pc_get_v2` records plus one Mamba sidecar fetch, and had one
`pc_l3_host` with `completed_tokens=54976`.

- y: query `ts=1788913074.852`; Mamba sidecar hit at `1788913115.099`;
  `pc_l3_host` at `1788913115.102`; engine IO finished at
  `1788913115098`, `restore_success n_tokens=54976` at `1788913115110`.
- z: query `ts=1788913084.874`; Mamba sidecar hit at `1788913163.190`;
  `pc_l3_host` at `1788913163.192`; engine IO finished at
  `1788913163190`, `restore_success n_tokens=54976` at `1788913163196`.

Neither request had a capacity retry, revoke, recompute, hybrid discard, or
Mamba-fetch failure.

### q, x, and w: positive hit, capacity wait, no eventual restore

Each request had exactly one positive storage query with the same full
sidecar-complete frontier (`KV=54976`, `Mamba=54976`). Each had 121
`declined_rate_limited` probe outcomes and 121 `WAIT_CAPACITY` states with
`reason=PREFETCH_BUDGET`, followed by one `restore_retry cause=capacity` and
one reissued prefetch.

The reissued prefetch then failed host allocation:

```text
prefetch_revoke storage_hit=54976 requested=55000 miss_reason=alloc_failed
restore_disposition disposition=WAIT granted=54976 reason=revoked:alloc_failed
restore_state state=WAIT_CAPACITY reason=HOST_ALLOC
restore_recompute cause=timeout final_storage_survivability=host
```

Exact terminal event timestamps:

| RID suffix | positive query ts | retry / reissue ts | alloc-failed revoke ts | timeout recompute ts |
|---|---:|---:|---:|---:|
| q | 1788913124.937 | 1788913115106 / 1788913115108 | 1788913124944 | 1788913250012 |
| x | 1788913135.671 | 1788913124946 / 1788913124948 | 1788913135675 | 1788913250223 |
| w | 1788913146.400 | 1788913135677 / 1788913135679 | 1788913146405 | 1788913250223 |

For all three, probe counters showed `revoked_full_miss=0` and
`revoked_insufficient=0`; there was no `restore_recompute cause=miss`. The
positive query therefore was not genuine L3-miss evidence. Nevertheless,
`restore_recompute cause=timeout` followed by final `cached_tokens=0` is a
full-history recompute outcome for acceptance purposes.

The exact literal names `DENIED_ALLOC`, `WAIT_HOST_ALLOC`, and
`revoked_alloc_failed` were absent from the log. The deployed bundle exposed
the same semantic path as `reason=revoked:alloc_failed` and
`state=WAIT_CAPACITY reason=HOST_ALLOC` (three requests, one each); this is a
logging/schema naming gap, not evidence that the path was absent.

### Invalid crop and Mamba failure checks

- `hybrid_discard`: `0` for the request-correlated batch and `0` in the full
  supplied engine log grep.
- `Failed to fetch ...mamba`: `0` for the request-correlated batch and `0` in
  the full supplied engine log grep.
- Every `pc_storage_query` observed for this batch was sidecar-aligned at
  `54976/54976`; no shortened Mamba boundary was fetched.

## Acceptance matrix

| Criterion | Verdict | Evidence |
|---|---|---|
| Positive L3 hits avoid genuine miss | PASS narrowly | q/x/w had full KV+Mamba queries, `revoked_full_miss=0`, and no `cause=miss`. |
| Positive L3 hits avoid full-history recompute | FAIL | q/x/w all timed out in `HOST_ALLOC` wait and returned `cached_tokens=0`; only y/z restored. |
| No invalid crop or Mamba fetch failure | PASS | Zero `hybrid_discard` and zero Mamba fetch failures; all queried frontiers were sidecar-complete. |
| Prefetch issued/retry/wait behavior observable | PASS / partial | 121 budget waits and one capacity retry per q/x/w were observed. |
| Eventual KV+Mamba restore after capacity release | FAIL | y/z restored; q/x/w reissued after budget release but alloc-failed and never recovered from `HOST_ALLOC`. |
| Storage preservation | PASS | `23051071488` bytes and `550080` files both pre/post. |

## Timeout classification

No client socket timed out because the harness allowed 360 s; q/x/w instead
completed HTTP 200 only after the server's internal 180-second restore timeout.
The observed state is:

1. positive, sidecar-complete L3 query at 54,976 tokens;
2. prefetch-budget wait and a real `restore_retry cause=capacity` wake;
3. reissued allocation failure (`alloc_failed`);
4. `WAIT_CAPACITY/HOST_ALLOC` with no later retry or restore success;
5. internal timeout and final uncached completion.

This run does not prove a permanent physical capacity impossibility: the log
does not expose host-pool available/locked/evictable counters at the failed
allocation, and no lower sidecar-complete checkpoint was searched. It does
prove a liveness/state-machine failure for the acceptance scenario: after a
positive hit and `HOST_ALLOC` wait, no later capacity-release retry restored
q/x/w before timeout. Exact allocator causality remains an open debugger-deep
question, not an infrastructure or HTTP harness failure.

## Artifacts, evidence, summary, followups, open issues

Artifacts/evidence:

- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-20260909-CAPACITY-BUNDLE-LIVE.md`
- Preserved remote engine log: `/tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log`
- Preserved remote probe: `/tmp/t38c-probe.log`
- Live service remained PID `82493`, health `200` after testing.

Summary: the reviewed bundle prevented invalid shortened-frontier/Mamba
fetches and restored two of five positive L3 histories. It did not satisfy
complete capacity semantics because three positive, sidecar-complete hits
ended in `HOST_ALLOC` wait timeout and full-history recompute.

Followups (fresh Task ID required): route the `HOST_ALLOC` liveness/allocator
classification to `debugger-deep`; add/verify a stable event schema for
`DENIED_ALLOC`/`WAIT_HOST_ALLOC`; and rerun only after the resulting fix has a
fresh reviewed deployment.

Open issues:

- Exact host-pool occupancy at q/x/w allocation failure is not logged.
- Lower-frontier feasibility for q/x/w was not established.
- No durability, Ready Horizon, or fleet behavior was tested or claimed.
- Extra work requires a fresh Task ID.

Invocation handoff:

```text
status: done
artifacts: this report plus preserved remote engine/probe logs
evidence: exact live request timings, per-RID HTTP results, storage snapshots, and correlated state/trace events
summary: complete capacity-semantics acceptance FAIL; guard/Mamba safety PASS, eventual positive-hit restore FAIL for q/x/w
followups: fresh debugger-deep and fresh deployment/test Task IDs
open_issues: allocator occupancy and lower-frontier feasibility remain unobserved; no durability/RH/fleet claim
```
