# DEVOPS-20260908-P0-S25-LIVE-R3-CLEANUP

- Task ID: `DEVOPS-20260908-P0-S25-LIVE-R3-CLEANUP`
- Orchestration epoch: `2026-09-08`
- Role: `devops-executor`
- Invocation status: `done`
- Target: `root@175.155.64.171:24052`
- Run: `p0-s25-v43-live-r3`

## Summary

The authorized stalled R3 vehicle and engine were stopped. No replacement run was launched. No remote file, event log, storage, checkout, or evidence directory was deleted or mutated.

## Pre-action verification

Read-only SSH verification confirmed:

- PID `999350`: vehicle command line was `/root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py --events /tmp/t38c-probe.log ... --evidence-dir /root/evidence-gate3-parked/p0-s25-v43-live-r3/vehicle --run-id p0-s25-v43-live-r3 ...`; environment contained `T38C_RUN_ID=p0-s25-v43-live-r3`; CWD `/root/sglang-b1-continuity`.
- PID `998868`: engine command line was `/root/miniconda3/envs/sglang-patch/bin/python3 -m sglang.launch_server ... --port 8024`; environment contained `T38C_RUN_ID=p0-s25-v43-live-r3`; CWD `/root/sglang-b1-continuity`.
- No attached child was present in the initial process listing.
- `/tmp/t38c-probe.log`: regular file, `842624366` bytes before action.
- `/tmp/t38c-durable-trace`: regular empty file, `0` bytes before action.

## Actions and outputs

1. Sent `SIGTERM` to exactly `999350` and `998868`; `kill_term_rc=0`.
2. Polling showed vehicle `999350` became `[python] <defunct>`, while engine `998868` remained live through ten one-second polls.
3. A launcher child `998916` appeared as defunct during post-SIGTERM inspection.
4. Issued the authorized escalation `kill -KILL 998868`; the command returned `kill: (998868) - No such process` and `rc=1`, because the engine exited between the preceding observation and the KILL attempt. The immediate verification showed no process for `998868`.

## Post-action verification

- `ps` showed no process for authorized PIDs `999350` or `998868`.
- The previously observed child `998916` was also absent at final verification.
- `/tmp/t38c-probe.log`: still present as a regular file, `842782347` bytes.
- `/tmp/t38c-durable-trace`: still present as a regular empty file, `0` bytes.
- No residual authorized process remained.

## Evidence and open issues

The remote evidence paths observed and preserved were `/tmp/t38c-probe.log`, `/tmp/t38c-durable-trace`, and the vehicle evidence directory `/root/evidence-gate3-parked/p0-s25-v43-live-r3/vehicle` as referenced by the verified command line. The event log grew from `842624366` to `842782347` bytes before final shutdown; it was not modified by this task.

Followup: the single 3090 is available for a separately authorized run after the code-gate and `build_complete` contract decisions.

Open issues: none for this cleanup. The underlying R3 runtime/instrumentation gaps remain as documented in `DEBUG-20260908-P0-R3-V3-GAP.md`.
