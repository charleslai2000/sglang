# G3-PROFILE-C-C1-RESTORE-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-C1-RESTORE-20260908
epoch: E4
role: devops-executor

## Result

Restored frozen v1 on the authorized experimental host after the C1 decode
pre-run guard halted. No benchmark traffic, dmon, client, or query telemetry
was sent.

## Evidence

- Candidate PID 470950 was identity-checked against the captured Python SGLang
  argv (`sglang serve`, `--port 18035`) and stopped; explicit descendants were
  captured. Port 18035 is absent.
- Remote artifacts: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-20260907T182700Z/c1/restore/`.
- Final v1 launch PID wrapper: 473868; health HTTP 200 on 127.0.0.1:8035.
- `/v1/loads?include=all`: idle, `max_running_requests=5`,
  `max_total_num_tokens=121394`, one RTX 3090.
- Final GPU evidence: one attributable SGLang worker (`494253`, driver name
  `[Not Found]`, 22294 MiB); no benchmark/dmon/18035 processes.
- Frozen command is preserved in `restore/v1.command`, including required PATH,
  model, parser/tool parser, fp8 KV, extra_buffer_lazy Mamba, and
  `preserve_thinking=false` flags.
- Model MD5: `a37cff66ad81b0e6311d4b6671ac2b09`.
- `server_args.py` SHA-256:
  `aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9`.
- Runner SHA-256:
  `cb2a23d0edf050772091777bf72335fb6a55b74770a37c0af118cccaec335dbd`.

## Preserved failure evidence

An initial wrapper-form attempt and its explicit stop are recorded as
`incorrect-attempt.*`; the exact recorded `python .../sglang serve` command
was then used. A subsequent startup reached CUDA OOM while stale C1 worker
allocation remained; `failed-v1.*` and `post-failed-gpu.txt` preserve that
evidence. The failed worker was explicitly identified and stopped before the
successful final launch. No flags were weakened or improvised.

## Followups

No C1 measurement exists; any corrected decode requires a fresh Task ID.

## Open issues

None for v1 restoration. Profile-C C1 remains blocked by the decode guard halt.

Final status: **done**
