# G3-IQ3-LOCAL-ENV-DEPS-STARLETTE-20260909

status: blocked
task_id: G3-IQ3-LOCAL-ENV-DEPS-STARLETTE
invocation_id: INV-G3-IQ3-LOCAL-ENV-DEPS-STARLETTE-001
epoch: E38
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s

`pwd` matched the bound workdir. Installed only `starlette` using `sg dev -c`
and shared `PIP_CACHE_DIR=/mnt/data/cache/pip`. Torch imports; SGLang now fails
on missing `torchvision` (`from torchvision.io import decode_jpeg`).

Logs: `/mnt/data/qwen3-g3-baseline/artifacts/env-rebuild-starlette-001-20260909.log`
and `env-rebuild-import-starlette-001-20260909.log`.

Followup: fresh dispatch to install only the matching `torchvision` package.

Open issue: `import torch, sglang` acceptance remains incomplete.
