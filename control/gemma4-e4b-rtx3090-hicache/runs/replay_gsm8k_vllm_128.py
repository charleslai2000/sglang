#!/usr/bin/env python3
"""Replay the frozen GSM8K fixture through vLLM's raw TokensPrompt path."""

import fcntl
import hashlib
import json
from pathlib import Path

import torch
from vllm import LLM, SamplingParams
from vllm.inputs import TokensPrompt

RUN = Path("/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun")
FIXTURE = RUN / "fixture-128.json"
OUT = RUN / "vllm-128-numeric-rid-verified"
MODEL = "/data/sglang-hicache/gemma4/model"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"


def main():
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fixture_bytes = FIXTURE.read_bytes()
        fixture = json.loads(fixture_bytes)
        if len(fixture) != 128:
            raise RuntimeError(f"expected 128 fixed prompts, got {len(fixture)}")
        OUT.mkdir(parents=True, exist_ok=False)
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
            max_model_len=2048,
            max_num_seqs=16,
            max_num_batched_tokens=2048,
            logprobs_mode="raw_logits",
        )
        params = SamplingParams(
            temperature=0,
            top_p=1,
            max_tokens=512,
            stop=["Question:", "</s>", "<|im_end|>"],
            include_stop_str_in_output=True,
            detokenize=True,
        )
        doc_ids = list(fixture)
        prompt_inputs = [
            TokensPrompt(prompt_token_ids=fixture[doc_id]["input_ids"])
            for doc_id in doc_ids
        ]
        outputs = llm.generate(prompt_inputs, params, use_tqdm=False)
        if len(outputs) != 128:
            raise RuntimeError(f"vLLM returned {len(outputs)} outputs")
        # The offline API sorts numeric request IDs lexicographically; restore the
        # original input order by numeric request_id before binding output to doc.
        outputs.sort(key=lambda out: int(out.request_id))
        rows = []
        for index, (doc_id, output) in enumerate(zip(doc_ids, outputs, strict=True)):
            expected_ids = fixture[doc_id]["input_ids"]
            actual_ids = list(output.prompt_token_ids or [])
            if output.request_id != str(index):
                raise RuntimeError(
                    f"input index {index} got unexpected request_id {output.request_id}"
                )
            if actual_ids != expected_ids:
                raise RuntimeError(
                    f"request {index} / doc {doc_id}: prompt token identity mismatch "
                    f"({len(actual_ids)} vs {len(expected_ids)})"
                )
            c = output.outputs[0]
            rows.append(
                {
                    "input_index": index,
                    "doc_id": doc_id,
                    "group": fixture[doc_id]["group"],
                    "request_id": output.request_id,
                    "prompt_ids": actual_ids,
                    "prompt_identity_match": True,
                    "prompt_sha256": hashlib.sha256(
                        json.dumps(actual_ids, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "output_ids": c.token_ids,
                    "text": c.text,
                    "finish_reason": c.finish_reason,
                    "stop_reason": c.stop_reason,
                    "prompt_len": len(actual_ids),
                    "completion_len": len(c.token_ids),
                }
            )
        (OUT / "results.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
        )
        (OUT / "manifest.json").write_text(
            json.dumps(
                {
                    "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
                    "model": MODEL,
                    "checkpoint_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
                    "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
                    "dtype": "bfloat16",
                    "kv_cache_dtype": "auto (runtime BF16)",
                    "vllm_version": "0.32.1rc1.dev326+gc722f3a53",
                    "params": repr(params),
                    "request_mode": "one batched LLM.generate, max_num_seqs=16",
                    "identity": "response prompt_token_ids checked against each fixture entry; fail-closed",
                    "output_order": "numeric request_id, restoring original input order",
                    "requests": len(rows),
                },
                indent=2,
            )
            + "\n"
        )
        del llm
        torch.cuda.synchronize()


if __name__ == "__main__":
    main()
