#!/usr/bin/env python3
"""Stream 32 independent long-context completions and retain server evidence."""

from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, random, threading, time, urllib.request
from pathlib import Path


def stream_one(
    base: str,
    rid: str,
    ids: list[int],
    max_new: int,
    barrier: threading.Barrier,
    out: Path,
) -> dict:
    body = {
        "input_ids": ids,
        "sampling_params": {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "max_new_tokens": max_new,
            "min_new_tokens": max_new,
            "ignore_eos": True,
            "sampling_seed": 101,
        },
        "stream": True,
        "return_token_ids": True,
        "rid": rid,
    }
    req = urllib.request.Request(
        base + "/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    barrier.wait()
    start = time.perf_counter()
    first = None
    chunks = 0
    text_bytes = 0
    with urllib.request.urlopen(req, timeout=3600) as response, out.open("w") as sink:
        for raw in response:
            if not raw.strip() or raw.startswith(b":"):
                continue
            if raw.startswith(b"data:"):
                payload = raw[5:].strip()
                if payload == b"[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if first is None:
                    first = time.perf_counter()
                chunks += 1
                text_bytes += len(payload)
                sink.write(json.dumps(obj) + "\n")
    end = time.perf_counter()
    return {
        "rid": rid,
        "prompt_tokens": len(ids),
        "stream_chunks": chunks,
        "first_chunk_s": first - start if first else None,
        "request_wall_s": end - start,
        "response_payload_bytes": text_bytes,
        "stream_path": str(out),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--requests", type=int, default=32)
    ap.add_argument("--context", type=int, default=32768)
    ap.add_argument("--decode-tokens", type=int, default=256)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--mode", choices=("staggered", "barrier"), default="barrier")
    ap.add_argument("--prefill-timeout", type=int, default=3600)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(args.seed)
    # Distinct IDs per request, no shared text/prefix. Independent uniform token sequences.
    prompts = [
        [rng.randrange(1, 260000) for _ in range(args.context)]
        for _ in range(args.requests)
    ]
    (args.out / "fixture.json").write_text(
        json.dumps(
            {
                "seed": args.seed,
                "requests": args.requests,
                "context_tokens": args.context,
                "decode_tokens": args.decode_tokens,
                "mode": args.mode,
                "num_unique_prompt_hashes": len(
                    {
                        hashlib.sha256(
                            json.dumps(x, separators=(",", ":")).encode()
                        ).hexdigest()
                        for x in prompts
                    }
                ),
                "prompt_ids_sha256": [
                    hashlib.sha256(
                        json.dumps(x, separators=(",", ":")).encode()
                    ).hexdigest()
                    for x in prompts
                ],
            },
            indent=2,
        )
        + "\n"
    )
    gate = threading.Barrier(args.requests + 1)
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.requests) as ex:
        futures = []
        for i, ids in enumerate(prompts):
            # A separate context file avoids retaining all token arrays in result artifacts.
            futures.append(
                ex.submit(
                    stream_one,
                    args.url,
                    f"g2-longctx-{args.requests}x{args.context}-r{i:02d}",
                    ids,
                    args.decode_tokens,
                    gate,
                    args.out / f"stream-{i:02d}.jsonl",
                )
            )
        gate.wait()
        rows = []
        for f in concurrent.futures.as_completed(futures):
            rows.append(f.result())
    end = time.perf_counter()
    rows.sort(key=lambda r: r["rid"])
    result = {
        "requests": args.requests,
        "context_tokens_each": args.context,
        "decode_tokens_each": args.decode_tokens,
        "mode": args.mode,
        "prefill_timeout_s": args.prefill_timeout,
        "wall_s": end - start,
        "completed": len(rows),
        "rows": rows,
        "all_streamed": all(r["stream_chunks"] > 0 for r in rows),
    }
    result["streamed_output_tokens"] = sum(row["stream_chunks"] for row in rows)
    (args.out / "client-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2),
        flush=True,
    )


if __name__ == "__main__":
    main()
