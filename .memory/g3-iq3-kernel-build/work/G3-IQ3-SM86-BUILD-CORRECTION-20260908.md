# G3 IQ3 SM86 build correction — 2026-09-08

Status: done

## Scope

Task ID: `G3-IQ3-SM86-BUILD-CORRECTION-20260908`  
Epoch: E7  
Role: devops

Only the local AOT build configuration was changed. The remote experimental
host was not edited, and the v1 service was not stopped, restarted,
reconfigured, or benchmarked. No GGUF/model weights, Python dispatch, MMQ
code, quantization behavior, or runtime flags were changed.

## Observed baseline

The supplied P0 identity evidence reports RTX 3090 capability `(8, 6)` and an
actual loaded extension with native images for `sm_80`, `sm_89`, `sm_90`,
`sm_100`, and `sm_120`, but no native `sm_86` image.

The local AOT configuration in
`python/sglang/kernels/aot/CMakeLists.txt` already added `sm_80` and `sm_89`
to `SGL_KERNEL_CUDA_FLAGS` under `ENABLE_BELOW_SM90`, but omitted `sm_86`.
That is the minimal build-configuration cause consistent with the P0 result.

## Implemented change

Added one flag in the common AOT architecture list:

```cmake
"-gencode=arch=compute_86,code=sm_86"
```

File changed:

`python/sglang/kernels/aot/CMakeLists.txt` (the `ENABLE_BELOW_SM90`
`SGL_KERNEL_CUDA_FLAGS` block).

This preserves the existing default behavior: x86 builds enable the below-SM90
list, while aarch64 keeps the existing default disabled behavior. No other
tracked file was changed by this task.

## Validation evidence

Raw command output is preserved under:

`.memory/g3-baseline-20260907/work/raw/g3-iq3-sm86-build-correction-20260908/`

- `local-diff-and-check.txt`: exact diff; `git diff --check` passed.
- `static-validation.txt`: confirms the common list contains `sm_80`, `sm_86`,
  and `sm_89`.
- `nvcc-sm86-compile.txt`: CUDA 12.0 `nvcc` compiled a minimal CUDA object
  with `-arch=sm_86` successfully (`stdin_compile_rc=0`).
- `nvcc-sm86-object-arch.txt`: `cuobjdump --list-elf` reports an `sm_86`
  cubin in that object.
- `cmake-configure.txt`: full configure was attempted with
  `FETCHCONTENT_FULLY_DISCONNECTED=ON`, but cannot run because local `cmake`
  is unavailable; local Python also has no `torch` module. This is an
  environment limitation, not a source failure.
- `architecture-flags.txt` and `toolchain.txt`: relevant source block and
  available toolchain facts.
- `SHA256SUMS`: hashes for the raw evidence files.

## Deployment status

The source correction is **build-ready but not deployable yet**: no AOT wheel
was built or installed, and the remote `common_ops.abi3.so` remains unchanged.
Runtime acceptance still requires a CUDA/PyTorch build environment, an isolated
wheel build, `cuobjdump --list-elf` verification of the resulting extension,
and a subsequent runtime/kernel validation task. No performance claim is made.

Invocation status: **done**

Follow-up: perform the isolated AOT build/install and verify the resulting
extension contains native `sm_86`; keep that delivery separate from MMQ and
dispatch changes.

Open issues: full CMake configure/build and remote installation were not
authorized or possible in this invocation; the remote artifact therefore still
has the pre-correction architecture set.
