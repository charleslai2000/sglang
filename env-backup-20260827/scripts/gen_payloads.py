#!/usr/bin/env python3
"""B0 block 2a payload generator (runs inside sglang-b0 container, /model tokenizer).

Constructs content-only payloads for the block-2a cases. Server prompt_tokens =
content_tokens + 52 (doc C content-only 122,334 -> server 122,386, offset +52,
confirmed by block 1). Construction method recorded per case.
"""
import json, os, random
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from transformers import AutoTokenizer

MODEL = "/model"
SERVED = "qwen3.8-27b-nvfp4-b0"
OUT = "/tmp/b2a-payloads"
os.makedirs(OUT, exist_ok=True)
tk = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
def enc(s): return len(tk.encode(s, add_special_tokens=False))

_VOCAB_STR = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu river mountain forest valley ocean desert island harbor "
    "clock tower bridge temple garden market library museum silver copper "
    "bronze crystal granite marble jade amber falcon osprey heron crane eagle "
    "raven swallow sparrow current voltage resistor capacitor inductor "
    "transistor quantum photon electron neutron proton atom molecule signal "
    "packet frame buffer queue stack heap cache orbit comet nebula galaxy "
    "planet asteroid meteor canvas palette sculpture fresco mosaic tapestry "
    "lighthouse beacon compass sextant anchor maple cedar birch willow poplar "
    "spruce arithmetic geometry algebra calculus topology sonnet ballad lyric "
    "hymn chant anthem emerald sapphire ruby topaz opal onyx vector matrix "
    "tensor gradient momentum filter kernel dilation stride pooling padding "
    "encoder decoder attention residual layer norm embedding projection"
)
VOCAB = sorted(set(_VOCAB_STR.split()))

def filler_base(seed, nwords=8000):
    rng = random.Random(seed)
    return " ".join(rng.choice(VOCAB) for _ in range(nwords))

def truncate_exact(text, n):
    """Char prefix of text ending exactly on a token boundary with count == n."""
    lo, hi = 0, len(text); best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if enc(text[:mid]) <= n:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    c = enc(text[:best])
    while c < n and best < len(text):
        best += 1; c = enc(text[:best])
    assert c == n, f"cannot hit {n}, got {c}"
    return text[:best]

def make_payload(text, max_tokens, logprobs=False):
    p = {"model": SERVED, "messages": [{"role": "user", "content": text}],
         "max_tokens": max_tokens, "temperature": 0.0, "stream": True,
         "stream_options": {"include_usage": True}}
    if logprobs:
        p["logprobs"] = True; p["top_logprobs"] = 1
    return p

# ---- sources ----
docC = json.load(open("/tmp/p3-cold.payload.json"))
content = docC["messages"][0]["content"]
assert enc(content) == 122334, f"docC content tokens {enc(content)} != 122334"
leg200 = json.load(open("/tmp/t5-leg200.json"))
leg200c = leg200["messages"][0]["content"]
assert enc(leg200c) == 200995, f"leg200 content tokens {enc(leg200c)} != 200995"

fb = filler_base(20260827)          # filler for boundary +N cases
fb_branch = filler_base(20260901)   # different seed -> different tail for branch

# ---- case texts (content-only) ----
# T+1  server 122,369 = content 122,317 = doc C truncated 17 tokens
t1 = truncate_exact(content, 122317)
# T+63 server 122,431 = content 122,379 = doc C + 45 filler
t63 = truncate_exact(content + "\n" + fb, 122379)
# T+255 server 122,623 = content 122,571 = doc C + 237 filler
t255 = truncate_exact(content + "\n" + fb, 122571)
# 200K = E1 leg200 (200,995 content / 201,047 server)
l200 = leg200c
# branch = doc C first 121,834 tokens + ~500 different filler tokens
branch_prefix = truncate_exact(content, 121834)
branch_filler = truncate_exact(fb_branch, 500)
branch = branch_prefix + "\n" + branch_filler
assert content.startswith(branch_prefix), "branch prefix must be a char prefix of doc C"

cases = [
    ("b2a-t1",     t1,     "doc C content truncated 17 tokens (content 122,317; server 122,369)"),
    ("b2a-t63",    t63,    "doc C + 45 filler tokens (content 122,379; server 122,431)"),
    ("b2a-t255",   t255,   "doc C + 237 filler tokens (content 122,571; server 122,623)"),
    ("b2a-l200",   l200,   "E1 leg200 payload t5-leg200.json (content 200,995; server 201,047)"),
    ("b2a-branch", branch, "doc C first 121,834 tokens + 500 different filler tokens (seed 20260901); shared prefix 121,834"),
]

print("case            content_tokens  server(=+52)  construction")
for name, txt, desc in cases:
    n = enc(txt)
    json.dump(make_payload(txt, 16), open(f"{OUT}/{name}-16.payload.json", "w"), ensure_ascii=False)
    json.dump(make_payload(txt, 256, logprobs=True), open(f"{OUT}/{name}-256lp.payload.json", "w"), ensure_ascii=False)
    print(f"{name:14} {n:>12}  {n+52:>12}  {desc}")

# sanity: branch shared prefix check
print("branch_prefix_tokens", enc(branch_prefix), "branch_filler_tokens", enc(branch_filler))
print("branch_total_content", enc(branch))
print("docC_content", enc(content))
print("DONE")
