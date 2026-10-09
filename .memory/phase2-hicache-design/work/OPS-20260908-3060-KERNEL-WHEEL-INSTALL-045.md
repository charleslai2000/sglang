# OPS-20260908-3060-KERNEL-WHEEL-INSTALL-045

Task ID: D3060-KERNEL-WHEEL-INSTALL-045  
Orchestration epoch: 20260908-3060  
Role: devops-executor  
Status: done (installation complete; runtime import verification reports an ABI/runtime failure)

## Scope and authorization

Remote target: `root@i-1.gpushare.com:27460` (password omitted).  
Allowed procedure: copy/rename the verified wheel, verify unchanged SHA256, install with the specified pip command, and run the specified metadata/import/Torch/basic-symbol checks. No Torch upgrade, rebuild, download, server start, benchmark, 3090 modification, or source/data deletion was performed.

## Commands and outputs

Connection and remote procedure (secret omitted):

```sh
ssh -p 27460 root@i-1.gpushare.com
src=/hy-tmp/sglang_kernel-0.4.6.post1.whl
dst=/hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl
cp -p "$src" "$dst"
sha256sum "$src" "$dst"
/root/sglang-env-3060-4b/bin/pip install --no-deps --force-reinstall "$dst"
/root/sglang-env-3060-4b/bin/pip show sglang-kernel
```

Observed:

```text
REMOTE_HOST=I2aff9805ac001019d1
SOURCE_STAT=377094734 /hy-tmp/sglang_kernel-0.4.6.post1.whl
SOURCE_SHA256=5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04  /hy-tmp/sglang_kernel-0.4.6.post1.whl
TARGET_STAT=377094734 /hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl
TARGET_SHA256=5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04  /hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl
Successfully installed sglang-kernel-0.4.6.post1
Name: sglang-kernel
Version: 0.4.6.post1
Location: /root/sglang-env-3060-4b/lib/python3.11/site-packages
Requires:
Required-by: sglang
```

Verification command:

```sh
/root/sglang-env-3060-4b/bin/python - <<'PY'
import torch
import sgl_kernel
PY
```

Observed verification:

```text
PYTHON=/root/sglang-env-3060-4b/bin/python
TORCH_VERSION=2.5.1+cu124
TORCH_CUDA_AVAILABLE=True
TORCH_CUDA_VERSION=12.4
SGL_KERNEL_IMPORT_ERROR=ImportError: [sgl_kernel] CRITICAL: Could not load any common_ops library!
GPU Info:
- Compute capability: 86
- Expected variant: SM86 (precise math for compatibility)
- CUDA version: 12.4
Error details from previous import attempts:
- ImportError: libnvrtc.so.13: cannot open shared object file: No such file or directory
- ModuleNotFoundError: No module named 'common_ops'
```

The basic `sgl_kernel` symbol/op check could not run because importing `sgl_kernel` failed. No additional remediation or alternative procedure was attempted.

## Changed resources

- Created `/hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl` via `cp -p`; size and SHA256 match the source.
- Reinstalled `sglang-kernel==0.4.6.post1` in `/root/sglang-env-3060-4b` using `--no-deps --force-reinstall`.
- Source wheel and existing data were not deleted or modified.

## Evidence and followups

Installation and pip metadata verification passed. Torch CUDA verification passed. `sgl_kernel` import/basic symbol verification is blocked by the exact runtime error above: missing `libnvrtc.so.13` and consequent missing `common_ops` import. Follow-up requires a new Task ID and authorization; no follow-up was performed.

Open issues: runtime import remains unresolved; ABI/runtime usability is not confirmed.
