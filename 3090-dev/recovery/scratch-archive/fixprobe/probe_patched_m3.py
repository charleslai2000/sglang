"""Greedy repro probes against the patched M3 server; mirrors the smoke step 2."""
import json, sys, time, urllib.request

BASE = "http://127.0.0.1:30164"
PROBES = [
    ("capital", "The capital of France is"),
    ("arithmetic", "Question: What is 17 times 3? Answer with only the number.\nAnswer:"),
    ("echo", 'Repeat exactly: "hello world"'),
]

def post(path, payload, timeout=300):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())

def wait_ready(deadline_s=900):
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            with urllib.request.urlopen(BASE + "/health_generate", timeout=10) as r:
                if r.status == 200:
                    return time.time() - t0
        except Exception:
            pass
        time.sleep(10)
    return None

def main():
    up = wait_ready()
    if up is None:
        print("SERVER NEVER READY"); sys.exit(2)
    print(f"server ready after {up:.0f}s")
    out = {}
    for tag, prompt in PROBES:
        payload = {"text": prompt, "sampling_params": {"temperature": 0, "max_new_tokens": 32},
                   "return_logprob": True, "logprob_start_len": 0, "top_logprobs_num": 5}
        st, body = post("/generate", payload)
        txt = body.get("text")
        lp = body.get("meta_info", {}).get("output_token_logprobs") or []
        ids = [x[1] for x in lp]
        print(f"[{tag}] http={st}")
        print(f"  text={txt!r}")
        print(f"  ids={ids}")
        print(f"  first_logprob={lp[0][0] if lp else None}")
        out[tag] = {"http": st, "prompt": prompt, "text": txt, "ids": ids,
                    "output_token_logprobs": lp}
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    print("wrote", sys.argv[1])

main()
