#!/usr/bin/env python3
"""Verify payload content token counts with in-container tokenizer (read-only)."""
import json, os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from transformers import AutoTokenizer

tk = AutoTokenizer.from_pretrained("/model", trust_remote_code=True)
def enc(s): return len(tk.encode(s, add_special_tokens=False))

for name in ["b2a-t1", "b2a-t63", "b2a-t255", "b2a-l200", "b2a-branch"]:
    for probe in ["16", "256lp"]:
        p = json.load(open(f"/tmp/pl/{name}-{probe}.payload.json"))
        content = p["messages"][0]["content"]
        n = enc(content)
        print(f"{name}-{probe}: content_tokens={n} server(=+52)={n+52} max_tokens={p['max_tokens']} logprobs={p.get('logprobs')}")

# also the docC payload used in run_branch.sh (p3-cold)
p = json.load(open("/tmp/p3-cold.payload.json"))
content = p["messages"][0]["content"]
print(f"p3-cold (docC): content_tokens={enc(content)} server(=+52)={enc(content)+52} max_tokens={p['max_tokens']}")

# branch shared prefix math: branch content should start with docC first 121834 tokens
b = json.load(open("/tmp/pl/b2a-branch-16.payload.json"))["messages"][0]["content"]
d = p["messages"][0]["content"]
# count shared prefix length: tokenize docC, find how many branch tokens match docC from start
bt = tk.encode(b, add_special_tokens=False)
dt = tk.encode(d, add_special_tokens=False)
shared = 0
for x, y in zip(bt, dt):
    if x == y:
        shared += 1
    else:
        break
print(f"branch/docC shared prefix tokens: {shared} (expected 121834)")
print(f"branch total content tokens: {len(bt)}, docC total: {len(dt)}")
