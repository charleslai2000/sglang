import json
from pathlib import Path

import torch

B = Path("/data/sglang-hicache/g2-quasar-runs/g2-4k-full17-bfloat16-20261104T234010Z")
F = Path("/data/sglang-hicache/g2-quasar-runs/g2-4k-full17-fp8_e5m2-20261105T000655Z")
OUT = Path("/data/sglang-hicache/g2-quasar-runs/g2-4k-layer17-cache-only-20261105.json")


def load(d):
    p = torch.load(d / "probe.layer17.pt", map_location="cpu", weights_only=True)
    y = torch.load(
        d / "attn.layer17.pos4095.output.pt", map_location="cpu", weights_only=True
    )["output"]
    return p, y


pb, yb = load(B)
pf, yf = load(F)
for p in (pb, pf):
    assert p["q_full"].shape == (2048, 8, 512)
    assert p["current_k"].shape == (2048, 2, 512)
    assert p["sliding_window_size"] == -1
    assert p["production_call"]["causal"] and not p["production_call"]["custom_mask"]
    assert p["production_call"]["page_size"] == 1
assert torch.equal(pb["prefix_slots"], pf["prefix_slots"])
assert torch.equal(pb["kv_indices"], pf["kv_indices"])
assert torch.equal(pb["window_kv_indices"], pf["window_kv_indices"])
for name in ("prefix_k_raw", "prefix_v_raw"):
    assert torch.equal(
        pb[name].to(torch.float8_e5m2).view(torch.uint8),
        pf[name].view(torch.uint8),
    )

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def run(qp, kp):
    dev = "cuda"
    q = qp["q_full"].to(dev).contiguous()
    kc = qp["current_k"].to(dev).contiguous()
    vc = qp["current_v"].to(dev).contiguous()
    slots = qp["kv_indices"].to(dev)
    prefix_k = kp["prefix_k_raw"].to(dev)
    prefix_v = kp["prefix_v_raw"].to(dev)
    raw_k = torch.zeros(qp["pool_k_shape"], dtype=prefix_k.dtype, device=dev)
    raw_v = torch.zeros(qp["pool_v_shape"], dtype=prefix_v.dtype, device=dev)
    raw_k[slots] = prefix_k
    raw_v[slots] = prefix_v
    qo = qp["qo_indptr"].to(dev)
    kv = qp["kv_indptr"].to(dev)
    indices = qp["kv_indices"].to(dev)
    out = torch.empty((2048, 8, 512), dtype=q.dtype, device=dev)
    extend_attention_fwd(
        q,
        kc,
        vc,
        out,
        raw_k,
        raw_v,
        qo,
        kv,
        indices,
        None,
        True,
        None,
        max_len_extend=2048,
        k_scale=1.0,
        v_scale=1.0,
        sm_scale=float(qp["sm_scale"]),
        logit_cap=0.0,
        sliding_window_size=-1,
        sinks=None,
        window_kv_offsets=None,
        xai_temperature_len=-1,
        page_size=1,
        score_mod=None,
        aux_tensors=None,
        extend_seq_lens_cpu=[2048],
    )
    torch.cuda.synchronize()
    return out[2047:2048].float().cpu()


def metrics(a, b):
    a, b = a.float(), b.float()
    d = b - a
    return {
        "rel_l2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "p99_abs": float(torch.quantile(d.abs(), 0.99)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
    }


rows = {}
for runname, qsrc, live in [("BF16_run", pb, yb), ("E5M2_run", pf, yf)]:
    cache_outputs = {}
    for cachename, csrc in [("BF16_cache", pb), ("E5M2_cache", pf)]:
        out = run(qsrc, csrc)
        cache_outputs[cachename] = out
        print(runname, cachename, "replay_to_live", metrics(live, out))
    print(
        runname,
        "cache_only_delta_vs_BF16_cache",
        metrics(cache_outputs["BF16_cache"], cache_outputs["E5M2_cache"]),
    )
    rows[runname] = {
        "BF16_cache_vs_live": metrics(live, cache_outputs["BF16_cache"]),
        "E5M2_cache_vs_live": metrics(live, cache_outputs["E5M2_cache"]),
        "KV_only_delta_E5M2_vs_BF16": metrics(
            cache_outputs["BF16_cache"], cache_outputs["E5M2_cache"]
        ),
    }

result = {
    "metadata": {
        "layer": 17,
        "position": 4095,
        "kv_indices_identical": True,
        "prefix_bf16_cast_byte_equal_to_e5m2": True,
        "kernel": "production Triton extend_attention_fwd",
        "q_and_current_kv_fixed_within_each_run": True,
    },
    "production_pair": metrics(yb, yf),
    "runs": rows,
}
OUT.write_text(json.dumps(result, indent=2))
print(OUT)
