# G3-E3-PROFILE-B-LAUNCH-20260908

ENTRY: ACCEPT

status: blocked
invocation_status: blocked
task_id: G3-E3-PROFILE-B-LAUNCH-20260908
epoch: E3
role: devops

## Artifacts

- Remote run root: `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T165140Z/`
- Local practical raw copy: `.memory/g3-baseline-20260907/work/raw/g3-e3-profile-b-20260907T165140Z/`
- Halt marker: `launch/HALTED.txt`
- Pre-transition evidence: `pre-transition/`
- Existing-v1 retention verification: `restore/` (no restore launch was needed because transition never started)

## Evidence and observed facts

- The complete pre-transition capture was completed on authorized host
  `root@175.155.64.171:22109` at `2026-09-07T16:52:39Z`.
- PID `298123` was reverified as the exact v1 command from the runbook, with
  direct `/proc/298123/cmdline` SHA-256
  `750ac48907968dacfd3175b1547a1cd8b9b89cc3eeaa5ebfd625ce221717d200` and
  normalized command SHA-256
  `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`.
  Its cwd is `/data/sglang-qwen35`.
- v1 `/health` returned HTTP 200; `/v1/loads?include=all` was idle with
  `num_running_reqs=0`, `num_waiting_reqs=0`, effective
  `max_running_requests=5`, and effective `max_total_num_tokens=132436`.
- Port 8035 was owned by PID `298123`; port 8036 was free. No benchmark,
  `dmon`, or matching client process was observed in the captured process scan.
- Model MD5 was unchanged at
  `a37cff66ad81b0e6311d4b6671ac2b09`; runner SHA-256 was
  `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`; and
  `server_args.py` SHA-256 was
  `aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9`.
- GPU query reported `0%` utilization, 24,576 MiB total, 22,912 MiB used,
  and 1,213 MiB free. However, compute accounting reported exactly one entry:
  `PID 315744, process_name [Not Found], 22888 MiB`. `/proc/315744` was
  absent and `pstree` could not attribute it to PID 298123. This is an
  unattributable GPU owner and fails the hard admission gate.

## Decision and safety outcome

Admission was **HALTED before transition**. PID `298123` was not signaled,
there is no Profile-B PID, no 8036 health check was attempted, and no
benchmark request or traffic was sent. No process tree was stopped or killed.
The already-running v1 service was retained and reverified after the failed
gate: health 200, idle loads, 8035 owned by PID 298123, 8036 absent, exact
v1 command hashes, model MD5, and source hashes unchanged. The remote
`restore/V1_RETAINED.txt` records this no-transition outcome; a new v1 launch
was intentionally not attempted because it would conflict with the healthy
existing v1 service.

Profile-B admission results:

| Gate | Result |
|---|---|
| v1 exact PID/cmdline, health, idle loads | PASS |
| 8036 free before transition | PASS |
| no benchmark/dmon process | PASS |
| exclusive attributable GPU compute owner | FAIL: stale/unattributable PID 315744 |
| B launch, B health/capacity, startup flags | NOT RUN |
| rollback/retained v1 verification | PASS (no-transition retention) |

The exact B command hash and B effective capacity are `N/A` because B was not
launched. A fresh Task ID is required only after the stale/unattributable GPU
compute entry is resolved and the dynamic gates are rechecked.

## Summary

Profile-B launch/admission is blocked safely at the pre-transition GPU-owner
gate. Existing v1 remains healthy and unchanged; all pre-transition and
post-decision evidence is preserved in the remote run root and local raw copy.

## Followups

- Resolve the stale `[Not Found]` GPU compute accounting entry outside this
  task's scope, then obtain a fresh Task ID for another admission attempt.
- Recheck all dynamic gates from the runbook before any future signal.

## Open issues

- `nvidia-smi` continues to report 22,888 MiB against absent PID `315744`;
  its cause was not diagnosed or altered under this launch task.
- `/metrics` and usable `pmon` attribution remain unavailable as documented
  by the runbook.

Final status: **blocked**
