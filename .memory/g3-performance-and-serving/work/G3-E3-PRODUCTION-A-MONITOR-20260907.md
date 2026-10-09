# G3-E3-PRODUCTION-A-MONITOR-20260907

status: done
invocation_status: done
task_id: G3-E3-PRODUCTION-A-MONITOR-20260907
epoch: E3
role: devops

## Scope and terminal result

- Monitored only the already-running wrapper on `root@175.155.64.171:22109`.
- Run: `/data/qwen3-g3-baseline/e3-prod-a/g3-e3-prod-a-20260907T145045488234751Z/`.
- Wrapper PID `434309`; expected service PID `298123`.
- The wrapper reached `RUN_COMPLETE` at `2026-09-08T00:30:06+08:00`.
- All 9 scheduled repeats ran; no signal, restart, reconfiguration, traffic injection, or workload alteration was performed.

## Observed facts and evidence

- Progress log records `POINT_END ... rc=0` for every point and `RUN_COMPLETE`:
  `progress.log`.
- Every repeat has `exit_code.txt=0`, one result JSONL line, `completed` equal to the scheduled prompt count, and zero non-empty errors.
- Warmup rule was observed: C1/repeat-1 has `warmup_requests=3`; all other repeats have `warmup_requests=0` (`metadata.txt`, `command.txt`).
- Every command includes `--flush-cache --flush-cache-timeout 60`. Each repeat's server-log delta records one `POST /flush_cache`; generate counts are C1r1=23 (3 warmup + 20 measured), C1r2/r3=20, C4r1/r2/r3=40, C5r1/r2/r3=50.
- Input fidelity: every `input_lens` value is exactly 2048. Requested/output-lens arrays are exactly 512 in every repeat. Retokenized output totals are 9,878/20 requests (C1), 19,621/40 (C4), and 24,338/50 (C5); the runner's reported output totals remain the requested 512-token totals (10,240/20,480/25,600).
- Telemetry logs are non-empty for all repeats (454–799 lines); per-repeat server-log deltas and before/after evidence are preserved.
- Wrapper, benchmark clients, and telemetry children are absent after completion. No unrelated process was touched.
- Postflight `/health` and `/v1/loads` both returned HTTP 200. Postflight loads were idle: `num_running_reqs=0`, `num_waiting_reqs=0`, `num_used_tokens=0`, `token_usage=0.0`.
- Service PID 298123 remained alive with the frozen IQ3_S SGLang command. Pre/post command-line SHA-256 is identical: `750ac48907968dacfd3175b1547a1cd8b9b89cb3eeaa5ebfd625ce221717d200`.
- Remote and copied local `SHA256SUMS` verification passed for all 484 listed files. Manifest SHA-256: `be1aff7b0615791b9fd9a159a6880ee28f2cc7f5958b607d50e41e4098ea83b9`; `SHA256SUMS` SHA-256: `3b28558b8f7992d2456983beb5ff4de4d7ab9ee3a3ab5c8878a2f9cd3ef69650`.

## Median scorecard across 3 repeats

Throughputs are runner-reported tokens/s; latency values are milliseconds. `in` is prefill/input throughput, `out` is decode/output throughput, and `total` is aggregate throughput.

| config | prompts / C | req/s | in tok/s | out tok/s | total tok/s | TTFT p50 / p95 / p99 | TPOT p50 / p95 / p99 | E2E p50 / p95 / p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | 20 / 1 | 0.047941 | 98.182879 | 24.545720 | 122.728599 | 2885.263 / 2889.311 / 2889.619 | 35.195 / 35.243 / 35.255 | 20870.928 / 20894.215 / 20896.515 |
| C4 | 40 / 4 | 0.066174 | 135.524626 | 33.881157 | 169.405783 | 8815.626 / 11468.756 / 11517.300 | 100.843 / 111.960 / 111.968 | 60441.638 / 60457.602 / 60457.841 |
| C5 | 50 / 5 | 0.066771 | 136.746389 | 34.186597 | 170.932986 | 8954.103 / 14338.957 / 14399.239 | 129.022 / 140.169 / 140.197 | 74889.240 / 74914.486 / 74915.513 |

Raw fields support the reported p50/p95/p99 values. No requested scorecard field was unavailable.

## Artifacts

- Remote run: `/data/qwen3-g3-baseline/e3-prod-a/g3-e3-prod-a-20260907T145045488234751Z/`.
- Local raw copy (including all 9 repeats, telemetry, logs, manifest, and hashes): `.memory/g3-baseline-20260907/work/raw/g3-e3-prod-a-20260907T145045488234751Z/`.
- Setup-only attempts remain excluded; no artifacts from those directories were copied into this run's raw subtree.

## Open issues and followups

- All nine benchmark stderr files contain the same non-fatal Python `multiprocess.resource_tracker` destructor traceback (`AttributeError: '_thread.RLock' object has no attribute '_recursion_count'`) after the benchmark completes. It did not change wrapper `rc=0`, result completion, or cleanup; retain as a runtime follow-up rather than treating it as a benchmark failure.
- The earlier setup-only `cfg: unbound variable` line remains in the shared progress history before the active `RUN_START`; it is excluded from this completed run and did not affect any scheduled point.
- No further operational action is required for this monitoring task. Results should be compared against the preserved unoptimized baseline using the raw JSONL and independent run ID.
