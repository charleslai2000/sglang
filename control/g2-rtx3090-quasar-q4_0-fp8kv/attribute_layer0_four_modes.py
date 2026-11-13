import json
import torch
from attribute_layer0_precision import exact_stream, rel

PROBE = "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-fp8_e5m2-20261104T172034Z/probe.layer0.pt"
BF = "/data/sglang-hicache/g2-quasar-runs/g2-4k-causal-bfloat16-20261104T144248Z/attn.layer0.pt"
LIVE = "/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-fp8_e5m2-20261104T173254Z/probe.layer0.outputs.pt"
AB = "/data/sglang-hicache/g2-quasar-runs/g2-4k-layer0-abc-strict-ordered-20261104.json"
OUT = "/data/sglang-hicache/g2-quasar-runs/g2-4k-layer0-four-modes-20261104.json"
p = torch.load(PROBE, map_location="cpu", weights_only=True)
bf = torch.load(BF, map_location="cpu", weights_only=True)
live = torch.load(LIVE, map_location="cpu", weights_only=True)["outputs"]
ab = json.load(open(AB))
# Reorder BF16 prefix by exact physical-slot identity, never treating slots as logical positions.
bmap = {int(s): i for i, s in enumerate(bf["kv_slots"])}
brow = torch.tensor([bmap[int(s)] for s in p["window_kv_indices"]])
bk, bv = bf["k_prefix_raw"][brow], bf["v_prefix_raw"][brow]
assert torch.equal(bk.to(torch.float8_e5m2), p["prefix_k_raw"])
assert torch.equal(bv.to(torch.float8_e5m2), p["prefix_v_raw"])
assert torch.equal(bf["all_k_current"], p["current_k"]) and torch.equal(
    bf["all_v_current"], p["current_v"]
)
records = {}
for pos in (2048, 2558, 2559):
    row = pos - 2048
    bi = bf["positions"].tolist().index(pos)
    q = p["q_full"][row].cuda()
    assert torch.equal(q.cpu(), bf["q"][bi])
    kc = p["current_k"][: row + 1].cuda()
    vc = p["current_v"][: row + 1].cuda()
    # A/B independently use the same recurrence but differ only in prefix cache values.
    A = exact_stream(q, bk.cuda(), bv.cuda(), kc, vc, qpos=pos)
    B = exact_stream(
        q, p["prefix_k_raw"].cuda(), p["prefix_v_raw"].cuda(), kc, vc, qpos=pos
    )
    C = torch.tensor(ab["positions"][str(pos)]["C"])[0]
    base = exact_stream(
        q, p["prefix_k_raw"].cuda(), p["prefix_v_raw"].cuda(), kc, vc, qpos=pos
    )
    variants = {}
    for qfp8 in (False, True):
        for pfp8 in (False, True):
            name = f"Qfp8_{int(qfp8)}_Pfp8_{int(pfp8)}"
            O = exact_stream(
                q,
                p["prefix_k_raw"].cuda(),
                p["prefix_v_raw"].cuda(),
                kc,
                vc,
                qpos=pos,
                q_fp8=qfp8,
                p_fp8=pfp8,
            )
            variants[name] = {
                "vs_A": rel(A, O),
                "vs_C": rel(C, O),
                "direct_from_KV_only": rel(base, O),
                "direct_delta_l2": float((O - base).norm()),
                "norm": float(O.norm()),
            }
    records[str(pos)] = {
        "A_to_B": rel(A, B),
        "B_to_C": rel(B, C),
        "C_to_live": rel(C, live[pos]),
        "variants": variants,
    }
open(OUT, "w").write(json.dumps(records, indent=2))
print(json.dumps(records, indent=2))
