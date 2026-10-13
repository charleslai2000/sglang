"""Build the optional CUDA 12.9 CUPTI range extension in-place.

The service must run with NVIDIA profiling permissions (typically sudo on
GA10x). This module is never imported unless T002 profiling is enabled.
"""
from __future__ import annotations

import os
from pathlib import Path

from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

HERE = Path(__file__).resolve().parent
CUDA_HOME = Path(os.environ.get("CUDA_HOME", "/usr/local/cuda-12.9"))
CUPTI_INCLUDE = CUDA_HOME / "targets/x86_64-linux/include"
CUPTI_LIB = CUDA_HOME / "targets/x86_64-linux/lib"

setup(
    name="sglang-t002-cupti-range",
    ext_modules=[
        CUDAExtension(
            name="sglang.srt.utils.cupti_range._cupti_range",
            sources=[
                str(HERE / "cupti_range.cpp"),
                str(HERE / "Metric.cpp"),
                str(HERE / "List.cpp"),
                str(HERE / "Eval.cpp"),
            ],
            include_dirs=[
                str(HERE),
                str(CUPTI_INCLUDE),
                str(CUDA_HOME / "extras/CUPTI/samples/extensions/include/profilerhost_util"),
                str(CUDA_HOME / "extras/CUPTI/samples/extensions/include/c_util"),
            ],
            library_dirs=[str(CUPTI_LIB)],
            libraries=["cupti", "nvperf_host", "nvperf_target", "cuda"],
            extra_compile_args={
                "cxx": ["-O2", "-std=c++17"],
                "nvcc": ["-O2", "-std=c++17", "-gencode=arch=compute_86,code=sm_86"],
            },
            runtime_library_dirs=[str(CUPTI_LIB)],
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
