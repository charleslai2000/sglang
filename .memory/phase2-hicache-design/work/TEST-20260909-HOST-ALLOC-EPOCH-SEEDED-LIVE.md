# TEST-20260909-HOST-ALLOC-EPOCH-SEEDED-LIVE

ENTRY: ACCEPT

```text
status: done
task_id: TEST-20260909-HOST-ALLOC-EPOCH-SEEDED-LIVE
orchestration_epoch: 20260909-P4
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 90793, 127.0.0.1:30000
commit_under_test: 82ab235606233160701b15f657a71794cfd29a30
verdict: PASS for seeded positive-hit safety and capacity classification; conditional HOST_ALLOC liveness not demonstrated because x/w/q remained physically infeasible
```

## Scope and evidence boundary

This was an independent live verification using only HTTP requests and
read-only SSH inspection with `/home/dev-codex/.ssh/sglang_3060_ed25519`. I did
not modify product code, restart the service, clear/delete/move storage, or
touch the 3090. The only local artifact written by this task is this report.
No durability, Ready Horizon, or fleet claim is made.

The repository instructions were read from
`/home/dev-codex/workspaces/nerun-dev/AGENTS.md`; the target sibling repository
has no additional `AGENTS.md`.

## Deployment and seeded-storage precondition

Read-only preflight at `2026-09-09T11:24:29.779888423+08:00` observed:

- PID `90793` alive (`Sl`), listening on port `30000`; `/health` returned HTTP
  200.
- `/proc/90793/environ` contained
  `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Launch log `/tmp/sglang3060-seeded-restart-20260909.log` recorded file-backend
  creation and application startup completion.
- The seven deployed source hashes matched the OPS report for commit
  `82ab235606`; no source drift was observed.

Seeded storage snapshots:

| Snapshot | Bytes | Files |
|---|---:|---:|
| Pre-batch, 11:24:29 | 23,051,071,488 | 550,080 |
| Post-batch, 11:29:31 | 23,051,071,488 | 550,080 |

The service remained PID `90793` and health HTTP 200 after the batch. The
preserved remote evidence files were:

```text
/tmp/sglang3060-seeded-restart-20260909.log
  sha256 c1a8803e2e999d010009504cd158f38dcb9b3f62bab0ed20105ce808bcb9b09e
/tmp/t38c-probe.log
  sha256 8ef3b48002f5a7d3f04375edeabd023577795856f35fc930234bda494dc42bad
```

## Exact live request

Five concurrent POST requests were sent to
`http://127.0.0.1:30000/generate`, one for each `x y z w q`, with:

```python
{"rid": "TEST20260909HOSTALLOCEPOCHSEEDEDLIVE_<ch>_<unique_ns>",
 "text": (ch + " ") * 55000,
 "sampling_params": {"temperature": 0, "max_new_tokens": 1}}
```

Batch start was `2026-09-09T11:24:51.629676+08:00`; batch end was
`2026-09-09T11:29:22.196350+08:00`; harness wall time was `270.566735 s`.
The client timeout was 360 seconds. All requests returned HTTP 200,
`prompt_tokens=55001`, one completion token, and `finish_reason=length`.

| Key | Request ID suffix | Wall seconds | Final `cached_tokens` | Final result |
|---|---|---:|---:|---|
| x | `..._x_1788924291631462476` | 210.170025 | 0 | positive hit, HOST_ALLOC wait, timeout recompute |
| y | `..._y_1788924291634432658` | 103.688058 | 54,976 | KV+Mamba storage restore |
| z | `..._z_1788924291635914380` | 47.942283 | 54,976 | KV+Mamba storage restore |
| w | `..._w_1788924291637324449` | 240.333368 | 0 | positive hit, HOST_ALLOC wait, timeout recompute |
| q | `..._q_1788924291638535394` | 270.556143 | 0 | positive hit, HOST_ALLOC wait, timeout recompute |

Final served cache breakdown was device `0`, host `0`, storage `109,952`
tokens across y/z, with x/w/q serving `cached_tokens=0` and
`cached_tokens_details=null` after timeout fallback. The underlying probe
shows that x/w/q were positive storage queries but did not consume the hit.

## Request-correlated L3 and restore evidence

Every one of the five RIDs had exactly one `pc_storage_query`:

```text
query_suffix_len=55000
kv_hit_pages=54976
storage_hit_count=54976
sidecar_hits={"kv":54976,"mamba":54976}
```

Therefore the positive-L3, KV+Mamba-complete precondition was observed for all
five requests; there were no misses to classify.

Successful restores:

- z: one prefetch, `prefetch_io_finished n_tokens=54976`, hybrid finalize
  `kv_expected=54976 kv_fetched=54976 mamba expected=1 fetched=1`,
  `restore_success n_tokens=54976`.
- y: the same complete KV+Mamba chain, followed by
  `restore_success n_tokens=54976`.

Capacity-classified requests x/w/q each had:

- 121 `WAIT_CAPACITY/PREFETCH_BUDGET` states and one `restore_retry
  cause=capacity`.
- One full `prefetch_length=55000` issue, followed by
  `prefetch_revoke storage_hit=54976 requested=55000 miss_reason=alloc_failed`.
- One `restore_host_alloc_retry_result` with `full_frontier_tokens=54976`,
  `retry_outcome=revoked_alloc_failed`, `genuine_miss=false`,
  `lower_checkpoint_queried=false`, and `crop_attempted=false`.
- One `WAIT_CAPACITY reason=HOST_ALLOC` state with the prefetch reservation
  released, then one `restore_recompute cause=timeout`.

The request-specific allocator snapshots were:

| RID | FIFO | Captured generations | Failed domains | KV required/free/evictable | Mamba required/free/evictable |
|---|---:|---|---|---:|---:|
| x | 0 | `kv=0,mamba=1` | `kv,mamba` | `54976 / 21057 / 0` | `1 / 104 / 0` |
| w | 1 | `kv=0,mamba=2` | `kv,mamba` | `54976 / 21057 / 0` | `1 / 104 / 0` |
| q | 2 | `kv=0,mamba=3` | `kv,mamba` | `54976 / 21057 / 0` | `1 / 104 / 0` |

These snapshots classify x/w/q as physically insufficient for the requested
complete 54,976-token primary-host allocation at their allocator attempts:
KV was short by 33,919 units and had zero evictable units. Mamba had enough
free units for its auxiliary requirement; its inclusion in `failed_domains`
reflects the all-or-nothing composite allocation path, not a Mamba fetch
error.

## HOST_ALLOC epoch and wake evidence

The deployed `host_alloc.v1` telemetry recorded three request allocator
attempts, three HOST_ALLOC wait snapshots, and nine wake-decision snapshots.
The full-frontier attempts occurred for x/w/q at mamba generations 1/2/3,
respectively. All had `retry_grant=true` for the allocator attempt but failed
the complete primary-host allocation, then parked with `retry_grant=false`.

Subsequent wake decisions were bounded and non-self-waking:

- x/w/q were assigned FIFO sequence 0/1/2.
- All wake decisions had `retry_skip=true` and `global_grant_used=false`.
- Decisions were `hold_no_generation` or `hold_budget`; no request was granted
  a second allocation attempt from its own cleanup.
- During the wait interval, Mamba allocability advanced through direct-free
  generations 1 -> 2 -> 3, while the relevant KV generation remained 0 and
  KV free/evictable stayed `21057/0`. Thus no complete KV+Mamba allocability
  change occurred that could make the 54,976-token request feasible.
- Later KV `direct_free` generation changes occurred after the x/w/q timeout
  cleanup, not before their restore deadlines.

This is evidence that the epoch telemetry and FIFO/no-self-wake guards were
active. It is not evidence of a successful post-wait HOST_ALLOC retry, because
the observed capacity changes were Mamba-only while KV remained physically
insufficient.

## Safety and miss-separation checks

For every positive-hit RID:

- `revoked_full_miss` maximum was 0.
- `revoked_insufficient` maximum was 0.
- The request allocator result recorded `genuine_miss=false`.
- No lower checkpoint was queried.
- No crop was attempted.
- Tagged `hybrid_discard` count was 0.
- Tagged Mamba fetch-error count (`Failed to fetch`) was 0.

The successful y/z probe paths each recorded 55 KV `pc_get_v2` records and a
sidecar-complete `pc_l3_host` record. x/w/q never reached a Mamba fetch because
the composite host allocation failed first.

## Acceptance matrix

| Criterion | Result | Evidence / classification |
|---|---|---|
| Positive L3 precondition for each request | PASS | All five had KV=54,976 and Mamba=54,976 storage queries. |
| No invalid crop or Mamba fetch error | PASS | Zero crop attempts, `hybrid_discard`, and Mamba fetch errors. |
| No genuine miss for a positive hit | PASS | x/w/q had `genuine_miss=false`, no full-miss counter, and `alloc_failed` only. |
| Full-span HOST_ALLOC allocator attempt | PASS | x/w/q each attempted the full 54,976-token frontier; no crop/lower checkpoint. |
| Generation wake after a feasible allocability change | NOT DEMONSTRATED | Only Mamba generations changed while KV remained `free=21057`, `evictable=0`; no complete feasible epoch occurred. |
| Feasible requests eventually restore KV+Mamba | PASS for observed feasible requests | y/z both restored all 54,976 KV tokens and one Mamba sidecar. |
| No timeout/full-history recompute for a feasible request | PASS for observed feasible requests | y/z had no timeout or recompute; x/w/q were explicitly capacity-infeasible at the snapshots. |
| Storage preservation and service health | PASS | Bytes/files unchanged; PID alive and health 200 post-run. |

## Verdict, artifacts, and open issues

The seeded live precondition is now valid and the positive-hit safety path is
verified. Two of five requests restored complete KV+Mamba state. Three entered
the new HOST_ALLOC state with exact telemetry proving insufficient KV capacity
at the full requested frontier; they timed out after bounded hold decisions,
without genuine-miss classification, crop, or Mamba-fetch failure.

Accordingly this invocation is `done`: the acceptance evidence is complete for
the observed seeded run, with a capacity-qualified result. It does not provide
a successful liveness proof for a later epoch in which KV capacity becomes
feasible. No claim is made that the observed shortage is permanently
impossible; only the exact point-in-time free/evictable telemetry is claimed.

Artifacts/evidence:

- This report.
- Remote engine log `/tmp/sglang3060-seeded-restart-20260909.log`.
- Remote probe `/tmp/t38c-probe.log`.
- Deployment/restart evidence in `OPS-20260909-RESTART-SEEDED-HOST-ALLOC.md`.

Followups require a fresh Task ID: run a deliberately feasible allocability-
change scenario (or a run whose complete KV host span becomes available before
the restore deadline) if a positive successful HOST_ALLOC generation-wake
oracle is required.

Open issues:

- This run cannot distinguish a later possible KV release from permanent host
  pressure; it only proves the observed KV shortage and zero evictability.
- x/w/q timeout recomputes are attributable to waiting after the observed
  allocation failure, but those requests were not feasible under the recorded
  full-span snapshot.
- No durability, Ready Horizon, or fleet behavior was tested.
- Extra work requires a fresh Task ID.

Invocation handoff:

```text
status: done
artifacts: this report plus preserved remote engine/probe logs
evidence: seeded backend precondition, exact storage snapshots, five positive L3 queries, per-RID HTTP timings, host_alloc.v1 generation/free/evictable/wake telemetry, and safety counters
summary: seeded positive-hit safety PASS; y/z complete restore PASS; x/w/q capacity-classified as full-KV infeasible with bounded HOST_ALLOC waits and timeout fallback; successful feasible-epoch wake not exercised
followups: fresh feasible-capacity epoch test only if required
open_issues: no permanent-capacity or durability/RH/fleet claim; extra work requires a fresh Task ID
```
