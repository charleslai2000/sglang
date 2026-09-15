#!/usr/bin/env python3
"""E-C1 single-stream decode probe (Qwen3.5-4B W4A16/Marlin, RTX 3090).

No HiCache, no Ready Horizon. One ~128-token prompt, max_tokens=1024,
stream=True, C1. Answers: what is the fundamental single-stream decode rate?

Emits one JSON row per repeat, a summary line, and (optionally) writes
--out with everything. Uses only /v1/tokenize and /v1/completions.
"""
import argparse
import json
import statistics
import time
import urllib.request


def _post_json(url, obj, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def tokenize(base, model, text, timeout):
    try:
        d = _post_json(base + "/v1/tokenize",
                       {"model": model, "text": text}, timeout)
        for k in ("count", "num_tokens"):
            if isinstance(d.get(k), int):
                return d[k]
        for k in ("tokens", "input_ids"):
            if isinstance(d.get(k), list):
                return len(d[k])
        return None
    except Exception:
        return None


WORDS = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam "
    "quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
    "consequat duis aute irure in reprehenderit voluptate velit esse cillum "
    "eu fugiat nulla pariatur excepteur sint occaecat cupidatat non proident "
    "sunt culpa qui officia deserunt mollit anim id est laborum"
).split()


def make_prompt(n_words, nonce):
    return "[%s] " % nonce + " ".join(
        WORDS[i % len(WORDS)] for i in range(n_words))


def _pct(v, q):
    if not v:
        return None
    s = sorted(v)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def run_one(base, model, prompt, max_tokens, timeout):
    payload = {
        "model": model, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0.0, "stream": True,
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        base + "/v1/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = last = None
    n_chunks = 0
    usage = None
    gaps = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            now = time.monotonic()
            if obj.get("usage"):
                usage = obj["usage"]
            ch = obj.get("choices") or []
            if ch and (ch[0].get("text") or ""):
                if first is None:
                    first = now
                else:
                    gaps.append(now - last)
                last = now
                n_chunks += 1
    t1 = time.monotonic()
    ct = (usage or {}).get("completion_tokens")
    n_tok = ct if isinstance(ct, int) and ct > 0 else n_chunks
    decode_s = (last - first) if (first is not None and last is not None) else None
    return {
        "ttft_s": (first - t0) if first is not None else None,
        "total_s": t1 - t0,
        "decode_window_s": decode_s,
        "output_tokens": n_tok,
        "completion_tokens_usage": ct,
        "n_chunks": n_chunks,
        "decode_tps": ((n_tok - 1) / decode_s) if decode_s and decode_s > 0 else None,
        "inter_token_ms_p50": (_pct(gaps, .5) * 1000) if gaps else None,
        "inter_token_ms_p95": (_pct(gaps, .95) * 1000) if gaps else None,
    }


def main():
    ap = argparse.ArgumentParser(description="E-C1 single-stream decode probe")
    ap.add_argument("--base", default="http://127.0.0.1:30000")
    ap.add_argument("--model", default="/mnt/data/models/qwen35-gptq")
    ap.add_argument("--words", type=int, default=100)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--nonce", default="ec1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ptok = tokenize(args.base, args.model, make_prompt(args.words, args.nonce),
                    args.timeout)
    rows = []
    for i in range(args.repeats):
        r = run_one(args.base, args.model,
                    make_prompt(args.words, "%s-r%d" % (args.nonce, i)),
                    args.max_tokens, args.timeout)
        r["repeat"] = i
        rows.append(r)
        print(json.dumps(r), flush=True)

    tps = [r["decode_tps"] for r in rows if r["decode_tps"]]
    ttft = [r["ttft_s"] for r in rows if r["ttft_s"]]
    out = {
        "prompt_tokens_measured": ptok,
        "prompt_words": args.words,
        "max_tokens": args.max_tokens,
        "repeats": args.repeats,
        "rows": rows,
        "decode_tps_p50": statistics.median(tps) if tps else None,
        "decode_tps_mean": statistics.mean(tps) if tps else None,
        "ttft_s_p50": statistics.median(ttft) if ttft else None,
    }
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=1)
    print("EC1_SUMMARY", json.dumps({
        "prompt_tokens_measured": out["prompt_tokens_measured"],
        "decode_tps_p50": out["decode_tps_p50"],
        "decode_tps_mean": out["decode_tps_mean"],
        "ttft_s_p50": out["ttft_s_p50"],
    }))


if __name__ == "__main__":
    main()
