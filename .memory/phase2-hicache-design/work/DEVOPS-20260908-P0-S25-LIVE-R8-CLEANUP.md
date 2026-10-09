# DEVOPS-20260908-P0-S25-LIVE-R8-CLEANUP

- Task ID: `DEVOPS-20260908-P0-S25-LIVE-R8-CLEANUP`
- Orchestration epoch: `2026-09-08`
- Host: `175.155.64.171:24052`
- Run ID: `p0-s25-v43-fix2-live-20260908T003948Z`

## Result

done

The stalled R8 diagnostic was stopped using the authorized procedure. No evidence,
storage, or log paths were deleted or mutated. No replacement run was launched.

## Pre-action verification

Engine PID `1012101` matched the requested `sglang.launch_server` command and port
`8024`. Vehicle PID `1012623` matched the requested run ID and evidence path.
Vehicle launcher PID `1012622` was the verified parent of the vehicle process.
Engine children observed were `1012145` (resource tracker), `1012146`
(scheduler), and `1012147` (detokenizer).

Pre-action process check output:

```text
1012101       1 Sl   /root/miniconda3/envs/sglang-patch/bin/python3 -m sglang.launch_server ... --port 8024
1012145 1012101 S    ... multiprocessing.resource_tracker ...
1012146 1012101 Rl   sglang::scheduler
1012147 1012101 Sl   sglang::detokenizer
1012622       1 Ss   bash -c ... p0_session_barrier_vehicle.py ... --run-id p0-s25-v43-fix2-live-20260908T003948Z ...
1012623 1012622 Sl   ... p0_session_barrier_vehicle.py ... --run-id p0-s25-v43-fix2-live-20260908T003948Z ...
```

The full command-line verification included the exact vehicle evidence directory
`/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8/vehicle` and run ID.

Preservation pre-check:

```text
directory 4096 1788828103 /root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8
directory 4096 1788827958 /root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8/vehicle
regular file 464782 1788828274 /tmp/t38c-probe.log
```

## Action and verification

Sent `SIGTERM` only to verified matching engine `1012101`, vehicle `1012623`,
and attached vehicle launcher `1012622`. Waited up to 10 seconds, checking each
second.

The verified matching engine exited during the wait, so no `SIGKILL` escalation was
performed. Post-term target check and final matched-process check both returned no
lines. Zero residual matching engine, vehicle, launcher, or descendants remained.

Preservation post-check:

```text
directory 4096 1788828103 /root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8
directory 4096 1788827958 /root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8/vehicle
regular file 464782 1788828274 /tmp/t38c-probe.log
```

## Changed resources

- Processes stopped: `1012101`, `1012623`, `1012622`.
- No files or evidence/storage/log resources changed by this cleanup.

## Open issues

None for the authorized cleanup.

## Followups

None.
