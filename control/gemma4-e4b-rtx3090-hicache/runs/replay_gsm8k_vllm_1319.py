#!/usr/bin/env python3
"""Matched full GSM8K replay from saved SGLang prompts via raw vLLM token IDs."""

import fcntl
import hashlib
import json
import re
from pathlib import Path

import torch
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from vllm.inputs import TokensPrompt

RUN = Path("/data/sglang-hicache/gemma4/runs")
SGLANG = RUN / "20261026T-gsm8k-g1-final-bos"
OLD = RUN / "20261026T-gsm8k-g1-final"
DATA = RUN / "gsm8k-prepare-20261026/data"
OUT = RUN / "20261026T-gsm8k-vllm-full-matched-r6"
MODEL = "/data/sglang-hicache/gemma4/model"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"
START = re.compile(r'(?m)^\{"doc_id": \d+, "doc":')


def read_samples(path):
    text = path.read_text()
    matches = list(START.finditer(text))
    rows = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        rows.append(json.loads(text[m.start() : end].strip().replace("\n", "\\n")))
    result = {int(row["doc_id"]): row for row in rows}
    if len(result) != 1319 or set(result) != set(range(1319)):
        raise RuntimeError(f"expected doc_ids 0..1318, got {len(result)} rows")
    return result


def main():
    bf = read_samples(SGLANG / "bf16/samples.jsonl")
    e5 = read_samples(SGLANG / "e5m2/samples.jsonl")
    old = read_samples(OLD / "bf16/samples.jsonl")
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    test = [json.loads(line) for line in (DATA / "test.jsonl").open() if line.strip()]
    if len(test) != 1319:
        raise RuntimeError(f"expected 1319 test docs, got {len(test)}")
    prompts = []
    prompt_rows = []
    for i in range(1319):
        row = bf[i]
        prompt = row["arguments"]["gen_args_0"]["arg_0"]
        if (
            row["doc"] != test[i]
            or e5[i]["doc"] != row["doc"]
            or old[i]["doc"] != row["doc"]
        ):
            raise RuntimeError(f"dataset/document mismatch at doc_id={i}")
        if hashlib.sha256(prompt.encode()).hexdigest() != row["prompt_hash"]:
            raise RuntimeError(f"prompt text/hash mismatch at doc_id={i}")
        ids = tok.encode(prompt, add_special_tokens=True)
        # The SGLang adapter uses tokenizer.encode(add_special_tokens=True) then
        # the Completion endpoint prepends BOS. Verify this reconstructed wire input.
        expected = [tok.bos_token_id, *ids]
        if expected[0] != 2 or bf[i]["doc_id"] != i:
            raise RuntimeError(f"unexpected BOS or row identity at doc_id={i}")
        prompts.append(TokensPrompt(prompt_token_ids=expected))
        prompt_rows.append(
            {
                "doc_id": i,
                "prompt_sha256": row["prompt_hash"],
                "prompt_token_ids": expected,
                "prompt_ids_sha256": hashlib.sha256(
                    json.dumps(expected, separators=(",", ":")).encode()
                ).hexdigest(),
                "prompt_len": len(expected),
            }
        )
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / "expected-prompts.jsonl").write_text(
        "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in prompt_rows)
    )
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        llm = LLM(
            model=MODEL,
            dtype="bfloat16",
            tensor_parallel_size=1,
            gpu_memory_utilization=0.70,
            enforce_eager=True,
            trust_remote_code=True,
            disable_custom_all_reduce=True,
            enable_prefix_caching=False,
            enable_chunked_prefill=False,
            max_model_len=8193,
            max_num_seqs=16,
            max_num_batched_tokens=16384,
            logprobs_mode="raw_logits",
        )
        params = SamplingParams(
            temperature=0,
            top_p=1,
            max_tokens=512,
            stop=["Question:", "</s>", "<|im_end|>", "<eos>"],
            include_stop_str_in_output=False,
            skip_special_tokens=False,
            spaces_between_special_tokens=False,
            detokenize=True,
        )
        outputs = llm.generate(prompts, params, use_tqdm=True)
        if len(outputs) != 1319:
            raise RuntimeError(f"vLLM returned {len(outputs)} outputs")
        outputs.sort(key=lambda out: int(out.request_id))
        rows = []
        for i, out in enumerate(outputs):
            expected = prompt_rows[i]["prompt_token_ids"]
            actual = list(out.prompt_token_ids or [])
            if out.request_id != str(i) or actual != expected:
                raise RuntimeError(
                    f"request {i}: worker response prompt identity mismatch"
                )
            c = out.outputs[0]
            rows.append(
                {
                    "doc_id": i,
                    "request_id": out.request_id,
                    "prompt_ids": actual,
                    "prompt_identity_match": True,
                    "prompt_sha256": prompt_rows[i]["prompt_sha256"],
                    "output_ids": c.token_ids,
                    "text": c.text,
                    "finish_reason": c.finish_reason,
                    "stop_reason": c.stop_reason,
                    "completion_len": len(c.token_ids),
                }
            )
        (OUT / "results.jsonl").write_text(
            "".join(
                json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
                for r in rows
            )
        )
        manifest = {
            "count": len(rows),
            "dataset": "gsm8k main test",
            "fixture_prompt_source": str(SGLANG / "bf16/samples.jsonl"),
            "dataset_test_sha256": "752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac",
            "checkpoint_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
            "checkpoint_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
            "tokenizer": str(tok.name_or_path),
            "input_ids": "reconstructed from exact saved SGLang per-doc prompt, tokenizer.encode(add_special_tokens=True), then BOS 2; response.prompt_token_ids checked exactly",
            "vllm_version": "0.32.1rc1.dev326+gc722f3a53",
            "dtype": "bfloat16",
            "kv_cache_dtype": "auto (runtime BF16)",
            "attention": "Triton; Marlin W4A16; eager",
            "max_model_len": 8193,
            "max_num_seqs": 16,
            "max_num_batched_tokens": 16384,
            "sampling": repr(params),
            "worker_prompt_ids_response_verified": True,
            "worker_capture_requested": True,
            "worker_capture_present": False,
            "identity_evidence": "all response prompt_token_ids equal the corresponding expected prompt IDs; no worker-capture artifact was produced",
            "output_order": "numeric request_id",
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        del llm
        torch.cuda.synchronize()


if __name__ == "__main__":
    main()
