"""Run bounded fixed-prompt production capture and full-vocab API logprob closure."""

import json, requests
from pathlib import Path

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
rows = [
    x
    for x in map(json.loads, (D / "prompts.jsonl").open())
    if x["doc_id"] in {3, 24, 70}
]
for x in rows:
    doc = x["doc_id"]
    req = {
        "input_ids": x["prompt_token_ids"],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1.0,
            "top_k": 1,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "repetition_penalty": 1.0,
            "max_new_tokens": 1,
            "stop": ["Question:", "</s>", "<|im_end|>"],
            "sampling_seed": 1234,
        },
        "return_logprob": False,
        "rid": f"g2-closure-{doc}",
    }
    r = requests.post("http://127.0.0.1:31223/generate", json=req, timeout=3600)
    r.raise_for_status()
    (D / f"closure3-api-{doc}.json").write_text(
        json.dumps(
            {
                "prompt_ids_sha256": x["prompt_ids_sha256"],
                "request": req,
                "response": r.json(),
            },
            separators=(",", ":"),
        )
    )
    print(
        doc, r.json()["output_ids"], r.json()["meta_info"]["prompt_tokens"], flush=True
    )
