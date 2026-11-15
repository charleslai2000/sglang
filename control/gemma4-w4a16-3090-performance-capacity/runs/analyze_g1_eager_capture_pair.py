#!/usr/bin/env python3
"""Compare saved same-input E5M2 and BF16 eager logits captures."""

import json, math
from pathlib import Path
import torch

ROOT = Path("/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new")
rows = []
for n in (512, 513, 514):
    a = json.loads((ROOT / "bfloat16" / f"n{n}.json").read_text())
    b = json.loads((ROOT / "fp8_e5m2" / f"n{n}.json").read_text())
    assert (
        a["prompt_token_ids"] == b["prompt_token_ids"]
        and a["fixture_sha256"] == b["fixture_sha256"]
    )
    x = torch.tensor(a["first_step_logits"], dtype=torch.float64)
    y = torch.tensor(b["first_step_logits"], dtype=torch.float64)
    dx = torch.log_softmax(x, 0)
    dy = torch.log_softmax(y, 0)
    top = torch.topk(x, 2)
    topb = torch.topk(y, 2)
    g = int(x.argmax())
    h = int(y.argmax())
    chosen = int(a["generated_token_ids"][0])
    chosenb = int(b["generated_token_ids"][0])
    rows.append(
        {
            "n": n,
            "input_sha256": a["fixture_sha256"],
            "bf16_top1": g,
            "e5m2_top1": h,
            "same_top1": g == h,
            "bf16_top2": int(top.indices[1]),
            "e5m2_top2": int(topb.indices[1]),
            "bf16_top1_top2_margin": float(top.values[0] - top.values[1]),
            "e5m2_top1_top2_margin": float(topb.values[0] - topb.values[1]),
            "bf16_selected_token": chosen,
            "e5m2_selected_token": chosenb,
            "selected_token_same": chosen == chosenb,
            "bf16_selected_logprob": float(dx[chosen]),
            "e5m2_selected_logprob": float(dy[chosen]),
            "e5m2_minus_bf16_logprob_same_token": float(dy[chosen] - dx[chosen]),
            "e5m2_logprob_own_selected_token": float(dy[chosenb]),
            "full_logits_max_abs_delta": float((y - x).abs().max()),
            "full_logits_rmse_delta": float((y - x).square().mean().sqrt()),
            "full_logits_relative_l2_delta": float((y - x).norm() / x.norm()),
            "top1_token_logit_delta": float(y[g] - x[g]),
            "bf16_top1_under_e5m2_margin": float(y[g] - y.topk(2).values[1]),
            "top1_margin_delta": float(
                (top.values[0] - top.values[1]) - (topb.values[0] - topb.values[1])
            ),
        }
    )
print(json.dumps(rows, indent=2))
(ROOT / "eager-pair-delta.json").write_text(json.dumps(rows, indent=2) + "\n")
