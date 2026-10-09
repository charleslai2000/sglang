# OPS-20260908-3060-12G-ENV-KERNEL-PREREQS

ENTRY: ACCEPT

- Task ID: `D3060-ENV-KERNEL-005`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Invocation status: `blocked`
- Target: `root@i-1.gpushare.com:27460` (RTX 3060 only)
- Source: `/root/sglang-3060-12g-hicache`
- Requested source identity: `d49214e59228a555dc9f878426928a8a628d8848`
- Target runtime prefix: `/root/miniconda3/envs/sglang-3060-4b`

## Summary

The authorized Python prerequisite was completed: `msgspec 0.21.1` was installed with `--no-deps` into the dedicated target prefix. A compatible CUDA compiler was already installed on the host; no apt installation or driver change was needed. `nvcc` is available at `/usr/local/cuda-12.4/bin/nvcc` and reports CUDA 12.4.131.

The requested kernel/backend acceptance remains blocked. The target has no importable `sgl_kernel`, and the source tree has no standalone `sgl-kernel` build/install method. Its Python package contains SGLang JIT/AOT kernel sources and Marlin sources, but invoking the Marlin Python import is blocked by the absent target dependency `transformers`. Installing the full dependency set or inventing an alternate kernel build was outside this Task ID.

## Exact commands and outputs

SSH used `sshpass -e` with the supplied password via `SSHPASS`; the secret was not printed or persisted. Remote commands were bounded to the target host and prefix.

Initial inspection:

```text
sed -n '1,80p' /root/sglang-3060-12g-hicache/SETUP_ONLY.md
git -C /root/sglang-3060-12g-hicache rev-parse HEAD
```

Observed:

```text
Qwen3.5-4B/SGLang RTX3060 bootstrap setup directory.
No model or source checkout installed by bootstrap task.
fatal: not a git repository (or any of the parent directories): .git
```

The requested commit could not be independently verified because the supplied source is not a Git checkout. The marker was preserved unchanged.

Before/after target package action:

```text
BEFORE: importlib.util.find_spec("msgspec") -> None
ACTION: /usr/local/bin/python -m pip install --no-deps --target /root/miniconda3/envs/sglang-3060-4b msgspec
RESULT: Successfully installed msgspec-0.21.1
AFTER: msgspec 0.21.1 /root/miniconda3/envs/sglang-3060-4b/msgspec/__init__.py
```

Runtime/toolchain evidence after the action:

```text
Python 3.11.11
pip 24.2
torch 2.5.1+cu124
torch.version.cuda 12.4
msgspec 0.21.1
nvcc path: /usr/local/cuda-12.4/bin/nvcc
Cuda compilation tools, release 12.4, V12.4.131
cuda-compiler-12-4 12.4.1-1
cuda-toolkit-12-4-config-common 12.4.127-1
cuda-toolkit-12-config-common 12.4.127-1
cuda-toolkit-config-common 12.4.127-1
NVIDIA driver 550.144.03
GPU NVIDIA GeForce RTX 3060, compute capability 8.6
```

Kernel/backend probes:

```text
sgl_kernel: None (not importable)
sglang: 0.5.19 (importable)
transformers: None (not installed)
Marlin import attempt: failed before module load with ModuleNotFoundError: No module named 'transformers'
```

Source inspection found `/root/sglang-3060-12g-hicache/python/setup.py`, `python/pyproject.toml`, SGLang JIT/AOT kernel sources, and Marlin source files under `python/sglang/kernels/jit/csrc/gemm/marlin/`. No standalone `sgl-kernel` setup/build script was present in the source tree.

Disk and safety verification:

```text
target before: 182M
target after: 183M
source: 127M
running sglang/server/benchmark processes: none
SETUP_ONLY.md sha256: c32970f9974472736d84d464acc8fe06912e80b5f74735ce6d82ff0fd6d490dc
```

## Changed resources

- Added only the `msgspec 0.21.1` package files under `/root/miniconda3/envs/sglang-3060-4b`.
- No apt package was installed; existing `cuda-compiler-12-4` was not changed.
- No NVIDIA driver change.
- No source files or setup marker changed.

## Scope and rollback

No model or weights were downloaded, no server or benchmark was started, no 3090 was touched, and no destructive cleanup was performed. The bounded rollback for the completed package action is removal of the newly added `msgspec` package files only, but rollback was not requested and was not performed.

## Artifacts

- This report only: `OPS-20260908-3060-12G-ENV-KERNEL-PREREQS.md`

## Followups

Fresh Task ID required to install additional target Python dependencies or to define/authorize a concrete source build procedure for the repository's JIT/AOT Marlin path.

## Open issues

- `sgl_kernel` remains unavailable.
- SM86 Marlin build/load result remains unverified because no repository-defined standalone build method was found and the Python import is blocked by missing `transformers`.
- Source commit identity remains supplied-but-unverified because the source is not a Git checkout.
