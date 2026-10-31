#!/usr/bin/env python3
"""Run frozen GSM8K prompt set through current SGLang or vLLM in ordered waves."""

import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DATA = Path("/data/sglang-hicache/gemma4")
OLD_RUN = DATA / "runs/20261026T-gsm8k-g1-final-bos"
DATASET = DATA / "runs/gsm8k-prepare-20261026/data/test.jsonl"
MODEL = DATA / "model"
CHECKPOINT = {
    "revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
    "sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
}
STOP = ["Question:", "</s>", "<|im_end|>", "<eos>"]
MAX_TOKENS = 512
WAVE = int(os.environ.get("GSM8K_WAVE_SIZE", "16"))


def digest_ids(ids):
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


def score(text, target):
    # This task's normalization leaves a single parsed number; compare after comma removal.
    m = re.search(r"#### (-?[0-9.,]+)", text)
    pred = m.group(1) if m else "[invalid]"
    golds = re.findall(r"#### (-?[0-9.,]+)", target)
    gold = golds[-1] if golds else "[invalid]"
    # lm-eval 0.4.13 exact_match_hf_evaluate normalization for GSM8K.
    normalized_pred = pred.replace(",", "").replace("$", "")
    normalized_gold = gold.replace(",", "").replace("$", "")
    correct = normalized_pred.lower() == normalized_gold.lower()
    if normalized_pred.endswith(".") and normalized_pred[:-1].lower() == normalized_gold.lower():
        correct = True
    return {
        "prediction": pred,
        "reference": gold,
        "correct": correct,
        "has_question_stop": "Question:" in text,
    }


def build_fixture():
    # Reuse the existing frozen 1,319 prompts and targets; do not rebuild GSM8K.
    samples = {}
    p = OLD_RUN / "bf16/samples.jsonl"
    text = p.read_text()
    starts = [m.start() for m in re.finditer(r'(?m)^\{"doc_id": \d+, "doc":', text)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        r = json.loads(text[start:end].strip().replace("\\n", "\\n"))
        samples[str(r["doc_id"])] = r
    assert len(samples) == 1319, len(samples)
    # Verify exact correspondence with the pinned local test split, without redownloading it.
    test_rows = [json.loads(x) for x in DATASET.read_text().splitlines() if x.strip()]
    if len(samples) != len(test_rows) or any(samples[str(i)]["doc"] != d for i, d in enumerate(test_rows)):
        raise RuntimeError("reused prompts/targets do not match pinned local test split")
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    fixture = []
    for docid in sorted(samples, key=int):
        r = samples[docid]
        prompt = r["arguments"]["gen_args_0"]["arg_0"]
        # Historical GSM8K fixture explicitly prepends Gemma BOS=2; HF encode itself omits it.
        ids = [int(tok.bos_token_id)] + tok.encode(prompt, add_special_tokens=False)
        # The historical runner's saved prompt token IDs are reconstructable from its exact prompt.
        if not ids:
            raise RuntimeError(f"empty tokenization for doc {docid}")
        fixture.append(
            {
                "doc_id": int(docid),
                "prompt": prompt,
                "input_ids": ids,
                "prompt_sha256": digest_ids(ids),
                "target": r["doc"]["answer"],
                "historical_bf16_correct": bool(r["exact_match"]),
                "request_order": len(fixture),
            }
        )
    return fixture


def run_sglang(fixture, endpoint, outdir):
    rows = []
    for start in range(0, len(fixture), WAVE):
        wave = fixture[start : start + WAVE]

        def call(item):
            payload = {
                "prompt": item["input_ids"],
                "model": "gemma4",
                "max_tokens": MAX_TOKENS,
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 666360643,
                "ignore_eos": False,
                "skip_special_tokens": False,
                "stop": STOP,
                "return_token_ids": True,
                "no_stop_trim": False,
                "rid": f"gsm8k-wave-{item['doc_id']}",
            }
            resp = requests.post(endpoint, json=payload, timeout=1800)
            resp.raise_for_status()
            body = resp.json()
            c = body["choices"][0]
            echoed = c.get("prompt_token_ids") or []
            if echoed and echoed != item["input_ids"]:
                raise RuntimeError(f"prompt echo mismatch doc={item['doc_id']}")
            return item, body, c, payload

        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            futs = [pool.submit(call, x) for x in wave]
            completed = [f.result() for f in as_completed(futs)]
        by_doc = {int(x[0]["doc_id"]): x for x in completed}
        for item in wave:
            _, body, c, payload = by_doc[item["doc_id"]]
            text = c.get("text") or ""
            row = {
                "doc_id": item["doc_id"],
                "request_order": item["request_order"],
                "wave": start // WAVE,
                "rid": payload["rid"],
                "request_id": body.get("id"),
                "prompt_ids": item["input_ids"],
                "prompt_sha256": item["prompt_sha256"],
                "prompt_echo_match": (c.get("prompt_token_ids") or item["input_ids"])
                == item["input_ids"],
                "output_ids": c.get("token_ids") or [],
                "text": text,
                "finish_reason": c.get("finish_reason"),
                "matched_stop": c.get("matched_stop"),
                "target": item["target"],
                "historical_bf16_correct": item["historical_bf16_correct"],
                "score": score(text, item["target"]),
            }
            rows.append(row)
            with (outdir / "results.jsonl").open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"SGLang wave {start // WAVE + 1}/{(len(fixture) + WAVE - 1) // WAVE} done", flush=True)
    return rows


def run_vllm(fixture, outdir):
    import torch
    from vllm import LLM, SamplingParams
    from vllm.inputs import TokensPrompt

    llm = LLM(
        model=str(MODEL),
        dtype="bfloat16",
        tensor_parallel_size=1,
        gpu_memory_utilization=0.70,
        enforce_eager=True,
        trust_remote_code=True,
        disable_custom_all_reduce=True,
        enable_prefix_caching=False,
        enable_chunked_prefill=False,
        max_model_len=8193,
        max_num_seqs=WAVE,
        max_num_batched_tokens=16384,
        logprobs_mode="raw_logits",
    )
    params = SamplingParams(
        temperature=0,
        top_p=1,
        max_tokens=MAX_TOKENS,
        stop=STOP,
        include_stop_str_in_output=False,
        detokenize=True,
        seed=666360643,
    )
    rows = []
    for start in range(0, len(fixture), WAVE):
        wave = fixture[start : start + WAVE]
        prompts = [TokensPrompt(prompt_token_ids=x["input_ids"]) for x in wave]
        outputs = llm.generate(prompts, params, use_tqdm=False)
        outputs.sort(key=lambda o: int(o.request_id))
        if len(outputs) != len(wave):
            raise RuntimeError("vLLM output count mismatch")
        for j, (item, o) in enumerate(zip(wave, outputs, strict=True)):
            expected_reqid = str(start + j)
            if o.request_id != expected_reqid:
                raise RuntimeError(
                    f"vLLM order mismatch: {o.request_id} != {expected_reqid}"
                )
            if list(o.prompt_token_ids or []) != item["input_ids"]:
                raise RuntimeError(f"vLLM prompt ID mismatch {item['doc_id']}")
            c = o.outputs[0]
            text = c.text or ""
            row = {
                "doc_id": item["doc_id"],
                "request_order": item["request_order"],
                "wave": start // WAVE,
                "request_id": o.request_id,
                "prompt_ids": list(o.prompt_token_ids),
                "prompt_sha256": item["prompt_sha256"],
                "prompt_echo_match": True,
                "output_ids": list(c.token_ids),
                "text": text,
                "finish_reason": c.finish_reason,
                "matched_stop": str(c.stop_reason)
                if c.stop_reason is not None
                else None,
                "target": item["target"],
                "historical_bf16_correct": item["historical_bf16_correct"],
                "score": score(text, item["target"]),
            }
            rows.append(row)
            with (outdir / "results.jsonl").open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"vLLM wave {start // WAVE + 1}/{(len(fixture) + WAVE - 1) // WAVE} done", flush=True)
    del llm
    torch.cuda.synchronize()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["sglang", "vllm"], required=True)
    ap.add_argument("--endpoint", default="http://127.0.0.1:31239/v1/completions")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    allowed_bootstrap = {"server.log", "server.pid", "identity.json", "frozen-prompts.jsonl", "manifest.json"}
    unexpected = [p.name for p in outdir.iterdir() if p.name not in allowed_bootstrap]
    if unexpected:
        raise FileExistsError(f"output directory has prior results: {unexpected}")
    fixture = build_fixture()
    fixture_path = outdir / "frozen-prompts.jsonl"
    fixture_path.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fixture)
    )
    manifest = {
        "engine": a.engine,
        "model": str(MODEL),
        "checkpoint": CHECKPOINT,
        "fixture_count": len(fixture),
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "source_sha": os.environ.get("G1_SOURCE_SHA", "unknown"),
        "stop": STOP,
        "max_tokens": MAX_TOKENS,
        "greedy": True,
        "wave_size": WAVE,
        "order": "numeric doc_id, request_order frozen; concurrent SGLang POST waves / vLLM generate waves",
        "environment": {
            k: os.environ.get(k)
            for k in ["PYTHONPATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES"]
        },
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = (
        run_sglang(fixture, a.endpoint, outdir)
        if a.engine == "sglang"
        else run_vllm(fixture, outdir)
    )
    assert len(rows) == 1319 and len({x["doc_id"] for x in rows}) == 1319
    summary = {
        "n": len(rows),
        "correct": sum(x["score"]["correct"] for x in rows),
        "accuracy": sum(x["score"]["correct"] for x in rows) / len(rows),
        "prompt_ids_verified": all(x["prompt_echo_match"] for x in rows),
        "rows": len(rows),
        "finish_reasons": {},
    }
    for row in rows:
        summary["finish_reasons"][str(row["finish_reason"])] = (
            summary["finish_reasons"].get(str(row["finish_reason"]), 0) + 1
        )
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
