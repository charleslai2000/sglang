#!/usr/bin/env python3
"""Single-layer Q4_0 A8-vs-FP32 GEMM diagnostic on frozen doc24 captures."""

import json
from pathlib import Path
import numpy as np
import torch
import gguf
import sgl_kernel
from sglang.srt.layers.quantization.gguf import fused_mul_mat_gguf

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
GG = "/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf"
A = "a149298aed9d489597b8ffb6ca34ca61"
B = "f1fcb176bfef46539bc32f5bdec4446f"
POS = 1103
R = gguf.GGUFReader(GG)
T = {t.name: t for t in R.tensors}


def cap(uid, stage, prefix="l5-ops"):
    return (
        torch.load(
            D / f"{prefix}.{uid}.layer5.pos{POS}.{stage}.pt",
            map_location="cpu",
            weights_only=False,
        )["value"]
        .float()
        .cuda()
    )


def raw(name):
    return torch.from_numpy(np.asarray(T[name].data).copy()).cuda()


def metrics(a, b):
    a = a.float().flatten()
    b = b.float().flatten()
    d = a - b
    return {
        "rel_l2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "rmse": float(d.square().mean().sqrt()),
        "max_abs": float(d.abs().max()),
        "cos": float(torch.nn.functional.cosine_similarity(a, b, dim=0)),
        "bf16_equal": bool(torch.equal(a.to(torch.bfloat16), b.to(torch.bfloat16))),
    }


res = {}
# Exact same input per projection captured from production A8 forward.
for stage, name, n in [
    ("q_proj", "blk.5.attn_q.weight", 4096),
    ("k_proj", "blk.5.attn_k.weight", 1024),
    ("v_proj", "blk.5.attn_v.weight", 1024),
]:
    if stage == "q_proj":
        x = cap(A, "attn_normed_input").to(torch.bfloat16)
    w = raw(name)
    a = sgl_kernel.ggml_mul_mat_vec_a8(w, x, 2, n)
    b = fused_mul_mat_gguf(x, w, 2, force_fp32_dequant_gemm=True)
    live = cap(A, stage)
    res[stage] = {
        "A8_vs_FP32": metrics(a, b),
        "A8_vs_live": metrics(a, live),
        "FP32_vs_live": metrics(b, live),
        "output_dtype": str(b.dtype),
        "same_input_sha256": __import__("hashlib")
        .sha256(x.cpu().view(torch.uint16).numpy().tobytes())
        .hexdigest(),
    }
# Expert FFN gate/up/down are packed in fused-MoE orientation and require the
# expert A8/GEMM APIs plus exact routing; ordinary GEMV is not a valid oracle.
# Keep them explicitly out of this direct projection matrix.
(D / "layer5-same-input-a8-vs-fp32-doc24.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
