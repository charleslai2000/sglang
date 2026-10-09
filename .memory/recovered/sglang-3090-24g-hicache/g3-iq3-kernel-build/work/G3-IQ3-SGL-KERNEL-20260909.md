# G3-IQ3-SGL-KERNEL-20260909

Status: blocked

## Entry and scope

ENTRY: ACCEPT. Mechanical local build/install was authorized for checkout commit
`5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`, targeting
`/mnt/data/qwen3-g3-baseline/venv`, with no service, benchmark, or GPU test.

## Confirmed procedure and blocker

The checkout-matched procedure is `python/sglang/kernels/aot/Makefile` target
`build` (`uv build --wheel ... --no-build-isolation`, then pip install), and its
README explicitly requires CMake >=3.31, Python >=3.10, scikit-build-core, and
optional Ninja. The package is `sglang-kernel` and its import path is
`sgl_kernel`. The target venv has Python 3.12.3, torch 2.13.0+cu130, Ninja
1.13.2, and the editable checkout `sglang 0.5.20.dev16+g5c5f5e3b2`.

The prescribed build cannot start: no system `cmake` is installed, `uv` is
1.11.1 but no CMake executable is available, and the supplied wheelhouse has
no CMake wheel. An attempted offline provisioning command failed exactly with:

```text
ERROR: Could not find a version that satisfies the requirement cmake>=3.31 (from versions: none)
ERROR: No matching distribution found for cmake>=3.31
```

Therefore no source, venv package, model, process, or GPU state was changed by
this invocation. `import sgl_kernel` remains:

```text
ModuleNotFoundError: No module named 'sgl_kernel'
```

The RTX3090 lock was checked non-destructively and was available. CUDA compiler
is `/usr/local/cuda` nvcc 12.0.140, while torch reports CUDA 13.0; no GPU test
was run. Native SM86 evidence is consequently unavailable.

## Artifacts and evidence

- Raw evidence: `work/raw/g3-iq3-sgl-kernel-20260909/evidence.log`
- Evidence SHA256: `d23e6684db2da5b6bd6901e985f1fbc8c38f2a1e9bd8ba1f3241a46b26269fc3`
- Package/build instructions: `python/sglang/kernels/aot/README.md`, `Makefile`, `pyproject.toml`
- Target commit: `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`

## Followups

Root-only action required: provision an approved CMake >=3.31 executable (or
matching wheel) into the authorized build environment, then dispatch a fresh
devops-executor invocation to run the unchanged Makefile build/install and
collect package path, shared-object SHA256, and SM86 ELF evidence.

## Open issues

- CMake >=3.31 is unavailable in the supplied environment/wheelhouse.
- `sgl_kernel` is not installed; acceptance criterion is unmet.
- CUDA toolkit/compiler (12.0) and torch CUDA runtime (13.0) mismatch should be
  recorded during the subsequent authorized build; this invocation does not
  select or alter a toolchain.
