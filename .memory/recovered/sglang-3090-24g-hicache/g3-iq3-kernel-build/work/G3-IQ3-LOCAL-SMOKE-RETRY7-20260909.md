# G3-IQ3-LOCAL-SMOKE-RETRY7-20260909

Status: blocked

## Scope

本机 GPU1 隔离 smoke；模型为 `/mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`，端口 18035，共享锁 `/mnt/data/gpu/3090.lock`。未启动正式 GPU smoke，未触碰其他进程、驱动、CUDA 或仓库产品代码。

## Evidence

- Offline wheelhouse installation completed with `pip install --no-index --require-hashes -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt --find-links /mnt/data/qwen3-g3-baseline/wheels`; all 29 requirements already satisfied, including `torch==2.13.0+cu130`.
- Preflight `prepare_server_args()` with `CUDA_VISIBLE_DEVICES=''` and exact frozen server argv returned `PREPARE_SERVER_ARGS_OK`.
- GPU inventory before launch: GPU1 RTX3090, 53 MiB / 24576 MiB, 0% utilization; port 18035 unused; lock was free.
- Foreground launch under `flock -x /mnt/data/gpu/3090.lock`, `CUDA_VISIBLE_DEVICES=1`, exact requested model/server flags, exited before model load with:
  `ModuleNotFoundError: No module named 'sgl_kernel'`.
- The venv has editable `sglang 0.5.20.dev16+g5c5f5e3b2` and `flashinfer-python 0.6.17`, but no `sgl_kernel` package or wheel was present in the supplied wheelhouse.
- No service remained running; no request was sent; no GPU test was started. Model partial/download files were not modified or removed.

## Blocker

The defined launch cannot proceed until the matching `sgl_kernel` runtime extension is provided/installed. This invocation did not select an alternative source or procedure.

## Raw artifacts

- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry7/preflight.txt`
- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry7/pip-install.log`
- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry7/env-check.txt`
- `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry7/server.log` (initial background attempt; empty)

## Follow-up

Provide the checkout-compatible `sgl_kernel` wheel/shared extension (including native SM86 if applicable), with provenance and hash. Then dispatch a fresh invocation for the smoke; no work was broadened here.

## Open issues

- `sgl_kernel` dependency/extension unavailable in venv.
