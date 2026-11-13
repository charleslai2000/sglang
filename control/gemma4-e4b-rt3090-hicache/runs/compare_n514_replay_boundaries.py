#!/usr/bin/env python3
"""Compare exact-bound N514 layer17 service taps to pinned HF eager replay."""

import json
from pathlib import Path
import torch

ROOT = Path("/data/sglang-hicache/gemma4/runs")
SERVICE = ROOT / "20261022T172926Z-e5m2-swa-boundary"
COMPONENT_RUN = ROOT / "20261022T122000Z-n514-prefill-layer17-fully-bound"
FORWARD = "e154f270660c4b83a79dfbf467aa9d0a"
RID = "9fc02e7ae2d14f6cba14b48362a875dd"
COMPONENT_FORWARD = "3ce156045d6940e2a029dff12a864c43"
COMPONENT_RID = "d05856debcd94266b9abc95c692b101c"
HF_PATH = SERVICE / "hf-oracle/n514-layer17-components-exact-ple-v2.pt"

hf = torch.load(HF_PATH, weights_only=True)
manifest = json.loads((SERVICE / f"bf16/forward.{FORWARD}.manifest").read_text())
ple = torch.load(SERVICE / f"bf16/forward.{FORWARD}.ple.17", weights_only=True)
assert hf["forward_id"] == FORWARD and hf["rid"] == [RID]
assert manifest["forward_id"] == FORWARD and manifest["rid"] == [RID]
assert hf["input_ids"] == manifest["input_ids"] == ple["input_ids"].tolist()
assert hf["positions"] == manifest["positions"] == ple["positions"].tolist()
assert ple["forward_mode"] == "EXTEND" and ple["extend_seq_lens"].tolist() == [514]
assert ple["extend_prefix_lens"].tolist() == [0]
assert hf["ple_source"].startswith("exact captured SGLang Forward")

component_root = COMPONENT_RUN / "components"


def load_component(name):
    p = (
        component_root
        / f"component.{COMPONENT_RID}.{COMPONENT_FORWARD}.layer17.{name}.json"
    )
    record = json.loads(p.read_text())
    assert record["rid"] == COMPONENT_RID and record["forward_id"] == COMPONENT_FORWARD
    assert (
        record["forward_mode"] == "EXTEND"
        and record["step_input_ids"] == hf["input_ids"]
    )
    assert record["step_positions"] == hf["positions"]
    assert record["query_token_range_in_request"] == [0, 514]
    return torch.tensor(record["value"], dtype=torch.bfloat16)


def metrics(actual, reference):
    a, b = actual.float().cpu(), reference.float().cpu()
    if a.shape != b.shape:
        raise AssertionError(f"shape mismatch {tuple(a.shape)} vs {tuple(b.shape)}")
    d = a - b
    return {
        "shape": list(a.shape),
        "max_abs": d.abs().max().item(),
        "mean_abs": d.abs().mean().item(),
        "relative_l2": (d.norm() / b.norm()).item(),
    }


pairs = {
    "post_rope_q": (
        load_component("q"),
        hf["attention_q_after_rope"][0].transpose(0, 1),
    ),
    "post_rope_k": (
        load_component("k"),
        hf["attention_k_after_rope"][0].transpose(0, 1),
    ),
    "v": (load_component("v"), hf["attention_v"][0].transpose(0, 1)),
    "attention_heads": (
        load_component("attention_output"),
        hf["attention_output_heads"][0],
    ),
    "decoder_layer_output": (
        load_component("decoder_layer_output"),
        hf["decoder_layer_output"][0],
    ),
}
result = {
    "status": "MEASURED",
    "service_forward_id": FORWARD,
    "service_rid": RID,
    "component_forward_id": COMPONENT_FORWARD,
    "component_rid": COMPONENT_RID,
    "n": 514,
    "layer": 17,
    "positions": [1, 514],
    "model_identity": manifest["model_identity"],
    "hf_ple_source": hf["ple_source"],
    "comparisons": {k: metrics(*v) for k, v in pairs.items()},
    "limitations": [
        "HF replay uses official compressed-tensors decompression, not identical SGLang W4A16 accumulation.",
        "N514 decoder-layer parity does not explain whole-model N512/N514 logit drift.",
    ],
}
out = SERVICE / "hf-oracle/n514-layer17-exact-ple-comparison.json"
out.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
