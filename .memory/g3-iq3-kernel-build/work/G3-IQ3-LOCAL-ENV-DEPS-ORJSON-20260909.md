# G3-IQ3-LOCAL-ENV-DEPS-ORJSON-20260909

status: blocked
task_id: G3-IQ3-LOCAL-ENV-DEPS-ORJSON
invocation_id: INV-G3-IQ3-LOCAL-ENV-DEPS-ORJSON-001
epoch: E34
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s

## Summary

`pwd` matched the bound workdir. Installed only `orjson` into the existing task
venv using `sg dev -c` and shared `PIP_CACHE_DIR`. `torch` imports, but SGLang
now stops at the next missing dependency, `pybase64`.

## Evidence

Logs: `/mnt/data/qwen3-q3-baseline/artifacts/env-rebuild-orjson-001-20260909.log`
and `env-rebuild-import-orjson-001-20260909.log` (under `/mnt/data/qwen3-g3-baseline/artifacts/`).
Exact failure: `ModuleNotFoundError: No module named 'pybase64'`.

## Followups

Fresh dispatch to install only `pybase64`, then rerun imports.

## Open issues

- `import torch, sglang` remains incomplete due to missing `pybase64`.
