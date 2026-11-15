#!/usr/bin/env python3
import json, math, hashlib
from pathlib import Path
import torch

OUT = Path("/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new")


def load(d, n):
    return json.loads((OUT / d / f"n{n}.json").read_text())


def logprobs(logits, token_ids):
    x = torch.tensor(logits, dtype=torch.float64)
    return [float(torch.log_softmax(x, 0)[int(t)]) for t in token_ids]


res = []
for n in (512, 513, 514):
    b = load("bfloat16", n)
    e = load("fp8_e5m2", n)
    bl = torch.tensor(b["first_step_logits"], dtype=torch.float64)
    el = torch.tensor(e["first_step_logits"], dtype=torch.float64)
    bg = int(bl.argmax())
    eg = int(el.argmax())
    bt = b["generated_token_ids"] or []
    et = e["generated_token_ids"] or []
    b_lp = b.get("generated_token_logprobs") or []
    e_lp = e.get("generated_token_logprobs") or []
    lcp = 0
    while lcp < min(len(bt), len(et)) and bt[lcp] == et[lcp]:
        lcp += 1
    # Teacher-forced continuation uses identical generated BF16 tokens evaluated in each dtype.
    btf = logprobs(b["first_step_logits"], bt)
    etf = logprobs(e["first_step_logits"], bt)
    res.append(
        {
            "n": n,
            "reference": "HF same checkpoint required but not yet captured",
            "first_step": {
                "bf16_greedy": bg,
                "e5m2_greedy": eg,
                "same": bg == eg,
                "bf16_logprob_of_bf16_greedy": float(torch.log_softmax(bl, 0)[bg]),
                "e5m2_logprob_of_bf16_greedy": float(torch.log_softmax(el, 0)[bg]),
                "e5m2_logprob_of_e5m2_greedy": float(torch.log_softmax(el, 0)[eg]),
                "max_abs_logit_delta": float((el - bl).abs().max()),
                "rms_logit_delta": float((el - bl).square().mean().sqrt()),
                "relative_l2": float((el - bl).norm() / bl.norm()),
            },
            "decode": {
                "bf16_tokens": bt,
                "e5m2_tokens": et,
                "first_free_running_divergence": lcp
                if lcp < min(len(bt), len(et))
                else None,
                "generated_logprob_length": {"bf16": len(b_lp), "e5m2": len(e_lp)},
                "teacher_forced_bf16_prefix_lp_delta_firststep": etf[0] - btf[0]
                if bt
                else None,
                "teacher_forced_selected_logprobs": {"bf16": b_lp, "e5m2": e_lp},
                "note": "API output logprobs are on each dtype’s own free-running tokens; model-level same-token logprob replay beyond initial prefix has not yet been performed.",
            },
        }
    )
(OUT / "comparison.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps(res, indent=2))
