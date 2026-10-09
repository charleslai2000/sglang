ENTRY: ACCEPT

# TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16

- Invocation status: `done`
- Admission: `ACCEPT`
- Role: `tester`
- Host: `root@175.155.64.171:24052`
- Remote checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-residency-node-sidecar-fix1-live-r16`
- Evidence: `/data/evidence-gate3-parked/p0-s25-v43-residency-node-sidecar-fix1-live-r16`
- Overall live verdict: **NOT_VERIFIED / fail-closed**

## Summary

The fresh remote run deployed the accepted FIX1 source with matching SHA-256
hashes and passed the remote focused emitter and V4.3 fixture checks. The
engine reached health 200 with the frozen configuration and the required
markers were present before engine and vehicle requests.

The live product path emitted exact identities for 23 target builds and 15
durability barriers, but emitted **zero strict `residency_barrier` events**.
It emitted 751,914 `residency_barrier_outcome` records with
`reason=node_lookup`, `exception_type=KeyError`, and `result=false`. Warm and
restore were therefore never admitted. This is runtime product evidence of a
residency-fold/node-lookup failure, not evidence of a queue or marker failure.

The vehicle and engine were stopped only for this run after the retry telemetry
grew the trace to 937 MB and the root filesystem reached 96% used (4.4 GB
free). The native vehicle bundle was not written before that safety stop, so
this run cannot verify the native HTTP `response.id`/finished, TTFT, or restore
criteria. No PASS claim is made.

## Source and preconditions

Final synchronized files and hashes are recorded in:

`/data/evidence-gate3-parked/p0-s25-v43-residency-node-sidecar-fix1-live-r16/source-hashes.txt`

All five local/remote pairs matched:

- `unified_radix_cache.py`: `beb2c7189bad3d668d3bc67cde66b271644de10b504aba63e31a87efa8bf4880`
- `p0_session_barrier_vehicle.py`: `5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62`
- `test_p0_residency_barrier_emitter.py`: `c4e22225120f42593480936859aa407db06a9bedfc645a942edffc0bee5d9aa9`
- `test_p0_trace_context_v4.py`: `fbc5dfedd081b0ee8ec5a7aaf6c4928fbf43b615716ef8f464372d47c772a30f`
- `direct-launch-gate3-parked.sh`: `8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09`

Remote `py_compile`, focused emitter checks, and V4.3 fixture checks passed;
outputs are under `raw/remote-py-compile.txt`,
`raw/remote-focused-emitter.txt`, and `raw/fixture-v4.3.txt`.

The engine log confirms: S=25 vehicle target, active/workers 8, history 55000,
RH off, TP=1, mamba ratio 0.42, HiCache ratio 1.3, FP8 E4M3, graph max batch 8,
requested max total 600000 with profiled value 501851, wait-complete prefetch,
120G storage, and exactly one `--enable-session-radix-cache`.

`raw/engine-proc-environ.txt` proves `T38C_RUN_ID` and
`PYTHONPATH=/root/sglang-b1-continuity/3090-dev` in the engine environment.
`raw/markers-before-engine.txt` and `raw/pre-request-audit.txt` prove both
`/tmp/t38c-durable-trace` and `/tmp/t38c-on` existed before requests.

## Runtime counts and identity results

Counts are from the final run-scoped reduction of
`raw/trace-post-stop.jsonl` (SHA-256
`abe6943638e5052b5aca2b51540bd78a33896c6c3859b3603eb1f7638b755818`).

| Evidence | Result |
|---|---:|
| Target `build_complete` | 23/25 |
| Target build events with exact six-field identity | 23/23 |
| Target `durability_barrier` | 15/25 |
| Target durability events with exact six-field identity | 15/15 |
| `combined_durable=true` / `kv_durable=true` / `mamba_durable=true` | 15 / 15 / 15 |
| Strict `residency_barrier` | 0/25 |
| `cold_residency=true` | 0/25 |
| `residency_barrier_outcome` | 751,929 |
| Outcome `node_lookup` + `KeyError` + false | 751,914 |
| Outcome `durability_not_ready` | 15 |
| Warm request | 0 |
| Restore outcome / success | 0 / 0 |
| Churn builds before safety stop | 0 |

Observed target build IDs were `s00000`–`s00015` and `s00017`–`s00023`;
missing builds were `s00016` and `s00024`. Observed durability IDs were
`s00000`–`s00008` and `s00010`–`s00015`; missing durability IDs were
`s00009`, `s00016`–`s00024`. The per-target exact identity and reason data is
in `raw/per-target-identities.jsonl` and `raw/per-target-summary.json`.
All observed build/durability identity sets were internally consistent; no
strict residency identity was available to duplicate.

Free/detach telemetry was retained but not promoted to residency success:
1,033 `residency_detach`, 1,147 `residency_free_complete`, and 24
`residency_release_enqueued` events. Device detach/free-complete counts were
1,028; host free-complete count was 119. These are lifecycle evidence only.

## Metrics and failure classification

Recorded metrics are in `raw/runtime-metrics.json`:

- Durability barriers carried 21,824 requested and 21,824 completed KV tokens;
  15 expected and 15 completed Mamba pages.
- Unscoped PC counters at the final snapshot recorded 25 attempts, 24 issued,
  1,323,518 L3 demand/miss tokens, and 1,323,518 L1/L2-miss tokens. These are
  retained as diagnostic counters, not accepted as native per-target vehicle
  metrics because they lack run binding.
- Storage-query counters recorded zero storage-hit count and zero KV-hit pages;
  host/device hit-token fields are unavailable without the native vehicle
  bundle.
- TTFT, response IDs, finished flags, and restore timing are unavailable: the
  vehicle was terminated before `_write_bundle`; `vehicle/vehicle.stdout.log`
  is empty and no native reducer bundle exists.
- The engine log contains 24 HTTP 200 chat responses and no non-2xx chat
  responses, but this does not substitute for native response.id/finished
  evidence.
- No `CUDA out of memory`, `OutOfMemoryError`, `AssertionError`,
  `BackendError`, or `ZeroDivisionError` token was found in the engine log.

Classification: the repeated `node_lookup`/`KeyError` outcomes are a product
runtime failure in the residency path. The bounded stop and trace growth are
an infrastructure-safety limitation that prevents completion of the native
vehicle bundle; they are not converted into a product PASS or a synthetic
warm/restore result. The first reduction attempt had a harness `KeyError`
while assembling an aggregate field; the corrected read-only reducer produced
the final artifacts above and did not alter raw evidence or product code.

## Stop and trace evidence

- Vehicle PID `1056181` and engine PID `1055665` were targeted with SIGTERM.
- Vehicle disappeared at `16:45:38+08:00`; engine disappeared at
  `16:46:11+08:00` after a temporary uninterruptible `D` state.
- `raw/final-process-audit.txt` records no residual engine/vehicle and confirms
  r15 evidence remained preserved. Markers were removed only after capture.
- Pre-stop trace hash: `a0ddd1ec36b85229e0cf18d5b43ee558944678ddaee009064f3e1a1a703e5623`
  at `raw/pre-stop-audit.txt`.
- Pre-engine-stop hash:
  `a1bfb9f50cd1e4cc06a56ab4bf22f53dcd20a15646e9e976ca22252b29dd840f` at
  `raw/pre-engine-stop-trace.txt`.
- Post-stop `/tmp` trace and preserved copy match at
  `abe6943638e5052b5aca2b51540bd78a33896c6c3859b3603eb1f7638b755818`;
  see `raw/trace-post-stop.sha256`.
- The pre/post difference is expected from additional retry telemetry emitted
  during engine shutdown; the preserved post-stop copy is the final trace.

## Artifacts

Remote evidence root:

`/data/evidence-gate3-parked/p0-s25-v43-residency-node-sidecar-fix1-live-r16`

Key artifacts:

- `verdict.json`
- `source-hashes.txt` and `evidence-manifest.sha256`
- `engine/launcher.log`, `engine/launch-command.txt`, `engine/pid`
- `vehicle/launch-command.txt`, `vehicle/pid`, `vehicle/vehicle.stdout.log`
- `raw/trace-post-stop.jsonl`
- `raw/per-target-identities.jsonl`
- `raw/per-target-summary.json`
- `raw/runtime-metrics.json`
- `raw/event-counts.json`
- `raw/live-monitor.txt`
- `raw/pre-stop-audit.txt`, `raw/pre-engine-stop-trace.txt`,
  `raw/trace-post-stop.sha256`, `raw/final-process-audit.txt`

## Followups

- Route hard causal diagnosis of the live `node_lookup`/`KeyError` residency
  fold to `debugger-deep` under a fresh Task ID.
- After repair, run a fresh native vehicle with a bounded/throttled diagnostic
  trace path and require completion of all 25 builds, durability barriers,
  strict residency barriers, warm HTTP response IDs/finished flags, TTFT, and
  restore outcomes.

## Open issues

- Native vehicle bundle and TTFT/response metrics are missing because the run
  was safety-stopped before vehicle finalization.
- Root filesystem reached 96% from runaway retry telemetry; no OOM/assert was
  observed.
- Pre-stop and post-stop hashes differ during shutdown; the final preserved
  trace hash is internally verified and manifest-covered.

## Status packet

- Status: `done`
- Artifacts: remote r16 evidence root and this report.
- Evidence: final source hashes, remote focused checks, marked engine/vehicle
  run, exact run-scoped reduction, per-target identities, raw trace hash
  equality after stop, and final process audit.
- Summary: **NOT_VERIFIED / fail-closed**; strict residency did not occur and
  the live path repeatedly failed node lookup.
- Followups: debugger-deep causal diagnosis and a fresh post-repair live run.
- Open issues: native warm/restore/TTFT bundle absent; resource-safe stop and
  shutdown hash delta recorded above.
