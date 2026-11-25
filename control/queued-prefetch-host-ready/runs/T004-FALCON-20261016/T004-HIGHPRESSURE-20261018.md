# Bounded high-pressure Falcon T004 arms

Date: 2026-10-18. Two complete measured arms were run under `/tmp/f1-r16b-gpu-exclusive.lock`, using the isolated T004 Extent fixture, same Falcon revision, 8 configured running requests, 32,768 total-token budget, 8 queue slots and Ready Horizon enabled. Queue Prefetch mode differed: OFF sets `SGLANG_DISABLE_HICACHE_QUEUE_PREFETCH=true`; ON leaves it false. This is one descriptive arm per mode, not a replicated performance result.

## Workload and outcomes

| Mode | Run ID | A occupant | B/C/D queued targets | B/C/D queue time | E2E | L3 hits |
|---|---|---|---|---|---|---|
| OFF | `falcon-t004-highpressure-off-20261017T235337Z` | 2,048 prompt / 1,024 output; E2E 27.035s | each 2,112 prompt / 128 output | 21.114 / 21.518 / 21.922s | 25.685 / 25.585 / 25.485s | 2,048 cached tokens each; cached details report 2,048 Storage pages |
| ON | `falcon-t004-highpressure-on-20261018T005414Z` | 2,048 prompt / 1,024 output; E2E 27.680s | each 2,112 prompt / 128 output | 21.358 / 21.461 / 21.433s | 25.613 / 25.535 / 25.434s | 2,048 cached tokens each; cached details report 2,048 Storage pages |

Both runs use distinct B/C/D durable target identities and same-run queries previously verified the corresponding 2,048 FULL and MAMBA page extents. The client held the bounded request set; scheduler logs recorded real occupant Decode and pending admissions. A is a genuine long Decode; B/C/D have real uncached suffix Prefill beyond the durable prefix and 128 output tokens. The CDB/response includes request RID, prompt/output IDs, per-request metadata, client monotonic timestamps, RID-filtered producer events, matching scheduler lines, final host metrics and probe count. Each arm reports 9,059 (OFF) / 9,707 (ON) same-run probe events.

For B/C/D, OFF average E2E=25.585s, ON=25.527s; the 58ms difference is descriptive only. Client measured E2E contains ~21.1–21.9s imposed queue residence plus restored-prefix/remaining Prefill, Decode and response overhead. It is not restore service time and cannot be interpreted as steady-state throughput or causal improvement. There is no low-concurrency matched control yet and only one run/mode.

The Extent process window/probe data is available in each arm JSON/probe file. It is aggregate to the run window, not per RID; the field `physical_bytes_read` is not independent device telemetry and does not split Linux page cache from media I/O. No profiler was started. There is no request-tagged first GPU execution/step or L0 Prefill/Decode metric; GPU stall/overlap is NOT_VERIFIED. Do not infer that queue overlap means compute overlap.

## Artifact paths

For each run ID `R`:
- `ab-R.json`: complete arm manifest and measured rows
- `driver-R.log`: per-request stream rows plus `AB_ARM_COMPLETE`
- `requests-R.jsonl`: client request evidence
- `server-R.log`: same-run scheduler/admission events
- `t38c-probe-R.jsonl`: producer events and extent snapshots
- `extent-R/`: isolated durable data
- `launcher-R.log`: launcher stdout/stderr

## Run failures and resource cleanup

- `20261017T230707Z` ended after fixture queries because the then-current workload required impossible 8-active occupancy under 8,192 tokens and single-token B/C/D; preserved, not a measurement.
- `20261017T232923Z` completed the workload but failed writing its manifest because `experiment_config` was JSON null. The manifest guard was fixed; this run is not counted.
- `20261017T233257Z` launcher refused an existing shared marker. The marker and symlink were traced to `232923Z`, and removed only after confirming no server process and exact symlink target.
- `20261017T235337Z` is complete. The outer command hard limit elapsed after `AB_ARM_COMPLETE`; the server was subsequently found to be the `exec`-replaced launcher PID and shut down by exact run-specific PID. GPU returned to 1MiB, 0% utilization.
- `20261018T005414Z` is complete. The background command returned after writing `AB_ARM_COMPLETE`, but the server remained because launcher `exec` replaces its shell and the caller's cleanup killed the stale shell PID; `/shutdown` returned 404. Verified the exact server command line and its isolated Extent run ID, then TERM-stopped that server only. GPU returned to 1MiB, 0%; no SGLang process remained.

This exposed a launcher lifecycle issue: caller-side cleanup must target the actual server PID after `exec`, or the launcher needs a non-exec child/wrapper that traps shutdown. `launch.sh` now retains the Python child PID, TERM-waits up to 30 seconds, then KILLs only that child if needed, waits it, and cleans run markers in EXIT/INT/TERM trap. `bash -n` passes; the new trap has not yet been exercised by a GPU service shutdown. Do not change production source for this operational harness bug.

## Status / next

One valid bounded high-pressure ON/OFF pair is now captured; no low-concurrency control or frozen long numerical/FULL+MAMBA correctness has been run. Existing three mechanism pairs remain the accepted mechanism evidence and are not repeated. Current quantitative evidence is descriptive only. Online L0, first-execution linkage and physical-media attribution remain NOT_VERIFIED. No source commit/push performed.
