# TEST-20260909-HOST-ALLOC-EPOCH-LIVE

ENTRY: ACCEPT

status: blocked
task_id: TEST-20260909-HOST-ALLOC-EPOCH-LIVE
orchestration_epoch: 20260909-P4
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 87794, 127.0.0.1:30000
commit_under_test: 82ab235606
verdict: BLOCKED — live service was not using the authorized seeded storage directory

## Scope and evidence boundary

The required five-request live batch was executed with read-only SSH inspection and
HTTP requests only. I did not modify product code, restart the service, clear/delete
storage, or touch the 3090. The only local write is this report. No durability, Ready
Horizon, or fleet claim is made.

The deployment identity was checked by the seven remote SHA-256 values in the deploy
report; the live values matched:

```text
schedule_batch.py                 9efd9159fa3491a3758d13dc2f751c4d9cf2e9fe726ca30238684b0014ddb7b6
scheduler.py                      ffda8d1b247195650924a059b3a0fdb1d38d670547810043021136d95559a249
hicache_restore.py                6300bb521fd684d28cd9ec94627b4f51b31ad582bc0ed4e04024b821b1012dd1
hybrid_cache_controller.py        afa00fcc921ab78a46aa96fec5a1f3232eaaab3eaea9eec7bab53795b6a407d7
hybrid_pool_assembler.py           bac2bd08b91897e608a9cd1df215c4b278d03d3227587eac38654d441a185633
pool_host/group.py                 beace6d3c6a92dcfb424794267e9cb33a346cea04b2918bf9588d438fb78f20f
unified_radix_cache.py             46621e8a09df9bafdc9dd3aab83f19f9d7cb36831ef8a6d25758b86e67de2e1b
```

## Exact commands and timestamps

All timestamps below are remote `Asia/Shanghai` time.

Preflight at `2026-09-09T11:09:13.130911093+08:00`:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'date --iso-8601=ns; ps -p 87794 -o pid=,ppid=,stat=,etime=,lstart=,cmd=;
   curl -sS -o /dev/null -w "health_http=%{http_code} exit=%{exitcode}\n" \
     --connect-timeout 3 --max-time 10 http://127.0.0.1:30000/health;
   stat -c "%n bytes=%s mtime=%y" \
     /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 \
     /tmp/sglang3060-host-alloc-final-20260909.log /tmp/t38c-probe.log;
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -xdev -type f | wc -l;
   du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909'
```

Observed: PID `87794` was alive, health `200`, target storage was
`23051071488` bytes and `550080` files.

The exact HTTP command was:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'python3 -' <<'PY'
import concurrent.futures, json, time, urllib.request
import urllib.error
from datetime import datetime, timezone
url = "http://127.0.0.1:30000/generate"
batch_tag = "TEST20260909HOSTALLOCEPOCHLIVE"
started = datetime.now().astimezone().isoformat(timespec="microseconds")
mono0 = time.monotonic()
def one(ch):
    rid = f"{batch_tag}_{ch}_{time.time_ns()}"
    payload = {"rid": rid, "text": (ch + " ") * 55000,
               "sampling_params": {"temperature": 0, "max_new_tokens": 1}}
    body = json.dumps(payload).encode()
    t0 = time.monotonic(); wall0 = datetime.now().astimezone().isoformat(timespec="microseconds")
    out = {"ch": ch, "rid": rid, "start": wall0}
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            out.update({"http": resp.status,
                        "end": datetime.now().astimezone().isoformat(timespec="microseconds"),
                        "wall_s": round(time.monotonic()-t0, 6),
                        "response": json.loads(resp.read())})
    except Exception as e:
        out.update({"http": getattr(e, "code", None),
                    "end": datetime.now().astimezone().isoformat(timespec="microseconds"),
                    "wall_s": round(time.monotonic()-t0, 6), "error": repr(e)})
    return out
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    results = list(ex.map(one, "xyzwq"))
print(json.dumps({"batch_start": started,
                  "batch_end": datetime.now().astimezone().isoformat(timespec="microseconds"),
                  "wall_s": round(time.monotonic()-mono0, 6),
                  "results": results}, sort_keys=True))
PY
```

Batch start was `2026-09-09T11:09:33.845177+08:00`; batch end was
`2026-09-09T11:12:13.502419+08:00`; harness wall time was `159.657298 s`.

Postflight at `2026-09-09T11:12:34.435676846+08:00` found PID `87794` alive,
health `200`, target storage still `23051071488` bytes / `550080` files,
engine log `/tmp/sglang3060-host-alloc-final-20260909.log`, and probe
`/tmp/t38c-probe.log`. The postflight command was:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'date --iso-8601=ns; ps -p 87794 -o pid=,stat=,etime=,cmd=;
   curl -sS -o /dev/null -w "health_http=%{http_code} exit=%{exitcode}\n" \
     --connect-timeout 3 --max-time 10 http://127.0.0.1:30000/health;
   du -sb /hy-tmp/hicache-qwen35-4b-p4-retry-20260909;
   find /hy-tmp/hicache-qwen35-4b-p4-retry-20260909 -xdev -type f | wc -l;
   stat -c "%n bytes=%s mtime=%y" \
     /tmp/sglang3060-host-alloc-final-20260909.log /tmp/t38c-probe.log'
```

## Per-request HTTP matrix

All responses were HTTP 200 with `prompt_tokens=55001`, `completion_tokens=1`,
and `finish_reason=length`. None was a cache restore.

| key | request ID | start | end | wall seconds | cached tokens | final result |
|---|---|---|---|---:|---:|---|
| x | `TEST20260909HOSTALLOCEPOCHLIVE_x_1788923373846961442` | 11:09:33.848168 | 11:10:33.870294 | 60.022195 | 0 | full recompute |
| y | `TEST20260909HOSTALLOCEPOCHLIVE_y_1788923373850076599` | 11:09:33.851271 | 11:10:03.749682 | 29.898473 | 0 | full recompute |
| z | `TEST20260909HOSTALLOCEPOCHLIVE_z_1788923373852272174` | 11:09:33.853260 | 11:11:04.329398 | 90.476215 | 0 | full recompute |
| w | `TEST20260909HOSTALLOCEPOCHLIVE_w_1788923373853977060` | 11:09:33.855160 | 11:11:35.688733 | 121.833629 | 0 | full recompute |
| q | `TEST20260909HOSTALLOCEPOCHLIVE_q_1788923373857271558` | 11:09:33.858413 | 11:12:13.501367 | 159.643031 | 0 | full recompute |

Final cached-token breakdown: `5/5` requests had `cached_tokens=0`; therefore
`0/5` device, host, or storage cached tokens were reported. This is consistent
with the request-correlated probe queries below.

## Request-correlated engine/probe evidence

Every request reached a storage query, but every query was a genuine miss:
`kv_hit_pages=0`, `storage_hit_count=0`, and `sidecar_hits={}`. Counts from the
request-tagged probe records were:

| key | `pc_storage_query` | `pc_outcome` issued | `declined_rate_limited` | `revoked_full_miss` | positive KV/Mamba hit |
|---|---:|---:|---:|---:|---|
| x | 14 | 14 | 1 | 14 | no |
| y | 1 | 1 | 0 | 1 | no |
| z | 29 | 29 | 2 | 29 | no |
| w | 29 | 29 | 93 | 29 | no |
| q | 54 | 54 | 1 | 54 | no |

The engine emitted `restore_recompute cause=miss` `127` times for these RIDs,
including the terminal recompute for each request. It emitted no tagged
`restore_success`. Four RIDs (x, z, w, q) had one `restore_retry cause=capacity`
while waiting on `PREFETCH_BUDGET`, but the subsequent attempts were still
`storage_hit=0 miss_reason=miss`; no RID reached `HOST_ALLOC`.

Safety/error observations for this batch:

```text
tagged hybrid_discard:       0
tagged Mamba fetch errors:   0
tagged restore_success:      0
tagged HOST_ALLOC states:    0
tagged restore_recompute timeout: 0
tagged restore_recompute miss: 127
```

The absence of `hybrid_discard` and Mamba fetch errors is a safety observation
on the genuine-miss path, not evidence of a successful hybrid restore.

## host_alloc.v1 telemetry

The engine log contained `68` global `host_alloc.v1` (`[HAE]`) records:

```text
pools:  mamba=48, kv=20
causes: queued_release_drain=16, lock_release_evictable=20, direct_free=32
```

All 68 had `rid=null` and `causal_rid=null`; none joined any of the five test
RIDs. They carried generation and evictable snapshots, for example a KV
`lock_release_evictable` transition `generation_before=46` to `47`,
`evictable_before=2048` to `3776`, `returned_units=0`, and a later transition
`generation_before=74` to `75` with the same evictability change. No
request-correlated `required`, `free`, `failed_domains`, HOST_ALLOC grant/skip,
or HOST_ALLOC wake/retry record was emitted because the batch never entered the
HOST_ALLOC state.

## Deployment/configuration blocker

The requested seeded directory was not the live backend directory. The launch
`server_args` line records `hicache_storage_backend='file'` and
`file_storage_path='sglang_storage'`, while `/proc/87794/environ` contained no
`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` override. Read-only path inspection
at `2026-09-09T11:15:53.783772082+08:00` found:

```text
/tmp/hicache                                      11551940608 bytes, 275080 files
/hy-tmp/hicache-qwen35-4b-p4-retry-20260909        23051071488 bytes, 550080 files
```

The target directory's mtime and occupancy were unchanged by the batch. The
deployed HiCacheFile implementation uses the storage-dir environment override
or its `/tmp/hicache` default; the live process had neither the required target
override nor a request-visible configuration selecting the authorized seeded
directory. The all-zero query hits and active `/tmp/hicache` contents are
therefore classified as a deployment/configuration issue, not as evidence that
the final commit's HOST_ALLOC logic failed.

## Acceptance matrix

| Gate | Verdict | Evidence / classification |
|---|---|---|
| No invalid crop / no Mamba fetch failure | PASS, limited | Zero `hybrid_discard` and zero tagged Mamba fetch failures; positive-hit branch was not exercised. |
| Positive L3 hit has no genuine miss | BLOCKED / observed FAIL | All five queries were genuine misses (`0/0/{}`); the positive-hit precondition was absent because the live backend did not use the seeded directory. |
| No same-request self-wake | BLOCKED / not exercised | No test RID entered HOST_ALLOC; HAE records were global with null RID identity. |
| HOST_ALLOC generation wake eventually retries full span and restores KV+Mamba | BLOCKED / not exercised | No HOST_ALLOC grant/skip, required/free/evictable request snapshot, or positive KV+Mamba restore was observed. |
| No timeout/full-history recompute attributable to waiting | PASS for observed path only | Terminal recomputes were `cause=miss`, not `cause=timeout`; this does not validate positive-hit waiting behavior. |
| Storage preservation | PASS | Target remained `23051071488` bytes / `550080` files before and after. |

## Artifacts, summary, followups, open issues

Artifacts/evidence:

- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-20260909-HOST-ALLOC-EPOCH-LIVE.md`
- Remote engine log: `/tmp/sglang3060-host-alloc-final-20260909.log`
- Remote probe: `/tmp/t38c-probe.log`
- Deployment identity and seven-file hashes: `OPS-20260909-DEPLOY-HOST-ALLOC-FINAL.md`

Summary: the final bundle was live and healthy, but the required seeded L3
scenario could not be independently validated. The service queried the wrong
storage directory, produced five genuine misses, and never exercised the
HOST_ALLOC epoch path. This is a real deployment/configuration blocker; it is
not a product verdict on the HOST_ALLOC implementation.

Followups require a fresh Task ID: deploy/restart the same reviewed bundle with
`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`
or the reviewed equivalent, then repeat exactly the five-key batch and require
positive `pc_storage_query` KV+Mamba hits before judging HOST_ALLOC behavior.

Open issues:

- No request-correlated HOST_ALLOC telemetry was available in this run, so
  required/free/evictable/gen feasibility and wake classification remain open.
- The five HTTP responses are valid service responses but are invalid evidence
  for the positive-hit acceptance scenario.
- No physical-capacity impossibility claim is made.
- Extra work requires a fresh Task ID.
