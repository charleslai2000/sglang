import json
from pathlib import Path
import torch

B = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-bfloat16-20261104T225902Z"
)
F = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-fp8_e5m2-20261104T232119Z"
)
OUT = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-layer17-production-kv-cross-20261104.json"
)


def load(d):
    p = torch.load(d / "probe.layer17.pt", map_location="cpu", weights_only=True)
    o = torch.load(
        d / "attn.layer17.pos4095.output.pt", map_location="cpu", weights_only=True
    )["output"]
    return p, o


pb, ob = load(B)
pf, of = load(F)
assert pb["positions"].tolist() == pf["positions"].tolist() == [4095]
# Request allocators differ by a constant offset; preserve each sequence's
# captured logical ordering when placing it into the synthetic pool below.
assert torch.equal(pb["prefix_slots"][1:] - pb["prefix_slots"][:-1], torch.ones(2047, dtype=pb["prefix_slots"].dtype))
assert torch.equal(pf["prefix_slots"][1:] - pf["prefix_slots"][:-1], torch.ones(2047, dtype=pf["prefix_slots"].dtype))
assert torch.equal(
    pb["prefix_k_raw"].to(torch.float8_e5m2).view(torch.uint8),
    pf["prefix_k_raw"].view(torch.uint8),
)
assert torch.equal(
    pb["prefix_v_raw"].to(torch.float8_e5m2).view(torch.uint8),
    pf["prefix_v_raw"].view(torch.uint8),
)
assert pb["sliding_window_size"] == pf["sliding_window_size"] == -1
assert pb["k_scale"] == pf["k_scale"] == 1.0 and pb["v_scale"] == pf["v_scale"] == 1.0
assert pb["sm_scale"] == pf["sm_scale"]

# Force exact production 2-stage Triton Extend implementation on each Q/KV pairing.
# Physical prefix slots retain their relative ordering; current Extend K/V stay BF16,
# as in the real runs.
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def replay(qsrc, kvsrc):
    dev = "cuda"
    q = qsrc["q_full"].to(dev).contiguous()
    kc = kvsrc["current_k"].to(dev).contiguous()
    vc = kvsrc["current_v"].to(dev).contiguous()
    slots = kvsrc["kv_indices"].to(dev)
    raw_k_src = kvsrc["prefix_k_raw"].to(dev)
    raw_v_src = kvsrc["prefix_v_raw"].to(dev)
    nslots = max(int(slots.max().item()) + 1, int(slots.numel()) + 1)
    shape = (nslots, raw_k_src.shape[1], raw_k_src.shape[2])
    raw_k = torch.zeros(shape, dtype=raw_k_src.dtype, device=dev)
    raw_v = torch.zeros(shape, dtype=raw_v_src.dtype, device=dev)
    raw_k[slots] = raw_k_src
    raw_v[slots] = raw_v_src
    qo = torch.tensor([0, q.shape[0]], device=dev, dtype=torch.int32)
    kv = torch.tensor([0, slots.numel()], device=dev, dtype=torch.int32)
    out = torch.empty((q.shape[0], q.shape[1], vc.shape[-1]), device=dev, dtype=q.dtype)
    extend_attention_fwd(
        q,
        kc,
        vc,
        out,
        raw_k,
        raw_v,
        qo,
        kv,
        slots,
        None,
        True,
        None,
        max_len_extend=q.shape[0],
        k_scale=float(kvsrc["k_scale"]),
        v_scale=float(kvsrc["v_scale"]),
        sm_scale=float(kvsrc["sm_scale"]),
        logit_cap=0.0,
        sliding_window_size=-1,
        sinks=None,
        window_kv_offsets=None,
        xai_temperature_len=-1,
        page_size=1,
        score_mod=None,
        aux_tensors=None,
        extend_seq_lens_cpu=[q.shape[0]],
    )
    torch.cuda.synchronize()
    return out[2047:2048].float().cpu()


def metric(ref, val):
    a, b = ref.float(), val.float()
    d = b - a
    return {
        "rel_l2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "p99_abs": float(torch.quantile(d.abs(), 0.99)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
    }


outs = {}
for qname, q in [("BF_Q", pb), ("FP_Q", pf)]:
    for kname, kv in [("BF_KV", pb), ("FP_KV", pf)]:
        key = f"{qname}__{kname}"
        y = replay(q, kv)
        outs[key] = y
        print(key, "vs_Bprod", metric(ob, y), "vs_Fprod", metric(of, y))

result = {
    "metadata": {
        "layer": 17,
        "position": 4095,
        "forward_type": "causal Full Attention Extend",
        "prefix_tokens": 2048,
        "extend_tokens": 2048,
        "window": -1,
        "same_physical_prefix_slot_sequence": True,
        "BF16_prefix_cast_equals_FP8_E5M2_bytes": True,
        "crossed": ["Q only", "KV only", "both"],
        "production_extend_kernel": True,
    },
    "metrics": {
        k: {"vs_BF16_production": metric(ob, v), "vs_E5M2_production": metric(of, v)}
        for k, v in outs.items()
    },
    "production_pair": metric(ob, of),
}
OUT.write_text(json.dumps(result, indent=2))
print(OUT)
