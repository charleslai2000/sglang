# G3-IQ3-LOCAL-READY-SCAN-20260909

Task ID: `G3-IQ3-LOCAL-READY-SCAN-20260909`  
Invocation: `INV-G3-IQ3-LOCAL-READY-SCAN-001`  
Epoch: `E11`  
Role: `scout`  
Status: `done` (read-only)

## Scope and safety

Checked only the local workstation and current repository. No GPU workload was
started or stopped; no package/model download or installation was attempted;
no user process was attached to.

## Observed local state

`nvidia-smi -L` reports:

```text
GPU 0: NVIDIA GeForce GT 1030
GPU 1: NVIDIA GeForce RTX 3090
```

At scan time, GPU1 was idle apart from the desktop allocation:

```text
1, NVIDIA GeForce RTX 3090, 24576 MiB, 37 MiB, 24086 MiB, 0 %, 34 C, 20.93 W
```

The process listing contained no `gpu_burn`, SGLang, benchmark, or user
training process. This is an instantaneous observation; the agreed external
GPU queue must still be acquired and rechecked immediately before testing.

## Runtime/toolchain readiness

Only `/usr/bin/python3` and `/usr/bin/nvcc` were found as active system
commands. System Python cannot import the intended runtime packages:

```text
torch None
sglang None
transformers None
safetensors None
flashinfer None
torch error ModuleNotFoundError("No module named 'torch'")
```

The available system compiler is CUDA 12.0.140:

```text
Cuda compilation tools, release 12.0, V12.0.140
```

No local `/data`, `/opt/cuda-conda`, `/data/sglang-qwen35-env`, or local
Python/venv executable matching the remote deployment was present. Repository
source exists at `python/sglang`, but it is not an installed runnable SGLang
environment by itself.

## Model and SM86 artifacts

No local GGUF/IQ3_S file was found under the workstation filesystem search,
including `/home/dev-codex/workspaces` and `/mnt/data`; the supplied
`/mnt/data/nerun-dev/IQ3_S_code_review_and_plan.zip` is source-review material,
not model weights. No local `common_ops*.so`, `*.abi3.so`, or other matching
SGLang SM86 binary artifact was found.

The current repository HEAD is `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`
(`build: add sm86 AOT target for IQ3 validation`), with the pre-existing dirty
worktree preserved. The local source contains the SM86 CMake change, but no
resulting compiled shared object is present locally.

## Readiness conclusion

The RTX3090 hardware is present and currently free, but local deployment is
**not ready**. Missing prerequisites are the approved IQ3_S GGUF, intended
PyTorch/SGLang environment, and a usable matching runtime/kernel artifact.
CUDA 12.0 `nvcc` is present, but it does not establish that the intended
environment or full AOT build is available.

## Evidence / command scope

Evidence was collected with targeted `nvidia-smi`, `ps`, `command -v`, `nvcc
--version`, Python `importlib.util.find_spec`, `findmnt`, `df`, targeted model
search, and repository `git status/log`. Prior local prerequisite evidence is
in `G3-IQ3-LOCAL-PREREQ-SCAN-20260909.md`; deployment paths documented in
`3090-dev/qwen3-27b-iq3s-b2-checkpoint.md` are remote-host facts and were not
assumed to exist locally.

## Followups / open issues

Provisioning or mounting the approved model and matching environment remains
unspecified. Before any test, establish the shared GPU queue/lock and repeat
the GPU/process check. No implementation or deployment action is included in
this scan; extra work requires a fresh linked Task ID.
