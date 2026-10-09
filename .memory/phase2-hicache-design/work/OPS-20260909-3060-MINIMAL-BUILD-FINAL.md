# OPS-20260909-3060-MINIMAL-BUILD-FINAL

status: blocked
task: D3060-OPS-069
epoch: 2026-09-09

## Summary

The exact reviewed commit was transferred and installed on the RTX3060 host. Configure
was attempted with the prescribed minimal-SM86 settings but failed before generation:
the host default CMake is 3.22.1, while this source requires CMake >=3.26. No build,
unit test, import/loadability test, or artifact was run or produced.

## Scope and changed resources

- Local source archive: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (read-only inspection; commit `a76cce39723654cb93ee186b9c3fb570961d7794`).
- Remote target: `/root/sglang-3060-12g-hicache`.
- Previous remote source preserved at:
  `/hy-tmp/d3060-source-backup-20260909-002742`.
- Transferred archive:
  `/hy-tmp/d3060-a76cce39723654cb93ee186b9c3fb570961d7794.tar.gz`.
- Configure output: `/hy-tmp/d3060-aot-configure.log`.
- Configure build directory created: `/hy-tmp/d3060-aot-build` (incomplete).
- No 3090 branch, local product file, `/hy-model`, or running build process was touched.

## Evidence

Archive SHA-256, observed identically locally and remotely:

`a71a3bebd0c2577141a013a6a76b6a3eda1fd740c4283c9a78b89a8a502d3f9e`

Remote source marker:

`a76cce39723654cb93ee186b9c3fb570961d7794`

Remote baseline before configure: Torch `2.5.1+cu124`; CUDA `12.4`; device capability
`(8, 6)`; memory `125Gi total, 41Gi free, 115Gi available`; `/hy-tmp` disk `50G
total, 7.9G used, 43G available`.

Configure command:

```text
cmake -S /root/sglang-3060-12g-hicache/python/sglang/kernels/aot \
  -B /hy-tmp/d3060-aot-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=<remote Torch cmake prefix> \
  -DCMAKE_CUDA_ARCHITECTURES=86 -DCUDAToolkit_ROOT=/usr/local/cuda-12.4 \
  -DSGL_KERNEL_MINIMAL_SM86=ON -DSGL_KERNEL_COMPILE_THREADS=1 \
  -DFETCHCONTENT_SOURCE_DIR_REPO_CUTLASS=/hy-tmp/d3060-aot-deps/repo-cutlass \
  -DFETCHCONTENT_SOURCE_DIR_REPO_FMT=/hy-tmp/d3060-aot-deps/repo-fmt \
  -DFETCHCONTENT_SOURCE_DIR_REPO_TRITON=/hy-tmp/d3060-aot-deps/repo-triton \
  -DFETCHCONTENT_SOURCE_DIR_REPO_FLASHINFER=/hy-tmp/d3060-aot-deps/repo-flashinfer \
  -DFETCHCONTENT_SOURCE_DIR_REPO_FLASH_ATTENTION=/hy-tmp/d3060-aot-deps/repo-flash-attention \
  -DFETCHCONTENT_SOURCE_DIR_REPO_FLASHMLA=/hy-tmp/d3060-aot-deps/repo-flashmla
```

Exact configure failure:

```text
CMake Error at CMakeLists.txt:1 (cmake_minimum_required):
  CMake 3.26 or higher is required.  You are running version 3.22.1
-- Configuring incomplete, errors occurred!
CONFIGURE_RC=1
```

Post-state: no `cmake`, `ninja`, or `nvcc` process; memory `125Gi total, 40Gi free,
115Gi available`; `/hy-tmp` disk `50G total, 8.0G used, 43G available`. No artifact
path/size/hash exists because configure did not complete.

## Followups

Provide an authorized execution method/environment with CMake >=3.26, then issue a
fresh Task ID to rerun configure/build and the required import/loadability check.

## Open issues

- CMake prerequisite is unresolved; selecting or installing an alternate CMake was not
  authorized by the exact procedure.
- Build success/failure beyond configure, artifact state, and runtime loadability remain
  unverified.
