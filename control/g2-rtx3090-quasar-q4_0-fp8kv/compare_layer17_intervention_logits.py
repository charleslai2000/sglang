import json
from pathlib import Path
import torch

ROOT = Path("/data/sglang-hicache/g2-quasar-runs")
BASES = {
    "bf16": ROOT / "g2-4k-full17-bfloat16-20261104T234010Z",
    "e5m2": ROOT / "g2-4k-full17-fp8_e5m2-20261105T000655Z",
}


def final(d):
    rows = []
    for f in d.glob("forward.*.logits"):
        r = torch.load(f, map_location="cpu", weights_only=True)
        if (
            r.get("forward_mode") == "EXTEND"
            and r["positions"].numel() == 2048
            and int(r["positions"][0]) == 2048
            and int(r["positions"][-1]) == 4095
            and r["output"].shape == (1, 262144)
        ):
            rows.append((f, r))
    if len(rows) != 1:
        raise RuntimeError(f"{d}: {len(rows)} final logits")
    return rows[0]


def metrics(a, b):
    d = b.float() - a.float()
    return {
        "relL2": float(d.norm() / a.float().norm().clamp_min(1e-30)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
    }


def tops(x):
    v, i = torch.topk(x.float().flatten(), 2)
    return {
        "top1": int(i[0]),
        "top1_logit": float(v[0]),
        "top2": int(i[1]),
        "top2_logit": float(v[1]),
        "margin": float(v[0] - v[1]),
    }


result = {}
for kv in ("bf16", "e5m2"):
    _, base = final(BASES[kv])
    bd = BASES[kv]
    refdir = ROOT / (
        "g2-4k-full17-bfloat16-20261104T234010Z"
        if kv == "bf16"
        else "g2-4k-full17-fp8_e5m2-20261105T000655Z"
    )
    outref = torch.load(
        refdir / "attn.layer17.pos4095.output.pt", map_location="cpu", weights_only=True
    )["output"]
    noopfile = ROOT / f"g2-layer17-{kv}-noop.attention.pt"
    cf_file = ROOT / f"g2-layer17-{kv}-reverse-cache.attention.pt"
    result[kv] = {"baseline": tops(base["output"]), "runs": []}
    dirs = sorted(ROOT.glob(f"g2-4k-l17-intervention-{kv}-*-*"))
    for d in dirs:
        if not d.is_dir() or not list(d.glob("forward.*.logits")) or not (d / "layer17-attention-applied.pt").exists():
            continue
        if d.name not in {
            "g2-4k-l17-intervention-bf16-noop-20261105T124013Z",
            "g2-4k-l17-intervention-e5m2-noop-20261105T132857Z",
            "g2-4k-l17-intervention-bf16-reverse-20261105T140216Z",
            "g2-4k-l17-intervention-e5m2-reverse-20261105T141236Z",
        }:
            continue
        _, r = final(d)
        ident = r["model_identity"]
        mode = ident["intervention"]
        if ident["kv"] != kv:
            continue
        item = {
            "run": d.name,
            "mode": mode,
            "delta": metrics(base["output"], r["output"]),
            **tops(r["output"]),
        }
        applied = torch.load(
            d / "layer17-attention-applied.pt", map_location="cpu", weights_only=True
        )["output"]
        # In this validated serving path the backend materializes its FP32
        # attention output in the same slot layout; compare the actual captured
        # tensor with the original run's live output for no-op, and only record
        # the reverse path's applied tensor plus its downstream logits.
        expected = outref if mode == "noop" else torch.load(
            cf_file, map_location="cpu", weights_only=True
        )["output"]
        item["applied_attention_vs_expected"] = metrics(expected, applied)
        item["actual_attention_change_vs_upstream_live"] = metrics(outref, applied)
        if mode == "noop" and item["delta"]["nonzero"]:
            raise RuntimeError(f"NOOP final logits mismatch: {item}")
        if item["applied_attention_vs_expected"]["nonzero"]:
            raise RuntimeError(
                f"Attention replacement did not match expected tensor: {item}"
            )
        result[kv]["runs"].append(item)
OUT = ROOT / "g2-layer17-intervention-logits.json"
OUT.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
print(OUT)
