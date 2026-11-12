#!/usr/bin/env python3
"""Short Nsight capture of llama.cpp Q4_0 M32 MMQ runtime kernels."""

import os
from pathlib import Path
import subprocess

build = Path("/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112")
out = Path(
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1"
)
weight = out / "weights/blk_0_attn_output_weight.raw"
inp = out / "weights/blk_0_attn_output_weight_input_f32.raw"
cmd = [
    str(build / "harness/llama_mmq_harness"),
    str(weight),
    "2560",
    "2048",
    "32",
    str(inp),
]
env = os.environ.copy()
env["LD_LIBRARY_PATH"] = f"{build}/bin:/usr/local/cuda-12.9/lib64:" + env.get(
    "LD_LIBRARY_PATH", ""
)
with open("/tmp/f1-r16b-gpu-exclusive.lock", "r") as lock:
    import fcntl

    fcntl.flock(lock, fcntl.LOCK_EX)
    subprocess.run(
        [
            "/usr/local/cuda-12.9/bin/nsys",
            "profile",
            "--force-overwrite=true",
            "--trace=cuda,nvtx",
            "-o",
            str(out / "llama-mmq-kernel-r1"),
            *cmd,
        ],
        env=env,
        check=True,
    )
    subprocess.run(
        [
            "/usr/local/cuda-12.9/bin/nsys",
            "export",
            "--type",
            "sqlite",
            "-o",
            str(out / "llama-mmq-kernel-r1.sqlite"),
            str(out / "llama-mmq-kernel-r1.nsys-rep"),
        ],
        check=True,
    )
