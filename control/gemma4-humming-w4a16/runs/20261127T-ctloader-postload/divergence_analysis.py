"""Compare the two backends' next-token distributions at the divergence point."""

import json
import os
import sys

import torch

root = sys.argv[1]
marlin = torch.load(os.path.join(root, "marlin", "logits.pt"), map_location="cpu")[
    "logits"
][-1].float()
humming = torch.load(os.path.join(root, "humming", "logits.pt"), map_location="cpu")[
    "logits"
][-1].float()

order_m = marlin.argsort(descending=True)
order_h = humming.argsort(descending=True)
top_m = [int(v) for v in order_m[:5]]
top_h = [int(v) for v in order_h[:5]]
margin_m = float(marlin[order_m[0]] - marlin[order_m[1]])
margin_h = float(humming[order_h[0]] - humming[order_h[1]])
noise = float((humming - marlin).abs().max())
mean_abs = float((humming - marlin).abs().mean())

result = {
    "marlin_top5": top_m,
    "humming_top5": top_h,
    "marlin_top1": top_m[0],
    "humming_top1": top_h[0],
    "marlin_top1_margin": margin_m,
    "humming_top1_margin": margin_h,
    "cross_backend_max_abs_diff": noise,
    "cross_backend_mean_abs_diff": mean_abs,
    "marlin_logit_of_humming_top1": float(marlin[top_h[0]]),
    "humming_logit_of_marlin_top1": float(humming[top_m[0]]),
    # A divergence caused by bf16 noise shows a margin of the same order as the
    # cross-backend difference at those two tokens.
    "margin_within_noise": bool(margin_m <= noise and margin_h <= noise),
    "top5_overlap": len(set(top_m) & set(top_h)),
}
json.dump(
    result, open(os.path.join(root, "comparison.json"), "w"), indent=1, sort_keys=True
)
print(json.dumps(result, indent=1, sort_keys=True))
