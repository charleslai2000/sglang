STATUS: done

# TEST-20260908-P0-S25-LIVE-EMITTER-FIX5

- Invocation status: `done`
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Remote checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-emitter-fix5-live-r14`
- Evidence: `/data/evidence-gate3-parked/p0-s25-v43-emitter-fix5-live-r14`

## Summary

The fresh S=25, RH-off run used the accepted FIX5 emitter and accepted FIX1
target-churn vehicle with exact source-hash agreement. It reached 25 target
builds, exactly 9 unique churn builds, and 25 combined KV/Mamba durability
barriers. The event stream then stabilized for 5 seconds with 1,992
`residency_free_complete` events but **zero** strict product
`residency_barrier(cold_residency=true)` events. No warm request or restore was
eligible. Per the authorized early-stop rule, the vehicle and engine were
stopped safely without waiting for the full watchdog.

This run does not verify the runtime acceptance criteria. The FIX5 queue guard
is observed fail-closed: after completion and queue activity, no subsequent
request drove the queue-drain callback that would publish the residency
barrier. The run is therefore `NOT_VERIFIED`, not a synthesized pass.

## Source identity and preconditions

Local hashes before sync and remote hashes after sync matched:

```text
f6e6a9b6c1c667681b0a655946e28ec62877cf9240ee8eb61275258300f72849  python/sglang/srt/mem_cache/unified_radix_cache.py
5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62  3090-dev/p0_session_barrier_vehicle.py
fbc5dfedd081b0ee8ec5a7aaf6c4928fbf43b615716ef8f464372d47c772a30f  3090-dev/test_p0_trace_context_v4.py
8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09  3090-dev/direct-launch-gate3-parked.sh
```

The remote V4.3 fixture passed before launch:

```text
P0 trace-context V4.3 focused checks: PASS
```

Preflight at `2026-09-08T14:58:12+08:00` found no matching engine/vehicle
process. Disk state was `/` 4.4G free and `/data` 99G free. The fresh event
marker was truncated before vehicle requests. The accepted launcher contained
exactly one `--enable-session-radix-cache`.

## Commands and timeline

Authorized source sync used `scp` for the three requested files only; no
checkout reset was performed. The remote fixture command was:

```text
/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/test_p0_trace_context_v4.py
```

The engine was launched with the accepted launcher and frozen configuration:

```text
STORAGE_DIR=/data/evidence-gate3-parked/p0-s25-v43-emitter-fix5-live-r14/storage \
MAX_SIZE=120G FILE_SIZE=120G RH=off SGLANG_PORT=8024 \
MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 SERVED=qwen3.5-9b-gptq \
KV_DTYPE=fp8_e4m3 MAMBA_RATIO=0.42 HICACHE_RATIO=1.3 \
T38C_RUN_ID=p0-s25-v43-emitter-fix5-live-r14 T38C_BUILD_COMPLETE_DEBUG=1 \
PYTHONPATH=/root/sglang-b1-continuity/3090-dev \
./3090-dev/direct-launch-gate3-parked.sh
```

The vehicle command was:

```text
/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py \
  --events /tmp/t38c-probe.log \
  --endpoint http://127.0.0.1:8024 \
  --model qwen3.5-9b-gptq \
  --model-path /root/models/Qwen3.5-9B-w4a16 \
  --evidence-dir /data/evidence-gate3-parked/p0-s25-v43-emitter-fix5-live-r14/vehicle \
  --run-id p0-s25-v43-emitter-fix5-live-r14 \
  --task-id TEST-20260908-P0-S25-LIVE-EMITTER-FIX5 \
  --epoch phase2-hicache-design/2026-09-08 \
  --sessions 25 --active 8 --build-workers 8 --history-target 55000 --rh off
```

Timeline:

- Engine launched as PID `1045849` at `2026-09-08T14:58:33+08:00`.
- Health probes returned startup connection-refused/503 responses, then HTTP
  200 at `2026-09-08T15:00:19+08:00`.
- Vehicle launched as PID `1046657` at `2026-09-08T15:00:44+08:00`.
- Stable pre-stop counts were captured at `2026-09-08T15:14:29+08:00` after
  two equal snapshots separated by 5 seconds.
- Vehicle process group received SIGTERM at `2026-09-08T15:14:29+08:00` and
  was gone after 2 seconds. Detached-process exit status was not waitable;
  SIGTERM conventionally corresponds to expected exit code 143, recorded as
  such in `raw/vehicle-stop.txt`.
- Engine process group received SIGTERM at `2026-09-08T15:14:30+08:00` and
  was gone after 8 seconds. Its detached-process status was likewise recorded
  as expected 143.
- Final audit completed at `2026-09-08T15:16:11+08:00`; both original PIDs,
  both process groups, and named engine processes were absent.

## Raw runtime counts

Counts below are parsed from the preserved post-stop trace and restricted to
the exact r14 `run_id`. The product six-field identity is
`(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash)`.

| Evidence | Result |
|---|---:|
| Run-scoped events | 9,697 |
| Target `build_complete` identities | 25/25 |
| Churn `build_complete` identities | 9/9 |
| Total `build_complete` | 34 |
| Unique target sessions / churn sessions | 25 / 9 |
| `durability_barrier` | 25 |
| Durability `combined_durable` / KV / Mamba | 25 / 25 / 25 |
| Durability barriers with exact six-field identity | 25/25 |
| `residency_barrier` | 0 |
| Strict residency `cold_residency=true` | 0 |
| Warm lookup / warm request | 0 / 0 |
| Restore outcome / restore success | 0 / 0 |
| `residency_detach` | 1,589 |
| `residency_free_complete` | 1,992 |
| `residency_release_enqueued` | 34 |
| `storage_persisted` | 697 |

All 25 target build events preceded their corresponding durability events. The
required durability-to-residency and residency-to-warm order cannot be
satisfied because no residency event was emitted. There was no early warm
request and no restore success to claim.

## Early-stop basis

The authorized deterministic early-stop reason is preserved in
`raw/early-stop-reason.txt`:

```text
25 target build_complete + 9 churn build_complete + 25 durability_barrier;
exact event counts stable; 0 strict residency_barrier after FIX5 queue guard;
no subsequent request remains to drive queue drain; vehicle is blocked waiting
for residency and warm is ineligible.
```

The pre-stop and post-stop raw trace copies are byte-identical:

```text
514c2b379b291b148195271dc9bdd38a0001ad59fe3726187591203dcb0580a6  trace-pre-stop.jsonl
514c2b379b291b148195271dc9bdd38a0001ad59fe3726187591203dcb0580a6  trace-post-stop.jsonl
```

The post-stop corrected counts are in `raw/counts-corrected.json`; the initial
and final raw counts are also preserved as `counts-pre-stop.json`,
`counts-post-stop.json`, and their stability snapshots. Vehicle stdout/stderr,
engine log, launcher/vehicle commands, health probes, `/proc` capture, stop
records, disk state, and final artifact hashes are retained under `raw/`.

## Runtime verdict

**NOT_VERIFIED / fail-closed.** The run satisfies the target-build, churn, and
durability portions but fails the required strict residency, warm, and restore
evidence. No PASS or partial warm result was synthesized. The observed outcome
matches the r13 acceptance blocker: completion/free activity exists, but no
post-completion request drives the queue-drain path that would allow the strict
FIX5 residency publication.

## Open issues

1. Product/runtime emitted zero strict residency barriers after 25 durability
   barriers, leaving the accepted vehicle deterministically blocked.
2. Warm and restore acceptance remain unverified because the warm scheduler was
   correctly never admitted without residency barriers.
3. Vehicle and engine were intentionally stopped by SIGTERM before the vehicle
   watchdog. The detached background launch made an OS-reported wait status
   unavailable; expected signal-derived status 143 and process disappearance
   are recorded.
4. The vehicle did not reach `_write_bundle`; no synthetic `verdict.json`,
   `reducer-result.json`, or warm rows were created. Raw trace/count/stop
   evidence is complete and preserved.
5. Existing r11/r12/r13 evidence was not deleted or modified.

## Status packet

- Status: `done`
- Artifacts: remote evidence at
  `/data/evidence-gate3-parked/p0-s25-v43-emitter-fix5-live-r14` and this report.
- Evidence: exact source hashes, remote fixture PASS, health/process captures,
  stable raw counts, exact six-field durability identity counts, pre/post trace
  hashes, authorized early-stop reason, stop records, and final no-residual
  process audit.
- Summary: **NOT_VERIFIED / fail-closed**; 25 target + 9 churn + 25 durability,
  0 residency, 0 warm, 0 restore.
- Followups: route the queue-drain/barrier deadlock to `debugger-deep` under a
  fresh Task ID; preserve this r14 evidence alongside r11/r12/r13.
- Open issues: listed above.
