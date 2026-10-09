STATUS: done

# TEST-20260908-P0-S25-LIVE-RESIDENCY-DIAGNOSTIC-FIX6

- Invocation status: `done`
- Admission: `ACCEPT`
- Host: `root@175.155.64.171:24052`
- Remote checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-residency-diagnostic-fix6-live-r15`
- Evidence: `/data/evidence-gate3-parked/p0-s25-v43-residency-diagnostic-fix6-live-r15`
- Live verdict: **NOT_VERIFIED / fail-closed**

## Result

The fresh marked S=25, RH-off run reached the required 25 target builds, 9
churn builds, and 25 durability barriers. It emitted **zero** strict
`residency_barrier` events and **zero** FIX6 `residency_barrier_outcome`
events. Therefore no first strict predicate, queue snapshot, `retry_epoch`, or
`poll_attempt` was observed for any target; no common failure predicate can be
identified. The only common observation is that FIX6 outcome telemetry was not
emitted in this live path.

Warm and restore were correctly never admitted: `warm_lookup_start=0`,
`warm_request=0`, `restore_outcome=0`, and `restore_success=0`. Free-complete
activity is not treated as residency success.

## Preconditions and timeline

- Preflight: `2026-09-08T15:47:40+08:00` local / `15:47:41+08:00` remote.
  No matching engine, vehicle, or launcher process existed. `/data` had 77G
  free; the fresh r15 evidence path was absent. Existing r11-r14 evidence was
  not modified.
- Remote V4.3 fixture: PASS, exit `0`, output preserved in
  `raw/fixture-v4.3.txt`.
- Engine PID `1051094`; health reached HTTP 200 at
  `2026-09-08T15:50:26+08:00`. Engine startup logged profiled
  `max_total_tokens=501851`, graph8, FP8 KV, hybrid cache, and 120G extent
  storage.
- Vehicle PID `1051639`; launched after health with the exact frozen vehicle
  configuration.
- Stable no-warm snapshots: `2026-09-08T16:03:25+08:00` and
  `16:03:30+08:00`. Acceptance-relevant counts were unchanged; only periodic
  `pc_stats_snapshot` records with unchanged counters continued.
- Vehicle SIGTERM: `2026-09-08T16:04:13+08:00`; gone at `16:04:14`.
  Engine SIGTERM: `16:04:14`; gone at `16:04:25`.
- Final audit: `2026-09-08T16:05:40+08:00`; health was connection-refused and
  no matching process remained. `/tmp/t38c-on` and
  `/tmp/t38c-durable-trace` were removed only after raw evidence capture.

## Source identity

Local hashes before sync matched remote hashes after sync:

```text
aaae7bd08135b4ee4e26e15398297b5882ae94541bd56fbc9028bd6155cefafc  python/sglang/srt/mem_cache/unified_radix_cache.py
5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62  3090-dev/p0_session_barrier_vehicle.py
fbc5dfedd081b0ee8ec5a7aaf6c4928fbf43b615716ef8f464372d47c772a30f  3090-dev/test_p0_trace_context_v4.py
8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09  3090-dev/direct-launch-gate3-parked.sh
```

The accepted launcher contains exactly one `--enable-session-radix-cache`.

## Commands

Authorized source sync:

```text
scp -P 24052 python/sglang/srt/mem_cache/unified_radix_cache.py root@175.155.64.171:/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_radix_cache.py
scp -P 24052 3090-dev/p0_session_barrier_vehicle.py 3090-dev/test_p0_trace_context_v4.py root@175.155.64.171:/root/sglang-b1-continuity/3090-dev/
```

Fixture:

```text
/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/test_p0_trace_context_v4.py
```

Engine launch used the accepted `3090-dev/direct-launch-gate3-parked.sh`:

```text
STORAGE_DIR=/data/evidence-gate3-parked/p0-s25-v43-residency-diagnostic-fix6-live-r15/storage MAX_SIZE=120G FILE_SIZE=120G RH=off SGLANG_PORT=8024 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 SERVED=qwen3.5-9b-gptq KV_DTYPE=fp8_e4m3 MAMBA_RATIO=0.42 HICACHE_RATIO=1.3 T38C_RUN_ID=p0-s25-v43-residency-diagnostic-fix6-live-r15 T38C_BUILD_COMPLETE_DEBUG=1 PYTHONPATH=/root/sglang-b1-continuity/3090-dev ./3090-dev/direct-launch-gate3-parked.sh
```

Exact vehicle command:

```text
/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py --events /tmp/t38c-probe.log --endpoint http://127.0.0.1:8024 --model qwen3.5-9b-gptq --model-path /root/models/Qwen3.5-9B-w4a16 --evidence-dir /data/evidence-gate3-parked/p0-s25-v43-residency-diagnostic-fix6-live-r15/vehicle --run-id p0-s25-v43-residency-diagnostic-fix6-live-r15 --task-id TEST-20260908-P0-S25-LIVE-RESIDENCY-DIAGNOSTIC-FIX6 --epoch phase2-hicache-design/2026-09-08 --sessions 25 --active 8 --build-workers 8 --history-target 55000 --rh off
```

The run created `/tmp/t38c-probe.log`, `/tmp/t38c-durable-trace`, and
`/tmp/t38c-on` before requests. Stop commands were targeted SIGTERM to PIDs
`1051639` and `1051094`; detached background wait statuses were unavailable,
with expected signal-derived status `143` recorded.

## Raw counts and ordering

Counts are from the preserved post-stop trace, restricted to the exact run ID
(`9,697` events):

| Evidence | Result |
|---|---:|
| Target `build_complete` | 25/25 |
| Churn `build_complete` | 9/9 |
| Total `build_complete` | 34 |
| Build ordering | all target builds before all churn builds |
| `durability_barrier` | 25 |
| Durability barriers with complete six-field identity | 25/25 |
| Durability `combined_durable=true` | 25/25 |
| `residency_release_enqueued` | 34 |
| `residency_detach` | 1,589 |
| `residency_free_complete` | 1,991 |
| Strict `residency_barrier` | 0 |
| `residency_barrier_outcome` | 0 |
| Warm lookup / warm request | 0 / 0 |
| Restore outcome / restore success | 0 / 0 |

Per-target diagnostic result:

- `p0-s25-s00000` through `p0-s25-s00024`: first outcome `null`.
- Outcome reason histogram: `{}`.
- Queue snapshots: none observed; therefore
  `queue_snapshot_locked`, `primary_queue_empty`, `extra_queue_empty`, and
  `extra_queue_emptiness` are unavailable for all 25 targets.
- `retry_epoch` and `poll_attempt`: unavailable for all 25 targets.

The absence of outcome records is a runtime/product evidence failure in the
marked path, not an infrastructure failure: the fixture passed, hashes
matched, health succeeded, and the exact build/durability phases completed.
Hard causal diagnosis remains open for `debugger-deep` under a fresh Task ID.

## Trace and artifacts

Pre-stop and post-stop trace copies are byte-identical:

```text
SHA-256: 1b72152496f2d2dd5640873833fbae0c2b04132e2a8acfdde5557915b8bf8f92
Bytes:   11766450
Lines:   10694
```

Preserved evidence includes engine/vehicle commands and logs, fixture output,
health and `/proc` captures, marker state, stable snapshots, process/stop
records, source hashes, raw pre/post traces, reducer summary, per-target
outcome map, reason histogram, derived barrier waits, and a 49-file evidence
manifest under the remote evidence path.

The native vehicle bundle was not produced because the vehicle was intentionally
SIGTERM-stopped after the authorized stable no-warm condition and before
`_write_bundle`. `raw/terminal-artifacts-status.txt` records this. The derived
files are explicitly labeled non-native and do not synthesize a verdict.

## Open issues and followups

1. FIX6 emitted no residency outcome telemetry and no strict residency barrier;
   the first strict predicate is therefore unclassified.
2. Warm/restore acceptance remains unverified because no residency barrier
   admitted a warm request.
3. Detached process exit status was not waitable; signal and process
   disappearance evidence is preserved, with expected status 143.
4. Root free space was 4.4G at preflight; `/data` had 77G free and the run
   completed without OOM or process residue.
5. Route hard causal diagnosis of the missing outcome/poll path to
   `debugger-deep` with a fresh Task ID.

## Status packet

- Status: `done`
- Artifacts: remote evidence at the path above and this report.
- Evidence: exact source hashes, V4.3 PASS, healthy engine, frozen live run,
  stable counts, raw trace hash equality, corrected six-field identity audit,
  safe stop, and final no-residual-process audit.
- Summary: **NOT_VERIFIED / fail-closed**; 25 target + 9 churn + 25 durability,
  0 residency, 0 outcome telemetry, 0 warm, 0 restore.
- Followup: debugger-deep causal diagnosis under a fresh Task ID.
- Open issues: listed above.
