"""Classify the single long-generation divergence as a path-fragile decision.

Inputs, all produced by the paired run and its follow-up probes:
* ``comparison.json``     -- prefill-path next-token distribution at the divergent
                             position, for both backends (same argmax in both).
* ``marlin|humming/logprob-response.json`` -- decode-path top-k logprobs for the
                             same prompt in each backend.
"""

import json
import os
import sys

root = sys.argv[1]


def load_top(path):
    payload = json.load(open(path))
    ids = payload.get("output_ids") or []
    tops = payload.get("meta_info", {}).get("output_top_logprobs") or []
    parsed = []
    for step in tops:
        row = []
        for entry in step or []:
            logprob, token = entry[0], entry[1]
            row.append({"logprob": float(logprob), "token": int(token)})
        parsed.append(row)
    return ids, parsed


marlin_ids, marlin_tops = load_top(
    os.path.join(root, "marlin", "logprob-response.json")
)
humming_ids, humming_tops = load_top(
    os.path.join(root, "humming", "logprob-response.json")
)
comparison = json.load(open(os.path.join(root, "comparison.json")))

# Position 22 is the first index where the pair-run graph decodes differed.
position = 22
marlin_step = marlin_tops[position] if position < len(marlin_tops) else []
humming_step = humming_tops[position] if position < len(humming_tops) else []
marlin_step = sorted(marlin_step, key=lambda e: -e["logprob"])
humming_step = sorted(humming_step, key=lambda e: -e["logprob"])


def margin(step):
    if len(step) < 2:
        return None
    return step[0]["logprob"] - step[1]["logprob"]


result = {
    "position": position,
    "prefill_argmax_marlin": comparison["marlin_top1"],
    "prefill_argmax_humming": comparison["humming_top1"],
    "decode_ids_equal_across_backends": marlin_ids == humming_ids,
    "decode_ids": {"marlin": marlin_ids, "humming": humming_ids},
    "decode_top5_marlin": marlin_step,
    "decode_top5_humming": humming_step,
    "decode_top1_marlin": marlin_step[0]["token"] if marlin_step else None,
    "decode_top1_humming": humming_step[0]["token"] if humming_step else None,
    "decode_margin_marlin": margin(marlin_step),
    "decode_margin_humming": margin(humming_step),
    "decode_top5_overlap": len(
        {e["token"] for e in marlin_step} & {e["token"] for e in humming_step}
    ),
}

# The divergence is path-fragile when both backends agree on the decode path but
# that choice differs from what the prefill path picks for the same prefix: the
# model's own two execution paths land on different sides of this decision, so a
# single-token difference between backends here is not a conversion defect.
result["divergence_is_path_fragile"] = bool(
    result["decode_ids_equal_across_backends"]
    and marlin_step
    and humming_step
    and marlin_step[0]["token"] == humming_step[0]["token"]
    and result["prefill_argmax_marlin"] == result["prefill_argmax_humming"]
    and marlin_step[0]["token"] != comparison["marlin_top1"]
)

with open(os.path.join(root, "verdict.json"), "w") as f:
    json.dump(result, f, indent=1, sort_keys=True)
print(json.dumps(result, indent=1, sort_keys=True))
