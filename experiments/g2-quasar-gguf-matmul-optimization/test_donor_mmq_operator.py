#!/usr/bin/env python3
"""Build and run the opt-in pinned donor Q4_0 M=32 operator against independent references."""

import hashlib, importlib.util, json, os
from pathlib import Path
import numpy as np
import torch
import gguf
from torch.utils.cpp_extension import load

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "python/sglang/kernels/aot/csrc/quantization/gguf/llama_mmq_q4_0.cu"
BUILD = Path("/data/sglang-hicache/g2-quasar-runs/t004-donor-extension")
AOT = Path(
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.abi3.so"
)
RUN = Path(
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1/weights"
)
NUM = Path("/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-numeric-r1")

BIND = """#include <torch/extension.h>\ntorch::Tensor gguf_q4_0_llama_mmq_m32(torch::Tensor,torch::Tensor);\nPYBIND11_MODULE(TORCH_EXTENSION_NAME,m){m.def("run",&gguf_q4_0_llama_mmq_m32);}\n"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def metrics(a, b):
    d = a.float() - b.float()
    return {
        "max_abs": d.abs().max().item(),
        "rel_l2": (
            torch.linalg.vector_norm(d)
            / torch.linalg.vector_norm(b.float()).clamp_min(1e-30)
        ).item(),
    }


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    ext = load(
        name="t004_donor_mmq",
        sources=[str(SRC), str(ROOT / "experiments/g2-quasar-gguf-matmul-optimization/donor_mmq_binding.cpp")],
        extra_include_paths=[str(SRC.parent)],
        extra_cuda_cflags=[
            "-O3",
            "-std=c++17",
            "-gencode=arch=compute_86,code=sm_86",
            "-D_GLIBCXX_USE_CXX11_ABI=1",
            "-U__CUDA_NO_HALF_OPERATORS__",
            "-U__CUDA_NO_HALF_CONVERSIONS__",
            "-U__CUDA_NO_HALF2_OPERATORS__",
            "-U__CUDA_NO_BFLOAT16_CONVERSIONS__",
            "-U__CUDA_NO_BFLOAT16_OPERATORS__",
        ],
        extra_cflags=["-O3", "-std=c++17", "-D_GLIBCXX_USE_CXX11_ABI=1"],
        with_cuda=True,
        build_directory=str(BUILD),
        verbose=True,
    )
    torch.ops.load_library(str(AOT))
    r = gguf.GGUFReader(
        "/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf"
    )
    saved = json.load(open(NUM / "results.json"))["results"]
    by = {x["tensor"]: x for x in saved}
    out = []
    for name, key in [
        ("blk.0.ffn_gate.weight", "blk_0_ffn_gate_weight"),
        ("blk.0.attn_output.weight", "blk_0_attn_output_weight"),
    ]:
        t = next(t for t in r.tensors if t.name == name)
        K, N = map(int, t.shape)
        raw = t.data.tobytes()
        prior = by.get(key)
        assert prior and sha(raw) == prior["weight_sha256"], (
            name,
            sha(raw),
            prior and prior["weight_sha256"],
        )
        q = torch.from_numpy(t.data.copy()).cuda().reshape(N, K // 32 * 18)
        input_file = NUM / f"{key}_input_f32.raw"
        if not input_file.exists():
            input_file = RUN / f"{key}_input_f32.raw"
        xf = torch.from_numpy(
            np.fromfile(input_file, dtype=np.float32).reshape(32, K)
        ).cuda()
        assert (
            sha(xf.cpu().contiguous().numpy().tobytes()) == prior["input_fp32_sha256"]
        )
        x = xf.to(torch.bfloat16)
        dec = gguf.quants.dequantize(t.data, gguf.GGMLQuantizationType.Q4_0)
        ref = xf @ torch.from_numpy(dec.copy()).cuda().reshape(N, K).float().T
        aotmod = importlib.util.spec_from_file_location(
            "ggufwrap",
            ROOT / "python/sglang/kernels/aot/python/sgl_kernel/quantization/gguf.py",
        )
        mod = importlib.util.module_from_spec(aotmod)
        aotmod.loader.exec_module(mod)
        aot = mod.ggml_mul_mat_a8(q, x, 2, N).float()
        donor = ext.run(q, x).to(torch.bfloat16).float()
        torch.cuda.synchronize()
        repeats = [ext.run(q, x).to(torch.bfloat16).float() for _ in range(3)]
        torch.cuda.synchronize()
        out.append({"tensor": name, "MKN": [32, N, K], "donor_finite": bool(torch.isfinite(donor).all()), "aot_finite": bool(torch.isfinite(aot).all()), "donor_vs_fp32": metrics(donor, ref) if torch.isfinite(donor).all() else None, "donor_vs_aot": metrics(donor, aot) if torch.isfinite(donor).all() and torch.isfinite(aot).all() else None, "repeat_bitwise_equal": [torch.equal(donor, z) for z in repeats], "donor_first": donor[0,:8].cpu().tolist(), "aot_first": aot[0,:8].cpu().tolist()})
    print(
        json.dumps(
            {"gpu": torch.cuda.get_device_name(), "operator_results": out}, indent=2
        )
    )


if __name__ == "__main__":
    main()
