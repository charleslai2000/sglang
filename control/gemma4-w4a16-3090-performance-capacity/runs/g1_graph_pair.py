#!/usr/bin/env python3
"""Small deterministic same-input eager-vs-real-decode-graph probe."""

import argparse, json, urllib.request, time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", required=True)
p.add_argument("--fixture", required=True)
p.add_argument("--output", required=True)
p.add_argument("--runs", type=int, default=2)
a = p.parse_args()
f = json.loads(Path(a.fixture).read_text())
ids = f["token_ids"]
out = []


def post(obj):
    req = urllib.request.Request(
        a.url + "/v1/completions",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.load(r)


for i in range(a.runs):
    # First request warms/captures the bs=1 graph. Returned output is retained for comparison too.
    obj = {
        "model": "gemma4",
        "prompt": ids,
        "max_tokens": 32,
        "temperature": 0,
        "top_p": 1,
        "logprobs": 1,
        "echo": True,
        "return_token_ids": True,
        "skip_special_tokens": False,
        "ignore_eos": True,
        "stop": [],
    }
    t = time.time()
    r = post(obj)["choices"][0]
    out.append(
        {
            "run": i,
            "elapsed_s": time.time() - t,
            "prompt_token_ids": r.get("prompt_token_ids"),
            "token_ids": r.get("token_ids"),
            "text": r.get("text"),
            "token_logprobs": (r.get("logprobs") or {}).get("token_logprobs"),
            "finish_reason": r.get("finish_reason"),
        }
    )
assert all(r["prompt_token_ids"] == ids for r in out)
Path(a.output).write_text(
    json.dumps(
        {
            "fixture": str(a.fixture),
            "n": len(ids),
            "fixture_sha256": f.get("fixture_sha256"),
            "runs": out,
        },
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        {
            "runs": len(out),
            "tokens": len(out[0]["token_ids"]),
            "identical_tokens": all(x["token_ids"] == out[0]["token_ids"] for x in out),
            "first_ids": out[0]["token_ids"][:8],
        }
    )
)
