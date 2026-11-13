#!/usr/bin/env python3
"""Replay one frozen Layer0 extend-attention call through production Triton."""

import argparse, json
from pathlib import Path
import torch

p = argparse.ArgumentParser()
p.add_argument("--probe", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
r = torch.load(a.probe, map_location="cpu", weights_only=False)
assert r["causal"] and r["sliding_window_size"] == 511 and r["logit_cap"] == 0
assert not r["score_mod_present"] and not r["aux_tensors_present"]
q = r["q"].cuda().contiguous()
k = r["k_current"].cuda().contiguous()
v = r["v_current"].cuda().contiguous()
qo = r["qo_indptr"].cuda().int().contiguous()
kvptr = r["kv_indptr"].cuda().int().contiguous()
kvidx = r["kv_indices"].cuda().int().contiguous()
kb = torch.zeros(r["pool_k_shape"], device="cuda", dtype=r["pool_k"].dtype)
vb = torch.zeros(r["pool_v_shape"], device="cuda", dtype=r["pool_v"].dtype)
o = torch.empty((q.shape[0], q.shape[1], v.shape[-1]), device="cuda", dtype=q.dtype)
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd

extend_attention_fwd(
    q,
    k,
    v,
    o,
    kb,
    vb,
    qo,
    kvptr,
    kvidx,
    r["custom_mask"],
    r["causal"],
    None if r["mask_indptr"] is None else r["mask_indptr"].cuda(),
    r["max_len_extend"],
    r["k_scale"],
    r["v_scale"],
    sm_scale=r["sm_scale"],
    logit_cap=r["logit_cap"],
    sliding_window_size=r["sliding_window_size"],
    window_kv_offsets=None
    if r["window_kv_offsets"] is None
    else r["window_kv_offsets"].cuda(),
    xai_temperature_len=r["xai_temperature_len"],
    page_size=r["page_size"],
    extend_seq_lens_cpu=[int(r["extend_seq_lens"][0])],
)
torch.cuda.synchronize()
actual = r["output"][r["row"] : r["row"] + 1].cuda()
replay = o[r["row"] : r["row"] + 1]
d = replay.float() - actual.float()
result = {
    "probe": a.probe,
    "rid": r["rid"],
    "position": r["position"],
    "row": r["row"],
    "qkv_shapes": [tuple(q.shape), tuple(k.shape), tuple(v.shape)],
    "qkv_dtypes": [str(q.dtype), str(k.dtype), str(v.dtype)],
    "kv_prefix_tokens": int(kvidx.numel()),
    "prod_replay_vs_capture": {
        "exact": bool(torch.equal(replay, actual)),
        "rel_l2": float(d.norm() / actual.float().norm()),
        "max_abs": float(d.abs().max()),
        "bf16_equal": bool(
            torch.equal(replay.to(torch.bfloat16), actual.to(torch.bfloat16))
        ),
    },
}
Path(a.output).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
