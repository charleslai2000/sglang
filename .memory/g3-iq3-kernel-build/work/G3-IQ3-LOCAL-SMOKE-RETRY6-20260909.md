# G3-IQ3-LOCAL-SMOKE-RETRY6-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-SMOKE-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-SMOKE-007`
- Epoch: `E19`
- Role: `devops-executor`
- Invocation status: `blocked`

## Executed scope

The requested CUDA-disabled `prepare_server_args()` preflight was executed against
the local editable checkout using the approved GGUF path and frozen server
arguments. The corrected option names are `--tp-size 1` and `--pp-size 1`.

The exact preflight command was the Python stdin command recorded in the shell
history/output for this invocation; it used:

```text
CUDA_VISIBLE_DEVICES=''
/mnt/data/qwen3-g3-baseline/venv/bin/python
prepare_server_args([
  --model-path /mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf,
  --host 127.0.0.1, --port 18035, --tp-size 1, --pp-size 1,
  --trust-remote-code, --reasoning-parser auto,
  --tool-call-parser qwen3_coder, --kv-cache-dtype fp8_e4m3,
  --mamba-radix-cache-strategy extra_buffer_lazy,
  --default-chat-template-kwargs '{"preserve_thinking": false}'
])
```

It completed successfully: `PREPARE_SERVER_ARGS_OK`, exit code `0`.

## Boundary and outcome

The GPU phase was not completed. The attempted shell invocation was interrupted
by the user while waiting for/starting the queued operation; no durable evidence
of lock acquisition, server PID, health response, runner request, telemetry, or
teardown was produced. Current process inspection found no own SGLang server or
queue wrapper. No GPU, driver, CUDA, repository, or other process was changed.

Model file observed:

```text
/mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
11771546784 bytes
```

Artifacts:

- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry6/preflight.stdout`
- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry6/preflight.stderr`
- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry6/preflight.exit` (`0`)

## Open issues / follow-up

- The one-request GPU smoke remains pending and requires a fresh invocation after
  the queue owner confirms the GPU is available.
- No server was started, so tokenizer sidecar/runtime loading still needs to be
  tested under the original scope.
- Extra work requires a fresh linked Task ID/invocation.
