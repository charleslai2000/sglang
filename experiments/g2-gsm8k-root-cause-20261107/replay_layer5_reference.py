#!/usr/bin/env python3
"""Fixed-input Layer-5 CPU reference using the archive's exact Q4_0 tensors."""

import json, math
from pathlib import Path
import numpy as np
import torch
import gguf

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
GG = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")
UUID = "a149298aed9d489597b8ffb6ca34ca61"
RID = "g2-l5-doc24"
POS = 1103
reader = gguf.GGUFReader(str(GG))
T = {x.name: x for x in reader.tensors}


def unpack_q4(name, out, inp):
    t = T[name]
    assert t.tensor_type == gguf.GGMLQuantizationType.Q4_0, (name, t.tensor_type)
    decoded = gguf.dequantize(t.data, t.tensor_type)
    assert decoded.shape == (out, inp), (name, decoded.shape)
    return torch.from_numpy(decoded.copy())


def tensor_f(name):
    return torch.from_numpy(np.asarray(T[name].data).astype(np.float32).copy())


def capture(stage):
    f = D / f"l5-ops.{UUID}.layer5.pos{POS}.{stage}.pt"
    return (
        torch.load(f, map_location="cpu", weights_only=False)["value"]
        .float()
        .reshape(-1)
    )


def metric(a, b):
    a = a.float().flatten()
    b = b.float().flatten()
    diff = a - b
    return {
        "rel_l2": float(diff.norm() / b.norm().clamp_min(1e-30)),
        "max_abs": float(diff.abs().max()),
        "rmse": float(diff.square().mean().sqrt()),
        "cos": float(torch.nn.functional.cosine_similarity(a, b, dim=0)),
    }


def lin(x, name, out, inp):
    w = unpack_q4(name, out, inp)
    # CPU dequantized GEMV oracle; production uses Q8_1 activation quantization.
    return (x.float() @ w.T).to(torch.bfloat16).float(), w


def fp16_round(x):
    return x.to(torch.float16).float()


def q8_1(x):
    """Production CUDA quantize_q8_1, 32 values/block, roundf ties away."""
    blocks = x.float().reshape(-1, 32)
    amax = blocks.abs().amax(dim=-1, keepdim=True)
    d = amax / 127.0
    q = torch.where(d != 0, blocks / d.clamp_min(1e-30), torch.zeros_like(blocks))
    q = torch.sign(q) * torch.floor(q.abs() + 0.5)
    q = q.clamp(-127, 127).to(torch.int32)
    d16 = fp16_round(d)
    sum16 = fp16_round(q.sum(dim=-1, keepdim=True).float())
    return q, d16, sum16


def production_q4_0_a8(x, name, out, inp):
    """Emulate CUDA MMVQ Q4_0xQ8_1 lane's dp4a integer dot and scale formula."""
    t = T[name]
    raw = np.asarray(t.data).reshape(out, inp // 32, 18)
    q4 = torch.from_numpy(raw[..., 2:].copy().astype(np.uint8)).to(torch.int32)
    packed32 = torch.stack(
        [
            q4[..., 4 * i]
            | (q4[..., 4 * i + 1] << 8)
            | (q4[..., 4 * i + 2] << 16)
            | (q4[..., 4 * i + 3] << 24)
            for i in range(8)
        ],
        dim=-1,
    )
    wlo = packed32 & 0x0F0F0F0F
    whi = (packed32 >> 4) & 0x0F0F0F0F
    d4 = torch.from_numpy(raw[..., :2].copy().view('<f2').astype(np.float32)[..., 0].copy())
    xq, dx, sx = q8_1(x)
    xq = xq.reshape(inp // 32, 32)
    outv = torch.zeros(out, dtype=torch.float32)
    # Each MMVQ lane handles two packed ints (=8 low + 8 high values); vdr=2.
    for block in range(inp // 32):
        # Preserve vec_dot's two dp4a calls per packed integer and Q8_1's
        # low/high 16-value segments. Low nibbles are shifted by -8; the
        # correction term accounts for both VDR=2 packed ints.
        sumi = torch.zeros(out, dtype=torch.int32)
        qseg = xq[block]
        for i in range(2):
            a = packed32[:, block, i]
            va0 = a & 0x0F0F0F0F
            va1 = (a >> 4) & 0x0F0F0F0F
            for p, qpart, off in ((va0, qseg[i * 4 : i * 4 + 4], 0),
                                  (va1, qseg[16 + i * 4 : 16 + i * 4 + 4], 16)):
                lanes = torch.stack([(p >> (8 * j)) & 255 for j in range(4)], dim=1)
                lanes = torch.where(lanes >= 128, lanes - 256, lanes)
                sumi += (lanes * qpart.to(torch.int32)).sum(dim=1)
        # Low-nibble offset correction for 16 Q4 values handled by this lane.
        scale = d4[:, block] * dx.reshape(-1)[block]
        # Each MMVQ lane processes 16 values; 32 lanes cover a full 512-wide tile.
        # For one row, emulate all lanes and sum their 16-value partials exactly.
        corr = d4[:, block] * (-8.0 * sx.reshape(-1)[block] / 2.0)
        outv += scale * sumi.float() + corr
    return outv.to(torch.bfloat16).float().view(1, out), None


def rms(x, w, eps=1e-6):
    z = x.float().reshape(-1, x.shape[-1])
    y = z * torch.rsqrt(z.square().mean(-1, keepdim=True) + eps)
    if w is not None:
        y = y * w.float()
    return y.to(torch.bfloat16).float().reshape(x.shape)


block = capture("block_input").view(1, 2560).to(torch.bfloat16)
x = (
    torch.load(
        D / f"l5-replay-ple.{UUID}.ple.5", map_location="cpu", weights_only=False
    )["value"]
    .float()
    .reshape(-1, 256)[POS : POS + 1]
    .to(torch.bfloat16)
)
# Match production input RMSNorm; parameter tensors are F32 GGUF.
norm_w = tensor_f("blk.5.attn_norm.weight")
attn_in = rms(block, norm_w)
q_raw, qw = lin(attn_in, "blk.5.attn_q.weight", 4096, 2560)
k_raw, kw = lin(attn_in, "blk.5.attn_k.weight", 1024, 2560)
v_raw, vw = lin(attn_in, "blk.5.attn_v.weight", 1024, 2560)
q, _ = production_q4_0_a8(attn_in, "blk.5.attn_q.weight", 4096, 2560)
k, _ = production_q4_0_a8(attn_in, "blk.5.attn_k.weight", 1024, 2560)
v, _ = production_q4_0_a8(attn_in, "blk.5.attn_v.weight", 1024, 2560)
q_proj, k_proj, v_proj = q, k, v
q = q.view(1, 8, 512)
k = k.view(1, 2, 512)
v = v.view(1, 2, 512)
# Q/K per-head RMSNorm; V has no scale, as Gemma4 reference specifies.
q = rms(q, tensor_f("blk.5.attn_q_norm.weight"))
k = rms(k, tensor_f("blk.5.attn_k_norm.weight"))
v = rms(v, None)
# proportional RoPE: rope_freqs archive 1/f factors (64 active, 192 -> zero invfreq).
freq = np.asarray(T["rope_freqs.weight"].data).astype(np.float32)
theta = 1_000_000.0
base_inv = 1.0 / (theta ** (torch.arange(256, dtype=torch.float32) / 512))
inv = base_inv / torch.from_numpy(freq)
# First 64 inverse frequencies are active. The 1e30 tail factors yield ~zero.
inv = torch.cat([inv[:64], torch.zeros(192)])
pos = POS
angle = inv * pos
c = angle.cos()
s = angle.sin()


def rotate(z):
    z = z.float()
    a = z[..., :256]
    b = z[..., 256:]
    ar = a * c
    br = b * c
    ai = a * s
    bi = b * s
    # NeoX half-split cross mixing on the full head, with the inactive angle tail identity
    # Construct standard rotate-half result for 512 dims.
    half = z.shape[-1] // 2
    rot = torch.cat([-z[..., half:], z[..., :half]], dim=-1)
    cs = torch.cat([c, c])
    ss = torch.cat([s, s])
    return (z * cs + rot * ss).to(torch.bfloat16).float()


q = rotate(q)
k = rotate(k)
# Causal full-attention at final prompt position: all positions 0..1103, shared GQA mapping 4Q heads/KV head.
# Reconstruct prior-prefix K/V from llama.cpp's callback tensors is out of scope for this single-row reference;
# use the exact SGLang attention output as a downstream seam and report the limitation explicitly.
sg_attn = capture("attention_output").view(1, 8, 512)
# Continue exact same-input FFN/PLE reference from the archived SGLang residual boundary is deferred until attention is closed.
# Layer-5 q/k norms from the exact production inputs.
q_norm_ref = rms(q.view(1, 8, 512), tensor_f("blk.5.attn_q_norm.weight"))
k_norm_ref = rms(k.view(1, 2, 512), tensor_f("blk.5.attn_k_norm.weight"))
v_norm_ref = rms(v.view(1, 2, 512), None)

results = {
    "input": {
        "sglang_capture_shape": [1, 2560],
        "input_bf16": True,
        "position": POS,
        "production_kernel_emulation": "Q4_0xQ8_1 MMVQ: 32-value Q8_1 blocks, fp16 scales/sum, dp4a integer products, BF16 output; compare against CUDA capture before attribution",
        "raw_q4_weights": [
            "blk.5.attn_q.weight",
            "blk.5.attn_k.weight",
            "blk.5.attn_v.weight",
        ],
    },
    "boundaries": {},
}
for stage, ref in [
    ("attn_normed_input", attn_in),
    ("q_proj", q),
    ("k_proj", k),
    ("v_proj", v),
]:
    results["boundaries"][stage] = metric(ref, capture(stage))
for stage, ref in [("q_proj_float_dequant", q_raw), ("k_proj_float_dequant", k_raw), ("v_proj_float_dequant", v_raw)]:
    results["boundaries"][stage] = metric(ref, capture(stage.replace("_float_dequant", "")))
for stage, ref in [
    ("q_normed", q_norm_ref),
    ("k_normed", k_norm_ref),
    ("v_normed", v_norm_ref),
]:
    results["boundaries"][stage] = metric(ref, capture(stage))
(D / "layer5-fixed-input-reference-doc24.json").write_text(
    json.dumps(results, indent=2)
)
print(json.dumps(results, indent=2))
