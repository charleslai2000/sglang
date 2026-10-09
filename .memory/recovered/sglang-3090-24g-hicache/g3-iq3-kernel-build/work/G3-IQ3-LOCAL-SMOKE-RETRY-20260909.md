# G3-IQ3-LOCAL-SMOKE-RETRY-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-SMOKE-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-SMOKE-002`
- Epoch: `E14`
- Status: **blocked**

## Scope and queue

The authorized queue was acquired with `flock -x /mnt/data/gpu/3090.lock`. GPU1
(RTX 3090) was idle before launch. Only port `127.0.0.1:18035` was checked and
used. No other process was stopped or modified.

## Exact launch

```text
CUDA_VISIBLE_DEVICES=1 PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/python /mnt/data/qwen3-g3-baseline/venv/bin/python -m sglang.launch_server --model-path /mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 18035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs '{"preserve_thinking": false}'
```

The process exited during Python imports with:
`ModuleNotFoundError: No module named 'openai'`.
Consequently no server PID became active, no health request or benchmark request
was sent, and no GGUF weights were loaded.

## Cleanup and evidence

- Port 18035: free after failure.
- Queue lock: free after failure.
- GPU1 after failure: 53 MiB, 0% utilization, 40 C.
- Raw artifacts:
  - `raw/g3-iq3-local-smoke-retry-20260909/queue.log`
    SHA256 `4f6938a763ab5a5cb222796a9d1d4ca1c108883a1e4db11f40b64a8e286a5140`
  - `raw/g3-iq3-local-smoke-retry-20260909/server.log`
    SHA256 `b1913becf8dd8eada115d7d9a7ebae8ca69eba3ddae779913d07323f7f6c8e76`

## Open issue / follow-up

The venv has `dill==0.4.1` but does not contain `openai`. A fresh invocation is
required to install/repair the approved dependency set, then retry the exact
smoke. No workaround or alternate workload was used.
