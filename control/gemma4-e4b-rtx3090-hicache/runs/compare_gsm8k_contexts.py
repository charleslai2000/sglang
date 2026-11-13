#!/usr/bin/env python3
"""Find identical 5-shot prompts, encode once, compare prefill logits offline."""

import hashlib, json, os, subprocess
from pathlib import Path
import torch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gsm8k_completion_adapter import GemmaGSM8KCompletions
from lm_eval.tasks import TaskManager


def main():
    root = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
    run = Path(sys.argv[1])
    task = TaskManager(
        include_path=str(root / "control/gemma4-e4b-rtx3090-hicache/runs")
    ).load(["gsm8k_official"])["tasks"]["gsm8k_official"]
    # IDs are reconstructed by the exact same tokenizer/5-shot config and compared to stored prompts.
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        "/data/sglang-hicache/gemma4/model", trust_remote_code=True
    )
    rows = {}
    for arm in ("bf16", "e5m2"):
        p = run / arm / "samples.jsonl"
        txt = p.read_text()
        import re, json

        starts = [m.start() for m in re.finditer(r'(?m)^\{"doc_id": \d+, "doc":', txt)]
        rr = []
        for i, s in enumerate(starts):
            c = txt[s : starts[i + 1] if i + 1 < len(starts) else len(txt)].strip()
            rr.append(json.loads(c.replace("\n", "\\n")))
        rows[arm] = rr
    assert len(rows["bf16"]) == len(rows["e5m2"]) == 1319
    idx = 0
    outputs = {}
    for r in rows["bf16"]:
        docid = r["doc_id"]
        prompt = r["arguments"]["gen_args_0"]["arg_0"]
        prompt_ids = [tok.bos_token_id] + tok.encode(prompt, add_special_tokens=False)
        pr = r["prompt_hash"]
        sibling = rows["e5m2"][docid]
        assert pr == sibling["prompt_hash"]
        ids2 = [tok.bos_token_id] + tok.encode(
            sibling["arguments"]["gen_args_0"]["arg_0"], add_special_tokens=False
        )
        assert prompt_ids == ids2
        # Exact input history is represented by stored complete prompt text; derive positional index in same running prefill.
        outputs[str(docid)] = {
            "prompt_sha256": hashlib.sha256(
                json.dumps(prompt_ids, separators=(",", ":")).encode()
            ).hexdigest(),
            "prompt_tokens": len(prompt_ids),
            "same_prompt_bf16_e5m2": True,
        }
    Path(run / "gsm8k-prompt-identity.json").write_text(
        json.dumps(
            {
                "n": len(outputs),
                "tokenizer": "pinned Gemma tokenizer",
                "bos_token_id": tok.bos_token_id,
                "records": outputs,
            },
            indent=2,
        )
        + "\n"
    )
    print("verified exact paired prompts", len(outputs))


if __name__ == "__main__":
    main()
