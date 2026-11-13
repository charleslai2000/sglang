#!/usr/bin/env python3
"""Summarize fixed-sample Stop ON/OFF replay and initial-logit captures."""

import json, torch
from pathlib import Path

RUN = Path("/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun")
recs = json.loads((RUN / "replays.json").read_text())
logits = {}
for f in RUN.glob("forward.*.logits"):
    x = torch.load(f, map_location="cpu", weights_only=False)
    logits[x["rid"][0]] = x
out = []
for case in sorted({x["case"] for x in recs}, key=int):
    off = [x for x in recs if x["case"] == case and x["policy"] == "off"]
    on = [x for x in recs if x["case"] == case and x["policy"] == "on"]
    assert len(off) == len(on) == 3
    pids = off[0]["prompt_ids"]
    assert all(x["prompt_ids"] == pids and x["prompt_ids_echo_match"] for x in off + on)
    off_ids = off[0]["output_ids"]
    on_ids = on[0]["output_ids"]
    assert all(x["output_ids"] == off_ids for x in off) and all(
        x["output_ids"] == on_ids for x in on
    )
    cap = [logits[x["rid"]] for x in off + on]
    assert all(torch.equal(cap[0]["output"], x["output"]) for x in cap)
    z = cap[0]["output"].flatten().float()
    top = torch.topk(z, 5)
    i = 0
    while i < min(len(off_ids), len(on_ids)) and off_ids[i] == on_ids[i]:
        i += 1
    out.append(
        {
            "doc_id": int(case),
            "prompt_sha256": off[0]["prompt_sha256"],
            "prompt_ids_returned_exact": True,
            "off_ids_stable_3of3": True,
            "on_ids_stable_3of3": True,
            "initial_full_logits_bitwise_identical_all_6": True,
            "initial_top5_ids": top.indices.tolist(),
            "initial_top5_logits": top.values.tolist(),
            "off_tokens": len(off_ids),
            "on_tokens_including_stop": len(on_ids),
            "first_raw_ids_difference": i,
            "on_stop": on[0]["matched_stop"],
            "on_stop_at_token_ids": [14977, 236787]
            if on[0]["matched_stop"] == "Question:"
            else None,
            "forward_ids": [x["forward_id"] for x in cap],
        }
    )
(RUN / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
