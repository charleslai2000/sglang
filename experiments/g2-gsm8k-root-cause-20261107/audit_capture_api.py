"""Audit same-request SGLang logits captures against API output logprobs."""

import json
from pathlib import Path
import numpy as np
import torch

ROOT = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
for doc in (3, 24, 70):
    record = json.load((ROOT / f"toplogprobs-{doc}-correct.json").open())
    request, response = record["request"], record["response"]
    prompt, rid = request["input_ids"], request["rid"]
    capture = None
    cap_path = None
    for candidate in ROOT.glob("sglang-full-logits.*.logits"):
        x = torch.load(candidate, map_location="cpu", weights_only=False)
        if (
            x.get("rid") == [rid]
            and x.get("input_ids") is not None
            and x["input_ids"].tolist() == prompt
        ):
            capture, cap_path = x, candidate
            break
    if capture is None:
        raise RuntimeError(f"No same-request logits capture for {rid}")
    logits = capture["output"][0].double().numpy()
    # output_top_logprobs contains all (logprob, token_id, text) entries for the generated token.
    values = response["meta_info"]["output_top_logprobs"][0]
    api_ids = np.array([item[1] for item in values])
    api_values = np.array([item[0] for item in values])
    assert len(api_ids) == len(logits) and len(np.unique(api_ids)) == len(logits)
    api_lp = np.empty(len(logits))
    api_lp[api_ids] = api_values
    calc_lp = logits - np.logaddexp.reduce(logits)
    err = np.abs(calc_lp - api_lp)
    print(
        json.dumps(
            {
                "doc": doc,
                "rid": rid,
                "forward_id": capture["forward_id"],
                "capture": str(cap_path),
                "top_capture": int(logits.argmax()),
                "top_api": int(api_ids[api_values.argmax()]),
                "max_abs_lp_error": float(err.max()),
                "mean_abs_lp_error": float(err.mean()),
                "rmse": float(np.sqrt(np.mean(err**2))),
                "p99": float(np.quantile(err, 0.99)),
            }
        )
    )
