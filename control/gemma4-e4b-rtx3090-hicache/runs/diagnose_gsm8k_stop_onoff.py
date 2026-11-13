#!/usr/bin/env python3
"""Check paired token IDs and prefill logits for 12-case stop-policy replay."""

import hashlib, json
from pathlib import Path
import torch
from transformers import AutoTokenizer

ROOT = Path("/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun")
tok = AutoTokenizer.from_pretrained(
    "/data/sglang-hicache/gemma4/model", trust_remote_code=True
)
records = json.loads((ROOT / "replays.json").read_text())
cases = json.loads((ROOT / "cases.json").read_text())
by = {}
for r in records:
    by.setdefault((r["case"], r["policy"]), []).append(r)
logit_files = []
for f in ROOT.glob("forward.*.logits"):
    try:
        rec = torch.load(f, map_location="cpu", weights_only=False)
    except Exception:
        continue
    logit_files.append((f, rec))
out = []
for doc in sorted(cases, key=int):
    a = by[(doc, "off")]
    b = by[(doc, "on")]
    assert len(a) == len(b) == 3
    off_ids = a[0]["output_ids"]
    on_ids = b[0]["output_ids"]
    stable_off = all(x["output_ids"] == off_ids for x in a)
    stable_on = all(x["output_ids"] == on_ids for x in b)
    prefix = 0
    while prefix < min(len(off_ids), len(on_ids)) and off_ids[prefix] == on_ids[prefix]:
        prefix += 1
    prompt = a[0]["prompt_ids"]
    assert all(x["prompt_ids"] == prompt for x in a + b)
    assert all(x["prompt_ids_echo_match"] for x in a + b)
    # Validate text with SGLang's stop-trim contract: returned ids may include the
    # matched string-stop token, while completion text intentionally excludes it.
    decoded_off = tok.decode(off_ids, skip_special_tokens=False)
    decoded_on = tok.decode(on_ids, skip_special_tokens=False)
    off_ok = a[0]["text"] == decoded_off
    on_trimmed = (
        decoded_on.split("Question:", 1)[0]
        if b[0]["matched_stop"] == "Question:"
        else decoded_on
    )
    on_ok = b[0]["text"] == on_trimmed
    captures = []
    for f, r in logit_files:
        ids = r.get("input_ids")
        if ids is None:
            continue
        if (
            torch.as_tensor(ids).numel() == len(prompt)
            and torch.as_tensor(ids).reshape(-1).tolist() == prompt
        ):
            logits = r["output"].reshape(-1, r["output"].shape[-1])[-1].float()
            captures.append(
                {
                    "file": f.name,
                    "rid": r.get("rid"),
                    "forward_id": r.get("forward_id"),
                    "input_exact": True,
                    "shape": list(r["output"].shape),
                    "top5_ids": torch.topk(logits, 5).indices.tolist(),
                    "top5_logits": torch.topk(logits, 5).values.tolist(),
                    "top1": int(logits.argmax()),
                }
            )
    out.append(
        {
            "doc_id": int(doc),
            "prompt_sha256": a[0]["prompt_sha256"],
            "prompt_ids_exact_and_echoed": True,
            "off_rids": [x["rid"] for x in a],
            "on_rids": [x["rid"] for x in b],
            "off_repeats_token_stable": stable_off,
            "on_repeats_token_stable": stable_on,
            "off_token_count": len(off_ids),
            "on_token_count": len(on_ids),
            "first_token_id_divergence": prefix,
            "off_finish": a[0]["finish_reason"],
            "on_finish": b[0]["finish_reason"],
            "on_matched_stop": b[0]["matched_stop"],
            "off_text_matches_decoded_ids": off_ok,
            "on_text_matches_decoded_ids_after_match_trim": on_ok,
            "prefill_logit_captures": captures,
        }
    )
print(json.dumps(out, indent=2))
(ROOT / "diagnosis.json").write_text(json.dumps(out, indent=2) + "\n")
assert all(x["off_repeats_token_stable"] and x["on_repeats_token_stable"] for x in out)
assert all(
    x["prompt_ids_exact_and_echoed"]
    and x["off_text_matches_decoded_ids"]
    and x["on_text_matches_decoded_ids_after_match_trim"]
    for x in out
)
