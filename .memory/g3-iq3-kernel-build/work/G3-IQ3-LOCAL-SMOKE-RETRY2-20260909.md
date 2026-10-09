# G3-IQ3-LOCAL-SMOKE-RETRY2-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-SMOKE-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-SMOKE-003`
- Epoch: `E15`
- Role: `devops-executor`
- Status: **blocked**

## Scope and preflight

Executed only on the local host, targeting GPU1 (RTX 3090), port `18035`, with the
authorized venv, checkout, and IQ3_S GGUF. With `CUDA_VISIBLE_DEVICES=''`, imports
passed: `torch 2.13.0+cu130`, `sglang 0.5.20.dev16+g5c5f5e3b2`. The model file exists
and is 11,771,546,784 bytes; SHA-256 is
`64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
Port `18035` was free and GPU1 was idle before launch.

## Exact execution

Acquired `/mnt/data/gpu/3090.lock` with `flock -x`. Started the authorized isolated
server command using `CUDA_VISIBLE_DEVICES=1`, port `18035`, and the frozen parser,
KV, Mamba, and chat-template flags. Server PID was `439529`.

The server exited before health became 200 (iteration 4). The retained traceback shows
startup import failure:

`ModuleNotFoundError: No module named 'partial_json_parser'`

Consequently no benchmark request was sent, no GGUF was loaded, and no other process
was touched. The invocation's server PID was confirmed exited; port `18035` is free;
the GPU lock was released. No product files, driver, CUDA, or user processes changed.

## Artifacts

Raw artifacts:
`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-smoke-retry2-20260909/`

This contains queue timing, server PID/log, runner help, post-check GPU telemetry, and
`SHA256SUMS`. The copied artifact directory is
`/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry2/`.

## Follow-up / open issue

Install the already-required, approved `partial_json_parser` dependency in the venv,
then create a fresh linked invocation before retrying. No workload substitution is
authorized.
