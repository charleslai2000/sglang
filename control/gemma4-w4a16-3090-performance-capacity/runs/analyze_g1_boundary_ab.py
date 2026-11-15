#!/usr/bin/env python3
"""Concise comparison of fixed new boundary probes; never claims historical replay."""

import json
from pathlib import Path
import torch

ROOT = Path("/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new")
hf = {r["n"]: r for r in json.loads((ROOT / "hf-reference.json").read_text())}
hfd = {r["n"]: r for r in json.loads((ROOT / "hf-decode-reference.json").read_text())}
result = []
for n in (512, 513, 514):
    ref = torch.tensor(hf[n]["full_logits"], dtype=torch.float64)
    row = {
        "n": n,
        "fixture_class": "new explicit-BOS GSM8K prompt prefix; not historical replay",
        "hf_greedy": hf[n]["greedy_token"],
        "arms": {},
    }
    arms = {}
    for d in ("bfloat16", "fp8_e5m2"):
        p = ROOT / d / f"n{n}.json"
        r = json.loads(p.read_text())
        x = torch.tensor(r["first_step_logits"], dtype=torch.float64)
        g = int(x.argmax())
        lp = torch.log_softmax(x, 0)
        diff = x - ref
        output_ids = r["generated_token_ids"]
        output_lp = (r.get("generated_token_logprobs") or [])[-len(output_ids) :]
        hfrow = next(a for a in hfd[n]["arms"] if a["dtype"] == d)
        dl = hfrow["logprob_deltas"]
        row["arms"][d] = {
            "first_greedy": g,
            "matches_HF_greedy": g == hf[n]["greedy_token"],
            "selected_logprob": float(lp[g]),
            "selected_logprob_delta_vs_HF": float(lp[g] - torch.log_softmax(ref, 0)[g]),
            "logits_max_abs_vs_HF": float(diff.abs().max()),
            "logits_RMSE_vs_HF": float(diff.square().mean().sqrt()),
            "logits_relL2_vs_HF": float(diff.norm() / ref.norm()),
            "continuous_tokens": output_ids,
            "output_logprob_count": len(output_lp),
            "HF_teacher_forced_decode_mean_abs_selected_logprob_delta": sum(
                map(abs, dl)
            )
            / len(dl),
            "HF_teacher_forced_decode_max_abs_selected_logprob_delta": max(
                map(abs, dl)
            ),
            "HF_teacher_forced_first_token_divergence": hfrow[
                "first_token_divergence_from_SGLang"
            ],
        }
        arms[d] = r
    bt, et = (
        arms["bfloat16"]["generated_token_ids"],
        arms["fp8_e5m2"]["generated_token_ids"],
    )
    div = next((i for i, (a, b) in enumerate(zip(bt, et)) if a != b), None)
    row["bf16_e5m2_first_free_running_divergence"] = div
    row["bf16_e5m2_token_prefix_length"] = (
        div if div is not None else min(len(bt), len(et))
    )
    row["greedy_margin_vs_runnerup_HF"] = float(
        torch.topk(ref, 2).values.diff().abs()[0]
    )
    result.append(row)
(ROOT / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
