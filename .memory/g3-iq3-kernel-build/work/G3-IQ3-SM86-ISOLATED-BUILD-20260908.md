# G3-IQ3-SM86-ISOLATED-BUILD-20260908

## Status

pending (build remains running on the authorized experimental host; no live extension was installed and v1 PID 503601/8035 was untouched).

## Scope and commands

Staged source and outputs are under `/data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/`. The staged CMake source contains the requested `compute_86,code=sm_86` flag under `ENABLE_BELOW_SM90`; the deployed source was not edited. Initial documented wheel command was attempted exactly with the deployed interpreter, but stopped immediately because `uv` is absent. No download or installation was attempted.

The supported host CMake fallback was then used:

```text
PATH=/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin:$PATH /data/sglang-qwen35-env/bin/cmake -S <staged>/src -B <staged>/cmake-build -G Ninja -DENABLE_BELOW_SM90=ON -DSGL_KERNEL_COMPILE_THREADS=1 -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/data/sglang-qwen35-env/lib/python3.12/site-packages/torch -DPython_EXECUTABLE=/data/sglang-qwen35-env/bin/python -DCMAKE_CUDA_ARCHITECTURES=86
/data/sglang-qwen35-env/bin/cmake --build <staged>/cmake-build --parallel 2
```

Configure succeeded and reported `Added CUDA NVCC flags for: -gencode;arch=compute_86,code=sm_86`. Build is currently at `[2/506]`, compiling the AOT common target; no resulting `.so` or `cuobjdump` result exists yet.

## Environment evidence

- GPU capability: `(8, 6)`.
- PyTorch: `2.13.0+cu130`; reported CUDA `13.0`.
- nvcc: CUDA `12.8` compiler, `/opt/cuda-conda/bin/nvcc`.
- CMake: `4.4.3`.
- No service restart, benchmark, product edit, audit hook, or live extension replacement.

## Artifacts

Remote: `/data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/`

Local raw logs: [raw build logs](./raw/g3-iq3-sm86-isolated-build-20260908/)

SHA-256: `build.log` 70815e87487ab1572f62a2ad2024c3cfddf09ea48f110ccca0d3f17b441d19e5; `cmake-build-2.log` cdd6bdd34aa063edb536f017e4ee40a3fe442b7d99278c28471a9244833b71da; `cmake-configure-2.log` 389d03027107486f2486c51d30c40374973e878a56066126c418ae0bf36e9764; `preflight.log` 3c4de15e53f58e77da0f51049bc219a9f1f4a87e94f099cc327901d97d609b93.

## Open issue

The build is large (506 Ninja steps) and has not completed within this invocation. Native `sm_86` production is therefore not yet confirmed; `cuobjdump --list-elf` is pending completion.
