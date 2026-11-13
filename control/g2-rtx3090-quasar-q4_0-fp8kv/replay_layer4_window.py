import json
from pathlib import Path
import torch

B = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-bfloat16-20261104T223356Z"
)
F = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-fp8_e5m2-20261104T224338Z"
)
OUT = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-layer4-window-replay-20261105.json"
)


def load(d):
    p = torch.load(d / "probe.layer4.pt", map_location="cpu", weights_only=True)
    y = torch.load(
        d / "attn.layer4.pos4095.output.pt", map_location="cpu", weights_only=True
    )["output"]
    return p, y


pb, yb = load(B)
pf, yf = load(F)
for p in (pb, pf):
    assert p["positions"].tolist() == [4095]
    assert p["q_full"].shape == (2048, 8, 256)
    assert p["current_k"].shape == p["current_v"].shape == (2048, 2, 256)
    assert p["sliding_window_size"] == 511
    assert p["kv_indices"].numel() == 511
assert torch.equal(pb["prefix_slots"], pf["prefix_slots"])
assert torch.equal(pb["window_kv_indices"], pf["window_kv_indices"])
assert torch.equal(pb["kv_indices"], pf["kv_indices"])
assert torch.equal(pb["q_full"][2047], pf["q_full"][2047])
for name in ("prefix_k_raw", "prefix_v_raw"):
    assert torch.equal(
        pb[name].to(torch.float8_e5m2).view(torch.uint8), pf[name].view(torch.uint8)
    )

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def run(qsrc, kvsrc):
    dev = "cuda"
    q = qsrc["q_full"].to(dev).contiguous()
    kc = qsrc["current_k"].to(dev).contiguous()
    vc = qsrc["current_v"].to(dev).contiguous()
    slots = kvsrc["kv_indices"].to(dev)
    pk = kvsrc["prefix_k_raw"].to(dev)
    pv = kvsrc["prefix_v_raw"].to(dev)
    nslots = int(slots.max().item()) + 1
    kb = torch.zeros((nslots, 2, 256), dtype=pk.dtype, device=dev)
    vb = torch.zeros((nslots, 2, 256), dtype=pv.dtype, device=dev)
    kb[slots] = pk
    vb[slots] = pv
    qo = torch.tensor([0, 2048], device=dev, dtype=torch.int32)
    kv = torch.tensor([0, 511], device=dev, dtype=torch.int32)
    out = torch.empty((2048, 8, 256), dtype=q.dtype, device=dev)
    extend_attention_fwd(
        q,
        kc,
        vc,
        out,
        kb,
        vb,
        qo,
        kv,
        slots,
        None,
        True,
        None,
        max_len_extend=2048,
        k_scale=float(kvsrc["k_scale"]),
        v_scale=float(kvsrc["v_scale"]),
        sm_scale=float(kvsrc["sm_scale"]),
        logit_cap=0.0,
        sliding_window_size=511,
        sinks=None,
        window_kv_offsets=kvsrc["window_offsets"].to(dev),
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


results = {}
for qn, qsrc, live in [("BF16_forward", pb, yb), ("E5M2_forward", pf, yf)]:
    outs = {}
    for kn, kvsrc in [("BF16_pool", pb), ("E5M2_pool", pf), ("BF16_current_KV", pb), ("E5M2_current_KV", pf)]:
        # For current-KV crossover keep the prefix pool fixed to qsrc; this
        # query's effective window contains current-chunk positions only.
        if kn.endswith("current_KV"):
            data = {**qsrc, "current_k": kvsrc["current_k"], "current_v": kvsrc["current_v"]}
            cache = qsrc
        else:
            data, cache = qsrc, kvsrc
        o = run(data, cache)
        outs[kn] = o
        print(qn, kn, "vs live", metrics(live, o))
    print(qn, "current-KV delta", metrics(outs["BF16_current_KV"], outs["E5M2_current_KV"]))
    results[qn] = {f"{k}_vs_live": metrics(live, v) for k, v in outs.items()}
    results[qn]["current_KV_cross_delta"] = metrics(outs["BF16_current_KV"], outs["E5M2_current_KV"])

# Scan every logical current key/value row in [3584,4095], not sampled boundaries.
for name in ("current_k", "current_v"):
    x = pb[name][1536:2048]
    y = pf[name][1536:2048]
    diff = (x.float() - y.float()).reshape(512, -1).norm(dim=1) > 0
    inds = diff.nonzero().flatten()
    print(
        name,
        "different_rows",
        int(diff.sum()),
        "first",
        3584 + int(inds[0]) if len(inds) else None,
        "last",
        3584 + int(inds[-1]) if len(inds) else None,
        "all_window_exact",
        not bool(diff.any()),
    )

result = {
    "layer": 4,
    "position": 4095,
    "effective_window": [3584, 4095],
    "input_id": int(
        torch.load(
            B / "current-kv.layer4.pos4095", map_location="cpu", weights_only=True
        )["input_id"]
    ),
    "prefix_is_read_by_position4095": False,
    "same_q_at_position": True,
    "same_physical_prefix_slots": True,
    "full_window_replay": results,
}
OUT.write_text(json.dumps(result, indent=2))
print(OUT)
