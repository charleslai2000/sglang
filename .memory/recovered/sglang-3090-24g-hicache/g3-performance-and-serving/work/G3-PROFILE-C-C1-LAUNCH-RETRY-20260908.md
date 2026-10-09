# G3-PROFILE-C-C1-LAUNCH-RETRY-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-C1-LAUNCH-RETRY-20260908
epoch: E4
role: devops-executor

## Result

Candidate retry was halted before startup because the exact command was rejected
by argparse: shell quoting removed the JSON value for
`--default-chat-template-kwargs`, producing `'{preserve_thinking:'`. No
benchmark traffic, dmon, query sampler, source/model edit, or GPU reset ran.

The failed candidate PID `474559` exited. The authorized rollback was performed
with corrected quoting and exact frozen v1 flags on port 8035. Final v1 health
is HTTP 200; the service is idle. C1 is not admitted and must not be retried
under this task.

## Commands and evidence

Remote RUN_ID: `g3-profile-c1-retry-20260907T184200Z`

Remote artifacts:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-retry-20260907T184200Z/c1-retry/launch/`

- Preflight captured current v1 PID `472940`, exact cmdline/tree, health/loads,
  port state, GPU query, and device handles.
- Only numeric PID `472940` was TERM-stopped after identity verification;
  8035 became free and no candidate listener existed.
- Candidate PID `474559` was launched once with tuple `(4,20,4)`. Its log ends
  with `sglang serve: error: argument --default-chat-template-kwargs:
  invalid loads value: '{preserve_thinking:'`; it never reached health.
- `HALTED.txt`, `failure.ps`, `command`, `pid`, `c1-retry.log`, and hashes
  preserve the failed attempt.
- Rollback PID `475000` runs the exact frozen v1 `launch_server` command with
  PATH including `/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin`.
- Final `restore.health` is HTTP 200 and `restore.loads` reports zero running
  and waiting requests. Final listener is only 127.0.0.1:8035. Port 18035 is
  absent. `restore.cmdline`, `restore.ps`, `restore.gpu`, `restore.fuser`, and
  `restore-v1.log` provide identity, allocation, and owner evidence.

## Verification

Observed final rollback health: HTTP 200 at `127.0.0.1:8035`.
Observed final server log completion includes detokenizer GC freeze and idle
prefill state (`#running-req: 0`, `#queue-req: 0`). No C1 request was sent.

## Summary / followups / open issues

Summary: retry failed closed at argument parsing; frozen v1 restoration passed.
Followup: a fresh Task ID is required for any corrected C1 retry.
Open issue: candidate retry was not admitted; no effective C1 capacity or
performance result exists.

Final status: **done**
