#!/usr/bin/env python3
"""Small direct same-input comparison of existing GGUF AOT MMQ/MVVQ paths.

No model service or persistent source/build artifacts. Defaults target actual c32
shapes. GPU use requires the project-exclusive lock held by the launcher.
"""

from __future__ import annotations
import argparse, json, statistics
from pathlib import Path
import torch
import gguf

# Load just the wrapper: full sgl_kernel initialization expects build-tree ops,
# while this isolated benchmark uses the explicitly pinned SM86 shared object.
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
GGUF_WRAPPER = ROOT / "python/sglang/kernels/aot/python/sgl_kernel/quantization/gguf.py"
spec = importlib.util.spec_from_file_location("sgl_kernel_gguf_wrapper", GGUF_WRAPPER)
assert spec and spec.loader
sgl_gguf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sgl_gguf)

AOT = Path(
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.abi3.so"
)
MODEL = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")


def tensor_bytes(reader, name):
    t = next(t for t in reader.tensors if t.name == name)
    shape = tuple(map(int, t.shape))
    typ = t.tensor_type
    block, bytes_per_block = gguf.GGML_QUANT_SIZES[typ]
    assert shape[0] % block == 0
    packed_cols = shape[0] // block * bytes_per_block
    # Runtime GGUFLinear stores [logical_N, packed_K_bytes] contiguous rows.
    raw = torch.from_numpy(t.data.copy()).to("cuda").reshape(shape[1], packed_cols)
    return raw, shape, typ


def event_ms(fn, repeats=30, warmup=5):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    vals = []
    for _ in range(repeats):
        a = torch.cuda.Event(enable_timing=True)
        b = torch.cuda.Event(enable_timing=True)
        a.record()
        fn()
        b.record()
        b.synchronize()
        vals.append(a.elapsed_time(b))
    return {
        "median_ms": statistics.median(vals),
        "mean_ms": statistics.mean(vals),
        "min_ms": min(vals),
        "n": repeats,
    }


def parity(a, b):
    x = a.float()
    y = b.float()
    diff = (x - y).abs()
    return {
        "max_abs": diff.max().item(),
        "rel_l2": (
            torch.linalg.vector_norm(x - y)
            / torch.linalg.vector_norm(y).clamp_min(1e-30)
        ).item(),
        "argmax_equal": torch.equal(x.argmax(-1), y.argmax(-1)),
    }


def run_one(reader, name, m, kernels, out):
    q, shape, qtype = tensor_bytes(reader, name)
    logical_k = int(shape[0])
    logical_n = int(shape[1])
    assert qtype in (gguf.GGMLQuantizationType.Q4_0, gguf.GGMLQuantizationType.Q6_K)
    # Reader shape is [K,N]; serialized linear weight is [N,K], so AOT row=N and X K.
    rows = logical_n
    cols = logical_k
    gen = torch.Generator(device="cuda").manual_seed(20261112)
    x = torch.randn((m, cols), device="cuda", dtype=torch.bfloat16, generator=gen)
    typ = int(qtype)
    # Current graph AOT MMQ call includes Q8_1 activation quantization. Dequant reference is
    # conversion+BF16 GEMM and measured separately; it is not claimed equivalent to Marlin.
    base = sgl_gguf.ggml_mul_mat_a8(q, x, typ, rows)
    torch.cuda.synchronize()
    rec = {
        "tensor": name,
        "gguf_type": qtype.name,
        "gguf_shape_KN": [logical_k, logical_n],
        "linear_MKN": [m, rows, cols],
        "bytes": q.numel(),
        "baseline_route": "ggml_mul_mat_a8 (A8 quantize + direct GGUF MMQ)",
        "baseline_timing": event_ms(lambda: sgl_gguf.ggml_mul_mat_a8(q, x, typ, rows)),
        "candidates": [],
    }
    for label, op in kernels:
        if label == "ggml_mul_mat_vec_a8" and m > 6:
            continue
        y = op(q, x, typ, rows)
        torch.cuda.synchronize()
        rec["candidates"].append(
            {
                "route": label,
                "timing_including_A8": event_ms(lambda: op(q, x, typ, rows)),
                "parity_vs_baseline": parity(y, base),
            }
        )
    block_size, type_size = gguf.GGML_QUANT_SIZES[qtype]
    # q is [N,packed_K_bytes], native dequant consumes rows=N, cols=K logical.
    deq = lambda: sgl_gguf.ggml_dequantize(q, typ, rows, cols, torch.bfloat16)
    w = deq()
    torch.cuda.synchronize()
    ref = x @ w.T
    rec["gguf_dequant_bf16_conversion"] = event_ms(deq)
    rec["dequant_bf16_gemm"] = event_ms(lambda: x @ w.T)
    rec["dequant_path_parity_vs_aot"] = parity(base, ref)
    # A persistent full BF16 matrix may not fit. Treat this as a kernel-only
    # counterfactual; record required resident storage before considering cache.
    rec["bf16_weight_bytes"] = rows * cols * 2
    rec["bf16_weight_mib"] = rows * cols * 2 / (1024**2)
    rec["dequant_reuse_break_even_calls"] = "not_applicable_without_budgeted_persistent_weight_cache"
    out.append(rec)
    del q, x, base, w, ref
    torch.cuda.empty_cache()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    torch.ops.load_library(str(AOT))
    assert torch.cuda.is_available()
    reader = gguf.GGUFReader(str(MODEL))
    out = []
    run_one(
        reader,
        "blk.0.ffn_gate.weight",
        32,
        [("ggml_mul_mat_a8", sgl_gguf.ggml_mul_mat_a8)],
        out,
    )
    run_one(
        reader,
        "blk.0.attn_output.weight",
        32,
        [("ggml_mul_mat_a8", sgl_gguf.ggml_mul_mat_a8)],
        out,
    )
    # Actual VQ-safe boundary: small N and M<=6 at the same K.
    run_one(
        reader,
        "blk.0.attn_output.weight",
        2,
        [
            ("ggml_mul_mat_a8", sgl_gguf.ggml_mul_mat_a8),
            ("ggml_mul_mat_vec_a8", sgl_gguf.ggml_mul_mat_vec_a8),
        ],
        out,
    )
    run_one(
        reader,
        "token_embd.weight",
        32,
        [("ggml_mul_mat_a8", sgl_gguf.ggml_mul_mat_a8)],
        out,
    )
    Path(args.output).write_text(
        json.dumps(
            {
                "torch": torch.__version__,
                "gpu": torch.cuda.get_device_name(),
                "results": out,
            },
            indent=2,
        )
    )
    print(json.dumps({"gpu": torch.cuda.get_device_name(), "results": out}, indent=2))


if __name__ == "__main__":
    main()
