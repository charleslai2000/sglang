#!/usr/bin/env python3
"""Replay the non-MoE Layer5 FFN/PLE suffix from immutable doc24 captures."""

from pathlib import Path
import json
import torch
import gguf

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
GGUF = "/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf"
UUID = "f1fcb176bfef46539bc32f5bdec4446f"
POS = 1103
reader = gguf.GGUFReader(GGUF)
tensors = {t.name: t for t in reader.tensors}


def cap(stage):
    rec = torch.load(
        D / f"l5-fp32-ops.{UUID}.layer5.pos{POS}.{stage}.pt",
        map_location="cpu",
        weights_only=False,
    )
    return rec["value"].float().cuda().to(torch.bfloat16)


def weight(name):
    t = tensors[name]
    if int(t.tensor_type) == int(gguf.GGMLQuantizationType.F16):
        return torch.from_numpy(t.data.copy()).cuda().to(torch.bfloat16)
    if int(t.tensor_type) == int(gguf.GGMLQuantizationType.F32):
        return torch.from_numpy(t.data.copy()).cuda().float()
    raise ValueError((name, t.tensor_type))


def rms(x, w):
    y = x.float() * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + 1e-6)
    return (y * w.float()).to(x.dtype)


def linear(x, w):
    return (x @ w.T).to(x.dtype)


def metrics(ref, live):
    a, b = ref.float().flatten(), live.float().flatten()
    d = a - b
    return {
        "rel_l2": float(d.norm() / b.norm().clamp_min(1e-30)),
        "max_abs": float(d.abs().max()),
        "rmse": float(d.square().mean().sqrt()),
        "cos": float(torch.nn.functional.cosine_similarity(a, b, dim=0)),
        "equal": bool(torch.equal(a, b)),
    }


# This GGUF has no experts/router tensors and native config disables MoE. The actual
# Layer5 branch is dense GELU MLP + residual + PLE + scalar.
ffn = cap("ffn_output")
# pre_ff_residual was captured before the fused pre-FFN norm mutates it.
# The actual residual at PLE is block_input + post_attention_normed.
block_input = cap("block_input")
post_attention_normed = cap("post_attention_normed")
resid = (block_input.float() + post_attention_normed.float()).to(torch.bfloat16)
ple_in = cap("ple_input")
post_ff_norm = weight("blk.5.post_ffw_norm.weight")
post_ple_norm = weight("blk.5.post_norm.weight")
scalar = weight("blk.5.layer_output_scale.weight").reshape(())
gate_w = weight("blk.5.inp_gate.weight")
proj_w = weight("blk.5.proj.weight")

ffn_norm = rms(ffn, post_ff_norm)
pre_ple = (ffn_norm + resid).to(torch.bfloat16)
gate_linear = linear(pre_ple, gate_w)
gate = torch.nn.functional.gelu(gate_linear.float(), approximate="tanh").to(
    torch.bfloat16
)
gated = (gate * ple_in).to(torch.bfloat16)
projection = linear(gated, proj_w)
contribution = rms(projection, post_ple_norm)
post_ple = (pre_ple + contribution).to(torch.bfloat16)
layer_out = (post_ple.float() * scalar.float()).to(torch.bfloat16)

stages = {
    "ffn_output_input": (ffn, cap("ffn_output")),
    "post_ffn_residual_sum": (
        resid,
        (block_input.float() + post_attention_normed.float()).to(torch.bfloat16),
    ),
    "pre_ple_base_from_ffn_plus_residual": (
        pre_ple,
        (rms(cap("ffn_output"), post_ff_norm) + resid).to(torch.bfloat16),
    ),
    "ple_gate": (gate, cap("ple_gate")),
    "ple_input_identity": (ple_in, cap("ple_input")),
    "ple_gated_input": (gated, cap("ple_gated_input")),
    "ple_projection": (projection, cap("ple_projection")),
    "ple_contribution": (contribution, cap("ple_contribution")),
    "post_ple": (post_ple, cap("post_ple")),
    "layer_output": (
        layer_out,
        torch.load(
            D / f"l5-fp32-layers.{UUID}.layer_output.5",
            map_location="cpu",
            weights_only=False,
        )["output"][-1:]
        .cuda()
        .to(torch.bfloat16),
    ),
}
result = {
    "model_sha256": "7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669",
    "forward_uuid": UUID,
    "rid": "g2-l5-doc24-fp32",
    "position": POS,
    "config": {
        "enable_moe_block": False,
        "num_experts": None,
        "top_k_experts": None,
        "intermediate_size": 10240,
        "hidden_size": 2560,
    },
    "weight_layout": {
        "blk.5.inp_gate.weight": {
            "stored_shape": list(tensors["blk.5.inp_gate.weight"].data.shape),
            "runtime_out_in": [256, 2560],
        },
        "blk.5.proj.weight": {
            "stored_shape": list(tensors["blk.5.proj.weight"].data.shape),
            "runtime_out_in": [2560, 256],
        },
        "layer_scalar": float(scalar),
    },
    "stages": {k: metrics(a, b) for k, (a, b) in stages.items()},
}
out = D / "layer5-ple-same-input-replay-doc24.json"
out.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
