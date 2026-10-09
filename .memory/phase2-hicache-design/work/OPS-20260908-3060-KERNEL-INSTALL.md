# OPS-20260908-3060-KERNEL-INSTALL

- Task ID: `D3060-KERNEL-INSTALL-015`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Entry: `ACCEPT`
- Status: `blocked`
- Target: `root@i-1.gpushare.com:27460`
- Environment: `/root/sglang-env-3060-4b`

## Scope and authorization

Attempted only the official `sglang-kernel==0.4.6.post1` installation with no dependencies, pip timeout 300 seconds and retries 1. Torch was not upgraded. No model, server, benchmark, or 3090 action was performed. The supplied SSH password was not printed.

## Commands and evidence

Remote identity and baseline:

```text
uid=0
host identity: I2aff9805ac001019d1
time: 2026-09-08T21:04:07+08:00
torch: 2.5.1+cu124
sglang-kernel: not installed
```

No complete cached wheel was found before installation. The exact install attempt selected:

```text
python -m pip install --no-deps --only-binary=:all: --timeout 300 --retries 1 sglang-kernel==0.4.6.post1
Downloading sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl (377.1 MB)
```

The transfer produced no completion, success, or error output during the execution window and the SSH session was stopped after it remained stalled well beyond the requested timeout. Final read-only inspection found only incomplete temporary pip downloads:

```text
/tmp/pip-unpack-sv7d_dq9/...whl 191889408 bytes
/tmp/pip-unpack-1m77l4l8/...whl 17039360 bytes
/tmp/pip-unpack-plosyort/...whl 17301504 bytes
/tmp/pip-unpack-bmssno5c/...whl 112721920 bytes
/tmp/pip-unpack-sac80bi9/...whl 112721920 bytes
```

No install was completed. The requested bounded AOT/JIT fallback was not started because the official install command remained active/stalled until the session was stopped; no valid wheel was available to proceed from.

## Verification

Final remote checks showed:

```text
pip show sglang-kernel: not found
sgl_kernel: ModuleNotFoundError
sglang.srt.layers.marlin: ModuleNotFoundError: No module named 'orjson'
sglang.srt.layers.quantization.marlin: KeyError: 'sglang'
```

Torch remained `2.5.1+cu124`. No package install or Torch change was observed.

## Changed resources

- Temporary incomplete pip-unpack files were created by pip under `/tmp`.
- No installed package, repository source, model, server, benchmark, or GPU configuration was changed.
- This report is the only requested persistent artifact.

## Summary

The official wheel download did not complete, and `sglang-kernel` remains absent. Installation and import verification are therefore incomplete. The operation is blocked on the remote package transfer.

## Followups

Retry the official install or run the bounded repository fallback only under a fresh Task ID, as required by the orchestration contract.

## Open issues

- The remote mirror transfer stalled without a concrete pip error.
- No valid complete wheel was found in cache or temporary paths.
- Marlin-related imports cannot be treated as installed-module verification while `sglang-kernel` is absent and the existing SGLang import environment lacks `orjson`.
