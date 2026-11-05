#!/usr/bin/env python3
"""T003 L17 A/B/C replay; private kernel copy, immutable T002 captures."""

import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import torch

ROOT = Path("/data/sglang-hicache/g2-quasar-runs")
REPO = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
BF = ROOT / "g2-4k-l17-intervention-bf16-noop-20261105T124013Z"
FP = ROOT / "g2-4k-l17-intervention-e5m2-noop-20261105T132857Z"
OUT = ROOT / "g2-layer17-abc-precision.json"


def load(p):
    return torch.load(p, map_location="cpu", weights_only=True)


def stats(a, b):
    a, b = a.float(), b.float()
    d = b - a
    return {
        "relL2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "p99_abs": float(torch.quantile(d.abs().flatten(), 0.99)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
        "equal": torch.equal(a, b),
    }


bf = load(BF / "layer17-backend-input.pt")
fp = load(FP / "layer17-backend-input.pt")
for k in ("positions", "prefix_slots", "kv_indices", "kv_indptr", "qo_indptr"):
    assert torch.equal(bf[k], fp[k]), k
for k in (
    "causal",
    "max_len_extend",
    "page_size",
    "logit_cap",
    "sliding_window_size",
    "sm_scale",
    "k_scale",
    "v_scale",
):
    assert bf[k] == fp[k], k
for k in ("prefix_k_raw", "prefix_v_raw"):
    assert torch.equal(
        bf[k].to(torch.float8_e5m2).view(torch.uint8), fp[k].view(torch.uint8)
    ), k
assert (
    torch.equal(bf["kv_indices"], bf["prefix_slots"])
    and bf["page_size"] == 1
    and bf["sliding_window_size"] == -1
)
# Private package overlay: only this kernel module comes from HEAD; normal runtime imports remain in checkout.
tmp = Path(tempfile.mkdtemp(prefix="g2-t003-kernel-"))
for rel in (
    "sglang/__init__.py",
    "sglang/kernels/__init__.py",
    "sglang/kernels/ops/__init__.py",
    "sglang/kernels/ops/attention/__init__.py",
):
    dst = tmp / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if rel == "sglang/__init__.py":
        dst.write_text(
            f'__path__ = [{str(REPO / "python/sglang")!r}, str(__import__("pathlib").Path(__file__).parent)]\n'
        )
    elif rel == "sglang/kernels/__init__.py":
        dst.write_text(
            '__path__ = [str(__import__("pathlib").Path(__file__).parents[1] / "python/sglang/kernels"), str(__import__("pathlib").Path(__file__).parent)]\n'
        )
    else:
        shutil.copy2(REPO / "python" / rel, dst)
source = subprocess.check_output(
    ["git", "show", "HEAD:python/sglang/kernels/ops/attention/extend_attention.py"],
    cwd=REPO,
)
(tmp / "sglang/kernels/ops/attention/extend_attention.py").write_bytes(source)
import importlib.util
private_source = tmp / "sglang/kernels/ops/attention/extend_attention.py"
spec = importlib.util.spec_from_file_location(
    "sglang.kernels.ops.attention._t003_head_extend", private_source
)
private_kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(private_kernel)
extend_attention_fwd = private_kernel.extend_attention_fwd


def replay(arm):
    dev = "cuda"
    q = bf["q"].to(dev).contiguous()
    kc = bf["current_k"].to(dev).contiguous()
    vc = bf["current_v"].to(dev).contiguous()
    slots = bf["kv_indices"].to(dev)
    if arm == "A":
        pk, pv = bf["prefix_k_raw"], bf["prefix_v_raw"]
        dtype = torch.bfloat16
        ks = vs = 1.0
    elif arm == "B":
        pk, pv = fp["prefix_k_raw"], fp["prefix_v_raw"]
        dtype = torch.float8_e5m2
        ks, vs = float(fp["k_scale"]), float(fp["v_scale"])
    else:
        pk = (fp["prefix_k_raw"].float() * float(fp["k_scale"])).to(torch.bfloat16)
        pv = (fp["prefix_v_raw"].float() * float(fp["v_scale"])).to(torch.bfloat16)
        dtype = torch.bfloat16
        ks = vs = 1.0
    kb = torch.zeros(bf["pool_k_shape"], dtype=dtype, device=dev)
    vb = torch.zeros(bf["pool_v_shape"], dtype=dtype, device=dev)
    kb[slots] = pk.to(dev)
    vb[slots] = pv.to(dev)
    out = torch.empty((2048, 8, 512), dtype=q.dtype, device=dev)
    extend_attention_fwd(
        q,
        kc,
        vc,
        out,
        kb,
        vb,
        bf["qo_indptr"].to(dev),
        bf["kv_indptr"].to(dev),
        bf["kv_indices"].to(dev),
        None,
        True,
        None,
        2048,
        ks,
        vs,
        float(bf["sm_scale"]),
        logit_cap=float(bf["logit_cap"]),
        sliding_window_size=-1,
        sinks=None,
        window_kv_offsets=None,
        xai_temperature_len=int(bf["xai_temperature_len"]),
        page_size=1,
        score_mod=None,
        aux_tensors=None,
        extend_seq_lens_cpu=[2048],
    )
    torch.cuda.synchronize()
    r = out[-1:].float().cpu()
    del kb, vb, out
    return r


live = load(BF / "layer17-attention.pt")["output"].float()
bref = load(ROOT / "g2-layer17-bf16-reverse-cache.attention.pt")["output"].float()
A, B, C = (replay(x) for x in "ABC")
assert torch.equal(A, live), "A not exact BF16 live"
assert torch.equal(B, bref), "B not exact same-upstream cache counterfactual"
ck = (fp["prefix_k_raw"].float() * float(fp["k_scale"])).to(torch.bfloat16)
cv = (fp["prefix_v_raw"].float() * float(fp["v_scale"])).to(torch.bfloat16)
assert torch.equal(
    ck,
    (fp["prefix_k_raw"].to(torch.bfloat16) * float(fp["k_scale"])).to(torch.bfloat16),
)
assert torch.equal(
    cv,
    (fp["prefix_v_raw"].to(torch.bfloat16) * float(fp["v_scale"])).to(torch.bfloat16),
)
for a, x in zip("ABC", (A, B, C)):
    torch.save(
        {"output": x, "upstream": "bf16", "layer": 17, "position": 4095, "arm": a},
        ROOT / f"g2-layer17-bf16-{a}.attention.pt",
    )
res = {
    "metadata": {
        "fixed_upstream": "BF16 capture",
        "physical_slot_ids_preserved": True,
        "A": "BF16 cache/BF16 production kernel",
        "B": "E5M2 raw cache/current production kernel",
        "C": "same E5M2 bytes; scale applied once into independent BF16 pool/BF16 kernel",
        "k_scale": float(fp["k_scale"]),
        "v_scale": float(fp["v_scale"]),
        "A_live_exact": True,
        "B_counterfactual_exact": True,
    },
    "attention": {"A_vs_B": stats(A, B), "B_vs_C": stats(B, C), "A_vs_C": stats(A, C)},
}
OUT.write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
print(OUT)
