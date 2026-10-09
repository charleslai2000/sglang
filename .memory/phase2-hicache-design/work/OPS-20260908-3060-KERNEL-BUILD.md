# OPS-20260908-3060-KERNEL-BUILD

## Invocation

- Task ID: `D3060-KERNEL-BUILD-006`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Target: `root@i-1.gpushare.com:27460`, RTX3060 only
- Status: **blocked**
- Entry: `ACCEPT`

## Authorized procedure and safety

The requested procedure was to install missing dependencies into
`/root/miniconda3/envs/sglang-3060-4b` and run the source-defined AOT build from
`/root/sglang-3060-12g-hicache/python/sglang/kernels/aot`, targeting SM86. No
weights, server, benchmark, 3090 changes, or destructive cleanup were performed.
The SSH password was supplied out-of-band and was not printed in this report.

## Commands and observed outputs

Remote inspection command (password omitted):

```text
ssh -o StrictHostKeyChecking=no -p 27460 root@i-1.gpushare.com
df -h / /root
nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader
/usr/local/cuda-12.4/bin/nvcc --version
find .../python/sglang/kernels/aot -maxdepth 2 -type f -print
sed -n '1,240p' README.md pyproject.toml Makefile CMakeLists.txt
/root/miniconda3/envs/sglang-3060-4b/bin/python -c '...'
```

Observed:

```text
Filesystem: overlay 30G total, 624M used, 30G available, 3% use
GPU: NVIDIA GeForce RTX 3060, compute capability 8.6, 12288 MiB
CUDA: release 12.4, V12.4.131
```

The prescribed source build command is defined by the Makefile as:

```bash
make build
```

Its effective build sequence is `pip install scikit-build-core isort black`,
`git submodule update --init --recursive`, then:

```bash
CMAKE_POLICY_VERSION_MINIMUM=3.5 MAX_JOBS=$(nproc) \
CMAKE_BUILD_PARALLEL_LEVEL=$(nproc) CMAKE_ARGS="" \
uv build --wheel -Cbuild-dir=build . --verbose --color=always --no-build-isolation
pip3 install dist/*whl --force-reinstall --no-deps
```

The environment executable required by the authorized target does not exist:

```text
/root/miniconda3/envs/sglang-3060-4b/bin/python: No such file or directory
```

Directory inspection showed `/root/miniconda3/envs/sglang-3060-4b` exists, but
`bin/` contains only `killall_sglang` and `sglang`; there is no `python`, `pip`,
or Python standard-library `lib/python*` tree. The directory contains package
files/metadata, including `sglang-0.5.19.dist-info`, but is not an executable
Python environment.

## SM86 coverage

The inspected `CMakeLists.txt` does not add SM86 to the common AOT extension.
With `ENABLE_BELOW_SM90=ON`, common flags include SM80 and SM89, plus SM90; it
does not include SM86. The optional FA3 target does include:

```text
-gencode=arch=compute_86,code=sm_86
```

but only when `SGL_KERNEL_ENABLE_FA3=ON`, and CUDA 12.4 enables FA3 by default
on non-aarch64 hosts. Thus SM86 would be present only in the optional FA3
extension, not the common `sgl_kernel` AOT extension. No build was run to
produce an artifact or confirm generated binaries.

## Artifacts and verification

- Wheel/artifact path: none produced.
- Wheel/artifact size: not applicable.
- Torch version/CUDA/GPU capability from the requested environment: unavailable
  because its Python executable is absent.
- `sgl_kernel` import: not attempted; no executable interpreter exists.
- Marlin-related SGLang imports: not attempted; no executable interpreter exists.
- Build log: no build started.
- Changed remote resources: none observed or intentionally changed.

## Blocker and required reroute

`NEEDS_REASONING`: the exact target environment is malformed. Recreating or
repairing it (for example by installing a Python/conda base and torch) is a
separate environment-provisioning decision not specified by the authorized
build method. A fresh Task ID with explicit authorization is required before
that action, or an existing executable environment path must be supplied.

## Followups

- Fresh Task ID: authorize a defined method to provision/repair
  `/root/miniconda3/envs/sglang-3060-4b`, then rerun the source-defined build.
- After provisioning, verify torch 2.13.0 compatibility required by the
  source `README.md`/`pyproject.toml`, build artifact size/path, imports, and
  actual SM86 sections in produced binaries.

## Open issues

- No wheel exists because the authorized environment cannot execute the build.
- The common AOT build is SM80/SM89/SM90-oriented; only optional FA3 explicitly
  lists SM86 in the inspected source.
