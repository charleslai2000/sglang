# G3-IQ3 local smoke retry5 — 2026-09-09

Invocation: `INV-G3-IQ3-LOCAL-SMOKE-006`; stable task `G3-IQ3-LOCAL-SMOKE-20260909`; epoch E18; role devops-executor.

Status: **blocked**.

## Procedure

Full frozen `prepare_server_args()` preflight ran with `CUDA_VISIBLE_DEVICES=''` and exited 0. GPU work was enclosed by `flock -x /mnt/data/gpu/3090.lock`; GPU1 was selected with `CUDA_VISIBLE_DEVICES=1`. Service target was loopback `127.0.0.1:18035`, own launch only. No user process, driver, CUDA, repository, or production service was changed.

Launch command:

```text
CUDA_VISIBLE_DEVICES=1 PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/python /mnt/data/qwen3-g3-baseline/venv/bin/python -m sglang.launch_server --model-path /mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 18035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs '{"preserve_thinking": false}'
```

Intended runner (not reached because server startup failed): `sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:18035 --dataset-name random-ids --random-input-len 2048 --random-output-len 512 --random-range-ratio 1.0 --request-rate inf --seed 42 --num-prompts 1 --max-concurrency 1 --tokenize-prompt --output-details`.

## Outcome

- Preflight: PASS.
- Server: FAIL before bind/health. Exit traceback is preserved in `server.log`.
- Blocking error: `ModuleNotFoundError: No module named 'compressed_tensors'` while importing `sglang.srt.model_loader`.
- Health: not reached; no successful request; no exact-length server receipt evidence.
- Teardown: own failed launch PID 458884 was cleaned; port 18035 is not listening; GPU1 has no benchmark compute process.
- Residual cleanup: exact original wrapper tree PIDs 458488/458879 (child sleep 464040) was terminated after identity check; lock is released and port 18035 remains free. Evidence: `raw/g3-iq3-local-smoke-retry5-20260909/cleanup.txt`.
- The torch warning about GT 1030 is incidental; process used `CUDA_VISIBLE_DEVICES=1`.

## Artifacts

Remote/local artifact directory: `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry5/`.
Raw evidence: `.memory/g3-baseline-20260907/work/raw/g3-iq3-local-smoke-retry5-20260909/`; SHA256SUMS is included.

## Follow-up

Fresh invocation required after the environment owner installs the approved `compressed_tensors` dependency into the venv (using the prepared hash-locked wheelhouse). Do not change workload or launch flags.

Open issue: venv dependency set is incomplete; smoke cannot proceed.
