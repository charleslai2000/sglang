# G3-PROFILE-C-C1-LAUNCH-FIX-20260908

ENTRY: ACCEPT

status: blocked
invocation_status: blocked
task_id: G3-PROFILE-C-C1-LAUNCH-FIX-20260908
epoch: E4
role: devops-executor

## Result

Corrected argv-array launch was executed once under fresh RUN_ID
`g3-profile-c1-fix-20260907T184841Z`. The JSON argument arrived correctly;
the log records `default_chat_template_kwargs: {'preserve_thinking': False}`.
Candidate PID `476413` allocated weights/Mamba/KV and entered CUDA graph capture,
but never reached health/admission before the bounded launch gate expired.
No benchmark traffic or dmon ran. Candidate was stopped and exact v1 was
started on 8035; restoration reached HTTP 200 and idle loads.

Remote artifacts: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-fix-20260907T184841Z/c1-fix/launch/`.

## Evidence

- candidate command is in `command`; it uses a bash argv array and `%q` output.
- candidate log shows effective `max_running_requests=4`, `max_mamba_cache_size=20`,
  `cuda_graph_max_bs_decode=4`, JSON template value, weights 11.86GB, Mamba
  allocation 3.01GB, KV allocation 4.52GB, then prefill graph capture.
- candidate health remained 000; `loads` empty; listener absent; final admission
  is `ADMISSION=FAIL`.
- rollback PID `477405` exact v1 command; final health 200, loads idle,
  effective v1 max_running_requests 5 and max_total_num_tokens 132436.

## Summary / followups / open issues

Summary: corrected quoting fixed the prior argparse failure, but this attempt
did not admit C1 because graph capture did not complete within the bounded gate.
The process argv is `/data/sglang-qwen35-env/bin/python -m sglang.launch_server`,
matching the preserved successful launch method; the prior `sglang serve` text is
not the actual canonical argv used by the preserved v1 process.

Followup: any retry requires a fresh Task ID and explicit timing/launch authority.
Open issue: no effective candidate admission or performance result exists.

Final status: **blocked**
