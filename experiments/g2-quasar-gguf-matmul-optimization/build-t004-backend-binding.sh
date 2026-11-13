#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
SRC=/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/ggml-pinned-source
BUILD=/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/pinned-backend-build
export CUDA_HOME=/usr/local/cuda-12.9 TORCH_CUDA_ARCH_LIST=8.6
source /home/ubuntu/venvs/sglang-3090/bin/activate
python - <<'PY'
import os
from pathlib import Path
from torch.utils.cpp_extension import load
root=Path('/home/ubuntu/workspaces/3rdparty/sglang-hicache')
src=Path('/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/ggml-pinned-source')
build=Path('/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/pinned-backend-build')
Path('/data/sglang-hicache/g2-quasar-runs/t004-backend-binding-build').mkdir(parents=True,exist_ok=True)
load(name='t004_llama_backend',sources=[str(root/'experiments/g2-quasar-gguf-matmul-optimization/t004_backend_binding.cpp')],extra_include_paths=[str(src/'include')],extra_cflags=['-O3','-std=c++17','-DGGML_BACKEND_SHARED'],extra_ldflags=[f'-L{build}/src',f'-Wl,-rpath,{build}/src',f'-L{build}/src/ggml-cuda',f'-Wl,-rpath,{build}/src/ggml-cuda','-lggml-cuda','-lggml-cpu','-lggml','-lggml-base','-L/usr/local/cuda-12.9/lib64','-lcudart'],with_cuda=True,build_directory='/data/sglang-hicache/g2-quasar-runs/t004-backend-binding-build',verbose=True)
PY
