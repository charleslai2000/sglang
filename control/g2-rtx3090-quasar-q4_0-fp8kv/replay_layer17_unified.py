import torch
from pathlib import Path

src = Path(
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-l17-intervention-bf16-noop-20261105T124013Z"
)
a = torch.load(src / "layer17-backend-input.pt", map_location="cpu", weights_only=True)
live = torch.load(src / "layer17-attention.pt", map_location="cpu", weights_only=True)[
    "output"
]
assert a["positions"][-1].item() == 4095 and a["input_ids"][-1].item() == 236187
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def run(prefix_k, prefix_v):
    dev = "cuda"
    slots = a["kv_indices"].to(dev)
    q = a["q"].to(dev).contiguous()
    kc = a["current_k"].to(dev).contiguous()
    vc = a["current_v"].to(dev).contiguous()
    kb = torch.zeros(a["pool_k_shape"], dtype=prefix_k.dtype, device=dev)
    vb = torch.zeros(a["pool_v_shape"], dtype=prefix_v.dtype, device=dev)
    kb[slots] = prefix_k.to(dev)
    vb[slots] = prefix_v.to(dev)
    out = torch.empty((2048, 8, 512), device=dev, dtype=q.dtype)
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


out = run(a["prefix_k_raw"], a["prefix_v_raw"])
d = out - live.float()
print(
    "two_stage_vs_live",
    float(d.norm() / live.float().norm()),
    float(d.abs().max()),
    int(torch.count_nonzero(d)),
)
assert torch.equal(out, live.float()), "same-path exact replay failed"
torch.save(
    {"output": out},
    "/data/sglang-hicache/g2-quasar-runs/g2-4k-l17-two-stage-replay-bf16.pt",
)
