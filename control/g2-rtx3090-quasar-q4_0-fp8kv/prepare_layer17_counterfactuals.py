import torch
from pathlib import Path
from replay_layer17_cache_only import load, run

base = Path("/data/sglang-hicache/g2-quasar-runs")
B, F = (
    base / "g2-4k-full17-bfloat16-20261104T234010Z",
    base / "g2-4k-full17-fp8_e5m2-20261105T000655Z",
)
pb, yb = load(B)
pf, yf = load(F)
# Build the exact production-kernel cache-format counterfactual output for each
# upstream. run(q,pool) was independently validated bitwise against live.
for upstream, qsrc, other_pool in [("bf16", pb, pf), ("e5m2", pf, pb)]:
    value = run(qsrc, other_pool)
    torch.save(
        {"output": value, "upstream": upstream, "layer": 17, "position": 4095},
        base / f"g2-layer17-{upstream}-reverse-cache.attention.pt",
    )
    live = yb if upstream == "bf16" else yf
    torch.save(
        {"output": live, "upstream": upstream, "layer": 17, "position": 4095},
        base / f"g2-layer17-{upstream}-noop.attention.pt",
    )
    print(upstream, "cf", value.shape, "delta_norm", float((value - live).norm()))
