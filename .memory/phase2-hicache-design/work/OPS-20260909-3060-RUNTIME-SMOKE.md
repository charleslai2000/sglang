# OPS-20260909-3060-RUNTIME-SMOKE

Status: blocked
Task: D3060-OPS-082, orchestration epoch 2026-09-09
Role: devops-executor

## Summary

The bounded runtime smoke was not launched. Preflight confirmed the authorized
RTX 3060/SM86 host and staged `sgl_kernel` resolution. The required
`launch_server --help` procedure cannot import in the existing protected venv:
`ModuleNotFoundError: No module named 'dill'`. Installing dependencies or
modifying site-packages is outside the authorization, so execution stopped
before server launch.

## Scope and safeguards

- Remote target: `root@i-1.gpushare.com:27460`, BatchMode SSH key
  `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Read-only preflight only; no server, model, staging, source, or venv files
  were modified.
- No local product, 3090 branch, or installed site-packages were modified.
- No BF16 run, capacity sweep, HiCache, or RH operation was started.

## Commands and evidence

1. Initial reviewed-commit check:

   `git -C /root/sglang-3060-12g-hicache rev-parse HEAD`

   Output: `fatal: not a git repository (or any of the parent directories): .git`.
   The authorized source directory exists but has no `.git` metadata at that
   path, so the supplied commit could not be independently checked with this
   command.

2. Authorized paths exist:

   - `/root/sglang-3060-12g-hicache`
   - `/hy-tmp/ops-081-sm86-import-20260909`
   - `/hy-tmp/models/Qwen3.5-4B-AWQ`
   - `/root/sglang-env-3060-4b`

3. Python/CUDA preflight output:

   - Python: `/root/sglang-env-3060-4b/bin/python`
   - Torch: `2.5.1+cu124`
   - CUDA: `12.4`
   - GPU: `NVIDIA GeForce RTX 3060`
   - Capability: `(8, 6)` (SM86)
   - Memory before launch: free `12508921856`, total `12622168064` bytes

4. Staged kernel import:

   Command used `PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python`.

   Output: `SGL_KERNEL /hy-tmp/ops-081-sm86-import-20260909/sgl_kernel/__init__.py`

   This is evidence that the staged package is first on the import path. No
   `libnvrtc13` or SM100 import was observed during this check.

5. Required help inspection:

   `PYTHONPATH=... /root/sglang-env-3060-4b/bin/python -m sglang.launch_server --help`

   Import failed before help output:

   `ModuleNotFoundError: No module named 'dill'`

## Verification

Verified: host access, authorized directories, SM86 capability, CUDA runtime,
and staged `sgl_kernel` path.

Not performed: launch-server flag verification, model config/quantization
summary, server boot, GPU memory after boot, backend/kernel runtime evidence,
HTTP readiness, completion request, TTFT/latency, and clean server shutdown.

## Followups

Provide a fresh Task ID and explicit authorization for an equivalent method that
does not modify the protected venv (for example, an already-approved complete
runtime environment containing `dill`), or authorize the required dependency
change. Then rerun the exact bounded smoke.

## Open issues

- Required launch help is blocked by missing `dill` in `/root/sglang-env-3060-4b`.
- Reviewed commit `032bbe7e38f2b06c0efb01bdfb5baa79532974e3` could not be checked
  because the supplied source path is not a Git working tree.
