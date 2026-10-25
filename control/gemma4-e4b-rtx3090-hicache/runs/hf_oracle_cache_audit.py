#!/usr/bin/env python3
"""Audit pinned HF Gemma4 QAT cache modes and CPU/CUDA eager semantics."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, __version__ as transformers_version

DATA = Path("/data/sglang-hicache/gemma4")
BASE = DATA / "runs/20261022T065916Z-e5m2-swa-boundary"
MODEL = DATA / "model"


def metrics(ref, got):
    a, b = ref.float().reshape(-1), got.float().reshape(-1)
    d = b - a
    ta, tb = torch.topk(a, 10).indices, torch.topk(b, 10).indices
    return {
        "rel_l2": (d.norm() / a.norm()).item(),
        "max_abs": d.abs().max().item(),
        "mean_abs": d.abs().mean().item(),
        "top10_exact": torch.equal(ta, tb),
        "top10_ref": ta.tolist(),
        "top10_got": tb.tolist(),
        "greedy_ref": int(a.argmax()),
        "greedy_got": int(b.argmax()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    args = parser.parse_args()
    device = args.device
    torch.set_num_threads(8)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        torch_dtype="auto",
        device_map=device,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        attn_implementation="eager",
    ).eval()
    text_model = (
        model.model.language_model
        if hasattr(model.model, "language_model")
        else model.model
    )
    checkpoint_sha = subprocess.check_output(
        ["sha256sum", str(MODEL / "model.safetensors")], text=True
    ).split()[0]
    qconfig = model.config.quantization_config
    records = {
        "env": {
            "transformers": transformers_version,
            "torch": torch.__version__,
            "device": device,
            "device_name": torch.cuda.get_device_name(0)
            if device == "cuda"
            else os.uname().machine,
            "attn_implementation": text_model.config._attn_implementation,
            "parameter_dtype": str(next(model.parameters()).dtype),
            "quantization_run_compressed": getattr(qconfig, "run_compressed", None),
            "quantization_status": str(getattr(qconfig, "quantization_status", None)),
            "quantization_format": getattr(qconfig, "format", None),
            "checkpoint_sha256": checkpoint_sha,
            "quantization_config_sha256": hashlib.sha256(
                json.dumps(
                    model.config.quantization_config, sort_keys=True, default=str
                ).encode()
            ).hexdigest(),
        },
        "sequences": {},
    }
    for n in (512, 514):
        req = json.loads((BASE / f"n{n}/bf16-request.json").read_text())
        ids = req["prompt"]
        assert len(ids) == n
        old = torch.load(
            BASE / f"oracle-n{n}.pt", map_location="cpu", weights_only=False
        )
        ref = old["logits"].float().reshape(-1)
        x = torch.tensor([ids], device=device)
        positions = torch.arange(1, n + 1, device=device).unsqueeze(0)
        seq = {
            "input_ids_sha256": hashlib.sha256(
                json.dumps(ids, separators=(",", ":")).encode()
            ).hexdigest(),
            "positions": [1, n],
            "old_oracle_ids_sha256": old["input_ids_sha256"],
            "old_oracle_positions": old["positions"],
            "old_oracle_provenance": old.get("source", "no source field"),
            "runs": {},
        }
        for use_cache in (False, True):
            with torch.inference_mode():
                out = model(
                    input_ids=x,
                    position_ids=positions,
                    use_cache=use_cache,
                    return_dict=True,
                    logits_to_keep=1,
                    return_shared_kv_states=True,
                )
            logits = out.logits[0, -1].detach().float().cpu()
            shared = out.shared_kv_states
            seq["runs"][str(use_cache)] = {
                "cache_present": out.past_key_values is not None,
                "shared_keys": list(shared.keys()) if shared is not None else None,
                "shared_tensor_shapes": {
                    k: [list(t.shape) for t in v] for k, v in shared.items()
                }
                if shared
                else None,
                "logits": logits,
            }
        cache_off = seq["runs"]["False"]["logits"]
        cache_on = seq["runs"]["True"]["logits"]
        seq["cache_true_vs_false"] = metrics(cache_off, cache_on)
        seq["cache_false_vs_old_oracle"] = metrics(ref, cache_off)
        seq["cache_true_vs_old_oracle"] = metrics(ref, cache_on)
        records["sequences"][str(n)] = seq
        print(
            json.dumps(
                {
                    k: seq[k]
                    for k in (
                        "input_ids_sha256",
                        "old_oracle_ids_sha256",
                        "old_oracle_positions",
                        "cache_true_vs_false",
                        "cache_false_vs_old_oracle",
                        "cache_true_vs_old_oracle",
                    )
                }
            ),
            flush=True,
        )
    torch.save(records, args.out)


if __name__ == "__main__":
    main()
