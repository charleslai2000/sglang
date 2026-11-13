#!/usr/bin/env python3
"""Fail-closed same-Forward N514 comparison of SGLang component taps to HF replay."""

import json, sys
from pathlib import Path
import torch

run = Path(sys.argv[1])
expected_sha = "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"
manifests = [json.loads(p.read_text()) for p in run.glob("forward.*.manifest")]
ids = json.loads((run / "request.json").read_text())["input_ids"]
selected = [
    m
    for m in manifests
    if m.get("input_ids") == ids
    and m.get("forward_mode") == "EXTEND"
    and m.get("status") == "COMPLETE"
]
if len(selected) != 1:
    raise RuntimeError(f"expected one exact N514 EXTEND Forward; found {len(selected)}")
m = selected[0]
fid = m["forward_id"]
rid = m["rid"][0]
if m["model_identity"].get("model_sha256") != expected_sha:
    raise RuntimeError("model SHA mismatch")
hf = torch.load(run / "hf-layer17.pt", weights_only=True)
if (
    hf["forward_id"] != fid
    or hf["rid"] != [rid]
    or hf["input_ids"] != ids
    or hf["positions"] != m["positions"]
):
    raise RuntimeError("HF replay identity/range mismatch")
comp_dir = run / "components" / "component"


def load(name):
    p = comp_dir / f"component.{rid}.{fid}.layer17.{name}.json"
    c = json.loads(p.read_text())
    if (
        c.get("forward_id") != fid
        or c.get("rid") != rid
        or c.get("model_sha256") != expected_sha
    ):
        raise RuntimeError(f"{name}: identity mismatch")
    if (
        c.get("forward_mode") != "EXTEND"
        or c.get("step_input_ids") != ids
        or c.get("step_positions") != m["positions"]
        or c.get("extend_token_range") != [0, 514]
    ):
        raise RuntimeError(f"{name}: token range mismatch")
    return torch.tensor(c["value"], dtype=torch.bfloat16)


def metric(a, b):
    a, b = a.float().cpu(), b.float().cpu()
    if a.shape != b.shape:
        raise RuntimeError(f"shape mismatch {a.shape} != {b.shape}")
    d = a - b
    return {
        "shape": list(a.shape),
        "max_abs": float(d.abs().max()),
        "mean_abs": float(d.abs().mean()),
        "relative_l2": float(d.norm() / b.norm()),
    }


layer = torch.load(run / f"forward.{fid}.layer_output.17", weights_only=True)
if (
    layer["forward_id"] != fid
    or layer["rid"] != [rid]
    or layer["input_ids"].tolist() != ids
    or layer["positions"].tolist() != m["positions"]
):
    raise RuntimeError("layer output identity mismatch")
comparisons = {
    "q_post_rope": metric(load("q"), hf["attention_q_after_rope"][0].transpose(0, 1)),
    "k_post_rope": metric(load("k"), hf["attention_k_after_rope"][0].transpose(0, 1)),
    "v": metric(load("v"), hf["attention_v"][0].transpose(0, 1)),
    "attention_heads": metric(
        load("attention_output"), hf["attention_output_heads"][0]
    ),
    "decoder_layer_output_component_vs_runtime_layer": metric(
        load("decoder_layer_output"), layer["output"]
    ),
    "decoder_layer_output_hf_vs_runtime": metric(
        layer["output"], hf["decoder_layer_output"][0]
    ),
}
result = {
    "status": "MEASURED",
    "rid": rid,
    "forward_id": fid,
    "model_identity": m["model_identity"],
    "positions": [1, 514],
    "n": 514,
    "layer": 17,
    "hf_ple_source": hf["ple_source"],
    "comparisons": comparisons,
    "limitation": "HF uses pinned compressed-tensors decompression/replay; this single layer match does not explain or close full-prompt N512/N514 logit failures.",
}
path = run / "same-forward-hf-comparison.json"
path.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
