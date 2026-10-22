#!/usr/bin/env python3
"""Fail-closed N=512/514 BF16 layer-localization and N=514 component audit."""
import json
import sys
from pathlib import Path

import torch

run = Path(sys.argv[1])
oracle_root = Path(sys.argv[2])
manifest = json.loads((run / "synthetic-manifest.json").read_text()) if (run / "synthetic-manifest.json").exists() else None
response = json.loads((run / "response.json").read_text())
request_rid = response["meta_info"]["id"]

# N=514 prefill-only runs intentionally have no logits manifest; select their
# full-input EXTEND UUID from the actual per-layer ForwardBatch capture.
base_candidates = []
for path in run.glob("forward.*.layer_output.0"):
    record = torch.load(path, weights_only=True)
    if (
        record["rid"] == [request_rid]
        and record["forward_mode"] == "EXTEND"
        and len(record["input_ids"]) == 514
    ):
        base_candidates.append((path, record))
if len(base_candidates) != 1:
    raise SystemExit(f"expected one full N=514 EXTEND for RID={request_rid}, found {len(base_candidates)}")
base_path, base = base_candidates[0]
forward_id = base["forward_id"]
hf514 = torch.load(oracle_root / "oracle-layers-n514.pt", weights_only=True)
if base["input_ids"].tolist() != hf514["input_ids"] or base["positions"].tolist() != hf514["positions"].tolist():
    raise SystemExit("N=514 service Forward IDs/positions do not match HF oracle")
print(f"N=514 RID={request_rid} Forward={forward_id} mode={base['forward_mode']} tokens=514")

for n in (512, 514):
    comparison = json.loads((oracle_root / f"n{n}/comparison.json").read_text())
    hf = torch.load(oracle_root / f"oracle-layers-n{n}.pt", weights_only=True)
    forward_id_n = comparison["bf16_forward_id"]
    previous = None
    largest_increment = None
    print(f"N={n} final-token BF16-vs-HF decoder outputs:")
    for layer in range(41):
        artifact = torch.load(
            oracle_root / f"bf16/forward.{forward_id_n}.layer_output.{layer}",
            weights_only=True,
        )
        if artifact["input_ids"].tolist() != hf["input_ids"] or artifact["positions"].tolist() != hf["positions"].tolist():
            raise SystemExit(f"identity mismatch N={n} layer={layer}")
        delta = artifact["output"].float()[-1] - hf["hidden_states"][layer + 1][0, -1].float()
        ref = hf["hidden_states"][layer + 1][0, -1].float()
        rel = float(delta.norm() / ref.norm())
        inc = rel if previous is None else rel - previous
        if largest_increment is None or inc > largest_increment[1]:
            largest_increment = (layer, inc, rel, float(delta.abs().max()))
        if layer in (15, 16, 17, 18, 19, 20, 21, 22, 23):
            print(f"  layer={layer:2d} rel_l2={rel:.8f} max_abs={float(delta.abs().max()):.6g} increment={inc:+.8f}")
        previous = rel
    print(
        "  largest positive layer-to-layer increase: "
        f"layer={largest_increment[0]} increment={largest_increment[1]:+.8f} "
        f"rel_l2={largest_increment[2]:.8f} max_abs={largest_increment[3]:.6g}"
    )

component_names = (
    "attention_norm_input",
    "q",
    "k",
    "v",
    "attention_output",
    "decoder_layer_output",
)
for name in component_names:
    path = run / "components" / f"component.{request_rid}.{forward_id}.layer17.{name}.json"
    if not path.exists():
        raise SystemExit(f"missing layer17 component: {path}")
    item = json.loads(path.read_text())
    if (
        item["rid"] != request_rid
        or item["forward_id"] != forward_id
        or item["forward_mode"] != "EXTEND"
        or item["batch_slot"] != 0
        or item["batch_slot_rid"] != request_rid
        or item["step_input_ids"] != hf514["input_ids"]
        or item["step_positions"] != hf514["positions"].tolist()
        or item["token_context_positions"] != hf514["positions"].tolist()
        or item["extend_seq_lens"] != [514]
        or item["extend_prefix_lens"] != [0]
        or not item["is_prefill_only"]
    ):
        raise SystemExit(f"identity/range mismatch in {path}")
    print(f"component MATCH layer=17 boundary={name} shape={item['shape']} dtype={item['dtype']}")
