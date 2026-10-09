STATUS: done

# TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1

- Invocation status: done
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-churn-fix1-live-r12`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12`

## Summary

The fresh frozen S=25 run started successfully with RH off and the accepted FIX1
vehicle. It produced all 25 target build identities and exactly 9 auxiliary churn
builds. The raw product trace contains 25 combined KV+Mamba durability barriers,
but it contains **zero strict `residency_barrier(cold_residency=true)` events**.
Consequently the vehicle issued no warm lookup/request and no restore request. The
vehicle reached its bounded watchdog and returned a fail-closed `NOT_VERIFIED`
verdict. This is not runtime PASS evidence; lower-level `residency_free_complete`
events were not mapped to residency acceptance.

The independent debugger conclusion that product-side strict residency evidence is
missing is consistent with the raw trace. No product implementation, design, ledger,
or gate report was modified.

## Preconditions and source identity

- Gate input: `review/gates/P0-VEHICLE-TARGET-CHURN-FIX1.md`, accepted.
- Local accepted vehicle SHA-256: `5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62`.
- Local accepted fixture SHA-256: `fbc5dfedd081b0ee8ec5a7aaf6c4928fbf43b615716ef8f464372d47c772a30f`.
- Remote vehicle and fixture hashes matched those values before launch.
- Remote accepted product cache source remained unchanged:
  `unified_radix_cache.py` SHA-256 `acc21828eac866f0d2f05f465273c8d77f586693544b796f15e62b9f810b9460`.
- Remote focused fixture: `P0 trace-context V4.3 focused checks: PASS`.
- Prior r11 evidence was preserved; its `/root/evidence-gate3-parked/p0-s25-v43-fix4-live-r11` tree was not modified.

## Frozen runtime and commands

Configuration was unchanged from the dispatch: S=25, history=55000, active=8,
build_workers=8, RH=off, TP=1, Qwen3.5-9B w4a16, `fp8_e4m3`, Mamba ratio 0.42,
HiCache ratio 1.3, `wait_complete`, extent storage 120G, graph8, max_total_tokens
600000, profiled/resolved 501851.

Engine command used the existing remote launcher:

```text
cd /root/sglang-b1-continuity
./3090-dev/direct-launch-gate3-parked.sh
```

The vehicle command was:

```text
/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py \
  --events /tmp/t38c-probe.log --endpoint http://127.0.0.1:8024 \
  --model qwen3.5-9b-gptq --model-path /root/models/Qwen3.5-9B-w4a16 \
  --evidence-dir /root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/vehicle \
  --run-id p0-s25-v43-churn-fix1-live-r12 \
  --task-id TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1 \
  --epoch phase2-hicache-design/2026-09-08 --sessions 25 --active 8 \
  --build-workers 8 --history-target 55000 --rh off
```

Timeline:

- Evidence/run initialized: `2026-09-08T12:43:36+08:00`.
- Engine health 200: `2026-09-08T12:45:22+08:00` after 53 bounded health-loop iterations.
- Vehicle started: `2026-09-08T12:46:16+08:00` (PID 1034986; recorded at 12:46:17).
- Target phase reached 25/25 builds at approximately `2026-09-08T12:55:22+08:00`.
- Churn phase reached 9/9 builds at approximately `2026-09-08T12:58:10+08:00`.
- Last fresh trace event: `2026-09-08T12:57:19+08:00`, churn session `p0-s25-churn-00008`.
- Vehicle observed exited naturally: `2026-09-08T13:28:56+08:00` after the bounded wait.
- Engine SIGTERM requested: `2026-09-08T13:29:14+08:00`; stopped at the sixth 2-second check.

## Raw runtime counts

Counts below are from the preserved r12 post-stop trace and are restricted to
`run_id=p0-s25-v43-churn-fix1-live-r12`.

| Evidence | Count/result |
|---|---:|
| Target `build_complete` identities | 25/25 |
| Auxiliary churn `build_complete` identities | 9/9 |
| Total `build_complete` | 34 |
| Build order | first 25 target, then 9 churn; no target after churn |
| `durability_barrier` | 25 |
| Durability barriers with `combined_durable=true` | 25/25 |
| Durability barriers with `kv_durable=true` | 25/25 |
| Durability barriers with `mamba_durable=true` | 25/25 |
| `residency_barrier` | 0 |
| `residency_barrier(cold_residency=true)` | 0/25 |
| `warm_lookup_start` | 0 |
| `warm_request` / warm response | 0 / 0 |
| Restore success | 0 |
| `storage_persisted` | 698 |
| `backup_submit` | 698 |
| `backup_ack_enqueue` / `backup_ack_drain` | 698 / 698 |
| `extent_commit` | 1416 |
| `storage_query` | 8 |
| `residency_detach` | 1589 |
| `residency_free_complete` | 1994 |
| `storage_invalidate` | 1,377,028 |
| Root suppression / assert / actual OOM / HTTP 4xx-5xx / zero-progress markers | 0 observed |

The seven engine-log `CUDA OOM` strings were low-free-memory preload advisories;
there was no `CUDA out of memory` failure, engine assertion, HTTP 4xx/5xx, or
zero-progress marker. The preexisting optional libtorchcodec import warning was
also present, as in prior runs.

## Churn acceptance evidence

`vehicle/churn-builds.jsonl` contains exactly 9 rows for
`p0-s25-churn-00000` through `p0-s25-churn-00008`. They have 9 unique build RIDs,
9 unique history SHA-256 values, builder seeds 25 through 33, HTTP 200, terminal
completion, `rid_source=response.id`, and no failure. `verdict.json` reports
`churn_count=9`, `churn_expected_count=9`, an empty `churn_failures` list, and an
empty `churn_scope_error` list. The raw build sequence independently confirms all
target builds precede all churn builds, and no churn identity appears in the
target-only planned/warm rows.

## Barrier and fail-closed evidence

The vehicle bundle contains 25 barrier-wait rows and 25 target build/warm rows.
The final vehicle verdict is:

```text
verdict=NOT_VERIFIED
fail_closed=true
planned_sessions=25
planned_row_count=25
eligible_full_sessions=25
churn_count=9
restore_success=0
```

Its branch summary is `D_recycle_or_remove=1`, `F_unresolved=24`, with 25 barrier
watchdog timeout errors. No warm scheduler success row exists. The strict product
residency acceptance count remains zero; the observed `residency_free_complete`
events are allocator/free events and are deliberately not treated as residency
barriers.

## Shutdown and artifacts

- No matching engine, vehicle, or launcher process remained after shutdown.
- Pre-stop and post-stop traces are byte-identical: 1,386,369 lines,
  1,629,164,506 bytes, SHA-256
  `e3a4865a145fa01f10c420b6ece00a91ef74cf2ff92cc2b248e834ad38530fad`.
- Engine log: `/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/engine/launcher.log`.
- Vehicle stdout: `/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/vehicle/stdout.log` (1,900 bytes).
- Vehicle stderr: `/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/vehicle/stderr.log` (0 bytes).
- Vehicle evidence: `vehicle/verdict.json`, `vehicle/churn-builds.jsonl`,
  `vehicle/barrier-waits.jsonl`, `vehicle/build-warm.jsonl`,
  `vehicle/reducer-result.json`, and `vehicle/trace-copy.jsonl`.
- Raw evidence: `raw/t38c-probe.log.prestop`, `raw/t38c-probe.log.poststop`,
  `raw/raw-counts-prestop.txt`, `raw/watchdog-monitor.txt`, process snapshots,
  environment captures, stop records, and `raw/evidence-sha256-final.txt`.
- The stale pre-r12 `/tmp/t38c-probe.log` was preserved as
  `raw/preexisting-t38c-probe.log`; the fresh run used the fixed product path
  `/tmp/t38c-probe.log` and all parsed events were r12-tagged.
- The background vehicle launch did not retain a wait-status file. Direct vehicle
  exit code is therefore **unavailable**; natural process exit and the persisted
  `NOT_VERIFIED` verdict/stdout are the terminal evidence. No exit code is inferred.

## Followups

- Product-side strict residency evidence must be repaired or separately explained
  under a fresh Task ID before any runtime PASS claim.
- A subsequent live run must show positive target `residency_barrier(cold_residency=true)`
  and causal warm/restore evidence; allocator `free_complete` events are insufficient.

## Open issues

1. Runtime acceptance is blocked by zero strict residency barriers and therefore
   zero warm/restore evidence; this run is NOT_VERIFIED, not PASS.
2. The vehicle’s direct process exit code was not captured by the background launch
   wrapper; only natural exit observation and the persisted fail-closed verdict are
   available.
3. The remote root filesystem ended at approximately 2.9G free after preserving
   the required r12 evidence; the r12 run and prior evidence were not deleted.

done
