# DEVOPS-20260908-P0-S25-LIVE-R5-EXACT-RETRY

status: blocked
task_id: DEVOPS-20260908-P0-S25-LIVE-R5-EXACT-RETRY
host: 175.155.64.171:24052
checkout: /root/sglang-b1-continuity

## Summary

The required SSH authentication check succeeded (`hostname` -> `pytorch-4402`).
The fresh launcher reached `/health`, but the vehicle terminated before session 0
because it was invoked with an interpreter that lacked `transformers`. No vehicle
verdict, branch, TTFT, restore, or barrier result was produced. The run is blocked
and is not a P0 acceptance result.

## Run and evidence

- run id: `p0-s25-v43-fix2-live-20260907T232110Z`
- fresh evidence: `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5`
- fresh storage: `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5/storage`
- engine PID: `1005986`
- readiness marker: `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5/ready-marker`
- vehicle exit: before session execution; stdout empty; no `verdict.json`
- vehicle error: `ModuleNotFoundError: No module named 'transformers'`

Before truncation, the authorized R4 transient snapshots were created:

- `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r4/raw/t38c-probe.log.pre-r5`
  SHA-256 `da3b5df8f4e822de4ad1a3ff9e7073f94f1b62504085025173f0ca05e29fc084`
- `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r4/raw/t38c-durable-trace.pre-r5`
  SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

The new 120,000,000,000-byte storage file was created. Prior evidence/storage
was not deleted or otherwise changed.

## Verification

The matching engine was force-stopped after the early vehicle exit. Final remote
process capture `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5/post-stop-processes-final.txt`
is empty for `sglang.launch_server`, `p0_session_barrier_vehicle`, and
`direct-launch-gate3-parked.sh`.

## Invocation evidence

Commands executed included:

```text
ssh -o BatchMode=yes -p 24052 root@175.155.64.171 hostname
```

Result: `pytorch-4402`.

The accepted launcher was started with `STORAGE_DIR` set to the new storage,
`MAX_SIZE=120G`, `FILE_SIZE=120G`, `RH=off`, and `SGLANG_PORT=8024`; health
readiness succeeded. The requested vehicle arguments were supplied for endpoint
`127.0.0.1:8024`, model `qwen3.5-9b-gptq`, sessions 25, active 8,
build-workers 8, history-target 55000, and RH off.

## Followups

Requires a fresh Task ID to rerun with the established environment interpreter
that provides `transformers`. No rerun, diagnosis, code change, or alternative
procedure was performed here.

## Open issues

- No branch counts, TTFT, restore counts, or barrier counts exist for this run.
- Vehicle interpreter/environment selection must be explicitly authorized in a
  fresh task.
