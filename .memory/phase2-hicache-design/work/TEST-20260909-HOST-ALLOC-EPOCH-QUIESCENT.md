# TEST-20260909-HOST-ALLOC-EPOCH-QUIESCENT

ENTRY: ACCEPT

```text
status: done
task_id: TEST-20260909-HOST-ALLOC-EPOCH-QUIESCENT
orchestration_epoch: 20260909-P4
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 90793, 127.0.0.1:30000
commit_under_test: 82ab235606233160701b15f657a71794cfd29a30
verdict: PASS for quiescent full-span KV+Mamba restore; NOT-DEMONSTRATED for generation-triggered HOST_ALLOC wake/eviction
```

## Scope and evidence boundary

This was a bounded read-only live follow-up. I used only remote HTTP requests and
read-only SSH inspection with `/home/dev-codex/.ssh/sglang_3060_ed25519`. I did
not restart the service, modify code, clear/delete/move storage, or touch the
3090. The only written artifact is this report. No contention, durability,
Ready Horizon, or fleet claim is made.

The repository instructions were read from
`/home/dev-codex/workspaces/nerun-dev/AGENTS.md`; the target sibling repository
has no additional `AGENTS.md`.

## Quiescent preflight and storage snapshot

The prior seeded five-way batch had completed before this check. Read-only
preflight at `2026-09-09T11:38:01.743656+08:00` observed PID `90793` alive,
`/health` HTTP `200`, and the seeded storage unchanged at:

```text
du -sb:      23051071488 bytes
file count:  550080
```

The service launch still used the seeded file backend directory
`/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.

The latest pre-request global `host_alloc.v1` change records were the prior
quiescence records at `ts_wall_ms=1788924562115`:

| pool | generation | evictable | free |
|---|---:|---:|---:|
| KV | 18 | 3,776 | not present in `host_allocability_change` schema |
| Mamba | 27 | 38 | not present in `host_allocability_change` schema |

The global change schema exposes generation and evictable units, but not free
units. The request-specific allocator schema is therefore the authoritative
source for free/evictable values when a `HOST_ALLOC` attempt occurs.

## Exact request and timestamps

The following read-only SSH/HTTP harness was used. It sent one request only;
the second seeded key `q` was not used because `y` was a genuine L3 hit and
completed successfully.

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'python3 -' <<'PY'
import json, time, urllib.request
rid = f"TEST20260909HOSTALLOCQUIESCENT_y_{time.time_ns()}"
payload = {"rid": rid, "text": ("y ") * 55000,
           "sampling_params": {"temperature": 0, "max_new_tokens": 1}}
req = urllib.request.Request(
    "http://127.0.0.1:30000/generate",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=360) as resp:
    print(resp.status, json.dumps(json.loads(resp.read()), sort_keys=True))
PY
```

Observed request:

```text
RID:       TEST20260909HOSTALLOCQUIESCENT_y_1788925081743642379
start:     2026-09-09T11:38:05.687742+08:00
end:       2026-09-09T11:38:42.676322+08:00
HTTP:      200
wall time: 36.988648 s
```

The post-request snapshot at `2026-09-09T11:38:42.676480+08:00` still showed
PID `90793`, health `200`, `23,051,071,488` storage bytes, and `550,080`
files. A final quiescent check at `2026-09-09T11:39:26.516027247+08:00`
again showed PID alive, health `200`, and the same storage byte/file counts.

## Request result and storage-hit evidence

The HTTP response reported:

```json
{
  "cached_tokens": 54976,
  "cached_tokens_details": {
    "device": 0,
    "host": 0,
    "storage": 54976,
    "storage_backend": "HiCacheFile"
  },
  "completion_tokens": 1,
  "finish_reason": {"length": 1, "type": "length"},
  "prompt_tokens": 55001
}
```

The request-correlated `/tmp/t38c-probe.log` records showed exactly one
storage query:

```text
query_suffix_len=55000
kv_hit_pages=54976
storage_hit_count=54976
sidecar_hits={"kv":54976,"mamba":54976}
pc_l3_host completed_tokens=54976 requested_tokens=55000
```

This was a genuine L3/file-backend hit, not a device/host hit. The probe also
recorded one full prefetch issue with `prefetch_length=55000`; the engine then
recorded:

```text
prefetch_io_finished n_tokens=54976
prefetch_finalize completed_tokens=54976 mode=cache
restore_hybrid_finalize result=accepted kv_expected=54976 kv_fetched=54976
  mamba expected=1 fetched=1 restore_state_after=READY
restore_success n_tokens=54976
```

The successful full-span chain is therefore:

```text
requested=55000 -> restored KV=54976 + Mamba=1 -> READY -> restore_success
```

## HOST_ALLOC generation/free/eviction observation

No request-correlated `restore_host_alloc_attempt`,
`restore_host_alloc_wait`, `restore_host_alloc_retry_result`, or
`host_allocability_change` record occurred during the y interval. The request
did not enter `HOST_ALLOC`; it was feasible at the quiescent allocator state
and proceeded to complete restore.

Consequently:

| Observation | Result |
|---|---|
| Full-span allocator attempt | PASS for observed 54,976-token restore; no failed HOST_ALLOC attempt was needed |
| Generation before/after request | No request-correlated change; latest global values remained KV=18 / Mamba=27 |
| Free/evictable before/after | No request-specific HOST_ALLOC snapshot; global change events expose evictable only. No change event was emitted |
| Eviction/reclaim | No host-pool reclaim event observed; no `reclaimed` allocator result exists for this request |
| Successful generation-triggered wake | NOT-DEMONSTRATED; no wait or generation wake was exercised |

The request-time promotion record did expose a successful reservation snapshot:
`full_free=320`, `full_evictable=65216`, `full_locked=0`, `mamba_free=20`,
`mamba_evictable=32`, `mamba_locked=1`. This is promotion-pool telemetry and
is not substituted for a missing `HOST_ALLOC` wait/reclaim snapshot.

## Error and recompute checks

For the unique RID, the engine log contained:

```text
restore_success:       1 (n_tokens=54976)
restore_recompute:     0
hybrid_discard:        0
Mamba fetch errors:     0 (`Failed to fetch` absent)
crop/lower checkpoint: 0 observed
```

There was no invalid shortened-frontier fallback: the KV and Mamba sidecar
hits were complete for the validated 54,976-token span.

## Acceptance classification

| Criterion | Classification | Evidence |
|---|---|---|
| Quiescent full-span restore can succeed | **PASS** | One sequential y request restored 54,976 KV tokens and one Mamba sidecar; HTTP 200; `cached_tokens=54976` |
| Positive L3/file-backend hit | **PASS** | `kv_hit_pages=54976`, `sidecar_hits={kv:54976,mamba:54976}`, storage cached tokens 54,976 |
| No hybrid/Mamba/recompute failure | **PASS** | Accepted hybrid finalize, restore success, zero discard, zero Mamba fetch error, zero recompute |
| Generation/eviction change makes a waiting request feasible | **NOT-DEMONSTRATED** | No HOST_ALLOC wait, generation wake, or reclaim occurred in this quiescent request |
| Storage/service preserved | **PASS** | PID/health remained stable; storage stayed 23,051,071,488 bytes / 550,080 files |

## Summary, followups, and open issues

Invocation status: `done`.

The bounded sanity check passes the primary quiescent restore question: a
54,976-token KV+Mamba seeded request restored successfully from L3 while idle,
with no recompute or hybrid/Mamba error. It does not demonstrate that a request
parked in `HOST_ALLOC` will wake after a later generation/eviction change,
because this request never became a waiter and no allocator generation change
was observed during it.

Artifacts/evidence:

- This report.
- Remote engine log `/tmp/sglang3060-seeded-restart-20260909.log`.
- Remote probe `/tmp/t38c-probe.log`.
- Prior seeded-batch report `TEST-20260909-HOST-ALLOC-EPOCH-SEEDED-LIVE.md`.

Followup: a successful generation-wake/eviction oracle requires a fresh Task ID
and an explicitly feasible-capacity transition scenario. No second request was
sent in this invocation.

Open issues:

- The current run does not prove HOST_ALLOC wait liveness under a later KV
  generation change.
- Global `host_allocability_change` records do not expose free units; free and
  evictable fields are available only on request-specific allocator records,
  which were not emitted because y did not enter HOST_ALLOC.
- No durability, contention, Ready Horizon, or fleet behavior was tested.
- Extra work requires a fresh Task ID.

```text
status: done
artifacts: this report plus preserved remote engine/probe logs
evidence: quiescent health/storage snapshots; one sequential L3 y request; KV/Mamba hit query; full 54976-token restore; accepted hybrid finalize; restore_success; no recompute/discard/Mamba error; no HOST_ALLOC generation/reclaim event
summary: PASS quiescent full-span restore; NOT-DEMONSTRATED generation-triggered HOST_ALLOC wake/eviction
followups: fresh feasible-capacity epoch test only if a wake oracle is required
open_issues: HOST_ALLOC wait liveness and free-unit global telemetry remain unobserved; no durability/RH/fleet claim; extra work requires fresh Task ID
```
