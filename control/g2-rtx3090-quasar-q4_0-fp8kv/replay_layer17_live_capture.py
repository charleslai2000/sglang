import json
import torch
from pathlib import Path

BASE = Path("/data/sglang-hicache/g2-quasar-runs")
CASES = {
    "bf16": BASE / "g2-4k-l17-intervention-bf16-noop-20261105T124013Z",
    "e5m2": BASE / "g2-4k-l17-intervention-e5m2-noop-20261105T132857Z",
}
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def replay(a, pk, pv):
    dev = "cuda"
    slots = a["kv_indices"].to(dev)
    q = a["q"].to(dev).contiguous()
    kc = a["current_k"].to(dev).contiguous()
    vc = a["current_v"].to(dev).contiguous()
    kb = torch.zeros(a["pool_k_shape"], dtype=pk.dtype, device=dev)
    vb = torch.zeros(a["pool_v_shape"], dtype=pv.dtype, device=dev)
    kb[slots] = pk.to(dev)
    vb[slots] = pv.to(dev)
    out = torch.empty((2048, q.shape[1], vc.shape[-1]), device=dev, dtype=q.dtype)
    extend_attention_fwd(
        q,
        kc,
        vc,
        out,
        kb,
        vb,
        a["qo_indptr"].to(dev),
        a["kv_indptr"].to(dev),
        a["kv_indices"].to(dev),
        a["custom_mask"],
        bool(a["causal"]),
        a["mask_indptr"],
        int(a["max_len_extend"]),
        float(a["k_scale"]),
        float(a["v_scale"]),
        float(a["sm_scale"]),
        logit_cap=float(a["logit_cap"]),
        sliding_window_size=int(a["sliding_window_size"]),
        sinks=None,
        window_kv_offsets=a["window_kv_offsets"],
        xai_temperature_len=int(a["xai_temperature_len"]),
        page_size=int(a["page_size"]),
        score_mod=a["score_mod"],
        aux_tensors=a["aux_tensors"],
        extend_seq_lens_cpu=[2048],
    )
    torch.cuda.synchronize()
    return out[-1:].float().cpu()


def metrics(x, y):
    d = y.float() - x.float()
    return {
        "equal": torch.equal(x.float(), y.float()),
        "relL2": float(d.norm() / x.float().norm().clamp_min(1e-30)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
    }


loaded = {}
for name, d in CASES.items():
    a = torch.load(
        d / "layer17-backend-input.pt", map_location="cpu", weights_only=True
    )
    live = torch.load(
        d / "layer17-attention.pt", map_location="cpu", weights_only=True
    )["output"].float()
    assert a["positions"][-1].item() == 4095 and a["input_ids"][-1].item() == 236187
    own = replay(a, a["prefix_k_raw"], a["prefix_v_raw"])
    print(name, "same_cache_replay", metrics(live, own))
    assert torch.equal(own, live)
    loaded[name] = (a, live)

result = {}
for name, (a, live) in loaded.items():
    other = "e5m2" if name == "bf16" else "bf16"
    b = loaded[other][0]
    # Fixed Q/current KV and all same-forward call metadata; only prefix cache bytes
    # and the cache scale/dtype coupled to that representation are changed.
    pk = b["prefix_k_raw"]
    pv = b["prefix_v_raw"]
    assert torch.equal(a["prefix_slots"], b["prefix_slots"]) and torch.equal(
        a["kv_indices"], b["kv_indices"]
    )
    cf = replay(a, pk, pv)
    result[name] = {
        "same_cache_live": metrics(
            live, replay(a, a["prefix_k_raw"], a["prefix_v_raw"])
        ),
        "reverse_cache_vs_live": metrics(live, cf),
        "reverse_output": cf,
    }
    out = BASE / f"g2-layer17-{name}-reverse-cache.attention.pt"
    torch.save({"output": cf, "upstream": name, "layer": 17, "position": 4095}, out)
    noop = BASE / f"g2-layer17-{name}-noop.attention.pt"
    torch.save({"output": live, "upstream": name, "layer": 17, "position": 4095}, noop)
    print(name, "reverse", result[name]["reverse_cache_vs_live"], out)
Path("/data/sglang-hicache/g2-quasar-runs/g2-layer17-live-path-replay.json").write_text(
    json.dumps(
        {
            k: {kk: vv for kk, vv in v.items() if kk != "reverse_output"}
            for k, v in result.items()
        },
        indent=2,
    )
)
