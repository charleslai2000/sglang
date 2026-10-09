# G3 Profile C6 launch report

- Task ID: `G3-PROFILE-C-C6-LAUNCH-20260908`
- Invocation status: `blocked`
- Target: `175.155.64.171:22109`
- Intended candidate: loopback `127.0.0.1:18036`, `max-running-requests=6`, `max-mamba-cache-size=32`, `cuda-graph-max-bs-decode=8`
- Remote artifact directory: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-20260908/launch/`

## Result

The candidate did not start. The first launch exited before model loading because the
shell quoting of `--default-chat-template-kwargs` reached SGLang as
`'{preserve_thinking:false}'`; the runner reported `invalid loads value`. There was no
candidate listener, request traffic, CUDA graph capture, or candidate GPU allocation.
This is a launch-command quoting failure, not an OOM or capacity result.

The authorized rollback restored the unchanged v1 service on port 8035. Health returned
200 and `/v1/loads?include=all` was idle; the observed restored service reported
`max_running_requests=5`, `max_total_num_tokens=132436`, weights 11.857 GB, KV 4.042 GB,
graphs 1.955 GB. GPU query at 2026-09-08T03:31:39+08:00 showed 22800 MiB used and
1325 MiB free, with no candidate PID remaining.

## Commands and evidence

The executed candidate command used `/data/sglang-qwen35-env/bin/python -m
sglang.launch_server`, model `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, host `127.0.0.1`, port
`18036`, frozen parser/KV/cache/template flags, and the three C6 capacity flags. It
failed before startup. The rollback used the same frozen v1 flags on port 8035 and
completed successfully.

Raw logs and command evidence are retained remotely:

- `server.log` (candidate parse failure)
- `rollback2.log` (successful v1 restore)
- `evidence.txt` (PID, health, loads, GPU query)
- `rollback2.pid`

Model SHA-256 was not emitted in the short evidence capture because the command exited
before that query completed; no model identity was changed.

## Follow-up

Retry requires a fresh task ID with argv-safe JSON quoting, then repeat the admission and
CUDA-graph gates. No benchmark traffic was sent and no product files were modified.

