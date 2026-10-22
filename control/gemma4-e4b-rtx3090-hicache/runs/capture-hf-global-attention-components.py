#!/usr/bin/env python3
"""Capture HF layer operation outputs for a SGLang exact N=514 layer input.

Uses the pinned HF model's standard compressed-tensors checkpoint modules, but
replays only the target layer with weights dequantized through compressed-tensors'
official per-group dequantizer and the official SGLang pack-quantized nibble order.
This isolates operation boundaries on the exact SGLang layer input; it does not
claim to emulate SGLang's W4A16 kernel accumulation order.

Usage: capture-hf-global-attention-components.py SERVICE_RUN N LAYER OUT.pt
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from compressed_tensors.compressors import ModelCompressor
from transformers import AutoModelForCausalLM
import transformers.models.gemma4.modeling_gemma4 as hf_module

run = Path(sys.argv[1])
n = int(sys.argv[2])
layer_id = int(sys.argv[3])
out_path = Path(sys.argv[4])
model_path = Path("/data/sglang-hicache/gemma4/model")
service_root = run / "bf16"
manifest_pairs = [(p, json.loads(p.read_text())) for p in service_root.glob("forward.*.manifest")]
manifest_pairs = [(p, m) for p, m in manifest_pairs if len(m.get("input_ids", [])) == n and m.get("forward_mode") == "EXTEND"]
if len(manifest_pairs) != 1:
    raise RuntimeError(f"expected exactly one N={n} EXTEND manifest, found {len(manifest_pairs)}")
_, manifest = manifest_pairs[0]
forward_id = manifest["forward_id"]
if manifest.get("status") != "COMPLETE" or manifest.get("model_identity", {}).get("model_sha256") != "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d":
    raise RuntimeError("manifest incomplete or checkpoint identity mismatch")
previous = torch.load(service_root / f"forward.{forward_id}.layer_output.{layer_id - 1}", weights_only=True)
ids, positions = previous["input_ids"].tolist(), previous["positions"].tolist()
hidden = previous["output"].float()
if ids != manifest["input_ids"] or positions != manifest["positions"] or hidden.shape[0] != n:
    raise RuntimeError("preceding-layer capture does not match exact Forward manifest")
ple_path = service_root / f"forward.{forward_id}.ple.{layer_id}"
ple_record = torch.load(ple_path, weights_only=True)
for field, expected in (("forward_id", forward_id), ("rid", manifest["rid"]), ("forward_mode", "EXTEND")):
    if ple_record.get(field) != expected:
        raise RuntimeError(f"PLE {field} mismatch: {ple_record.get(field)!r} != {expected!r}")
if ple_record.get("extend_seq_lens").tolist() != [n] or ple_record.get("extend_prefix_lens").tolist() != [0]:
    raise RuntimeError("PLE tensor is not from the exact fresh full-prefill query range")
if ple_record.get("input_ids").tolist() != ids or ple_record.get("positions").tolist() != positions:
    raise RuntimeError("PLE IDs/positions differ from exact Forward manifest")
per_layer_input = ple_record.get("value")
if tuple(per_layer_input.shape) != (n, 256):
    raise RuntimeError(f"unexpected exact-Forward PLE shape {tuple(per_layer_input.shape)}")


model = AutoModelForCausalLM.from_pretrained(
    model_path, torch_dtype=torch.bfloat16, device_map="cpu", trust_remote_code=True, low_cpu_mem_usage=True
).eval()
# Use compressed-tensors' complete official QAT decompression lifecycle. This
# also leaves PLE embedding and context-projection weights in their dense form.
ModelCompressor.from_compression_config(model.config.quantization_config).decompress_model(model)
text_model = model.model.language_model
layer = text_model.layers[layer_id]
# Force the explicit eager text attention implementation so the patched operation
# hook observes the actual attention operands/output rather than bypassing into SDPA.
layer.self_attn.config._attn_implementation = "eager"

if any(hasattr(module, "weight_packed") for module in layer.modules() if isinstance(module, torch.nn.Module)):
    raise RuntimeError("official compressed-tensors decompressor left packed target-layer weights")

records = {}
def save(name, tensor):
    records[name] = None if tensor is None else tensor.detach().float().cpu()
def hook(name):
    def fn(_module, _inputs, output):
        save(name, output[0] if isinstance(output, tuple) else output)
    return fn

handles = [
    layer.register_forward_pre_hook(
        lambda _m, inputs, kwargs: save("decoder_layer_input", kwargs["hidden_states"]),
        with_kwargs=True,
    )
]
for name in ("q_proj", "k_proj", "v_proj", "q_norm", "k_norm", "v_norm", "o_proj"):
    module = getattr(layer.self_attn, name, None)
    if module is not None:
        handles.append(module.register_forward_hook(hook(name)))
for name in ("input_layernorm", "post_attention_layernorm", "pre_feedforward_layernorm", "mlp", "post_feedforward_layernorm"):
    handles.append(getattr(layer, name).register_forward_hook(hook(name)))
handles.append(layer.register_forward_hook(hook("decoder_layer_output")))
original_apply = hf_module.apply_rotary_pos_emb
def capture_rotary(x, cos, sin, *args, **kwargs):
    out = original_apply(x, cos, sin, *args, **kwargs)
    save("rope_input", x); save("rope_cos", cos); save("rope_sin", sin); save("rope_output", out)
    return out
hf_module.apply_rotary_pos_emb = capture_rotary
original_attention = hf_module.eager_attention_forward
def capture_attention(module, query, key, value, attention_mask, *args, **kwargs):
    save("attention_q_after_rope", query); save("attention_k_after_rope", key); save("attention_v", value); save("attention_mask", attention_mask)
    scale = kwargs.get("scaling", getattr(module, "scaling", module.head_dim**-0.5))
    keys = hf_module.repeat_kv(key, module.num_key_value_groups)
    values = hf_module.repeat_kv(value, module.num_key_value_groups)
    scores = torch.matmul(query, keys.transpose(2, 3)) * scale
    if attention_mask is not None:
        scores = scores + attention_mask
    probs = torch.nn.functional.softmax(scores, dim=-1, dtype=torch.float32).to(query.dtype)
    save("attention_scores", scores); save("attention_probabilities", probs)
    result = original_attention(module, query, key, value, attention_mask, *args, **kwargs)
    save("attention_output_heads", result[0])
    return result
hf_module.apply_rotary_pos_emb = capture_rotary
hf_module.eager_attention_forward = capture_attention
try:
    pos = torch.tensor([positions], dtype=torch.long)
    hidden_batched = hidden[None].to(torch.bfloat16)
    # This exact N=514 request is a fresh causal prefill (prefix_len=0). A direct
    # decoder-layer replay must supply the same causal mask as the full HF model;
    # attention_mask=None would permit future-token attention and invalidate it.
    causal_mask = torch.full((1, 1, n, n), float("-inf"), dtype=hidden_batched.dtype)
    causal_mask = torch.triu(causal_mask, diagonal=1)
    per_layer = text_model.get_per_layer_inputs(torch.tensor([ids], dtype=torch.long), None)
    if per_layer is None or per_layer.shape[1] != n or per_layer.shape[2] != text_model.config.num_hidden_layers:
        raise RuntimeError("official HF PLE lookup does not align with the Forward token IDs/layers")
    per_layer_input = per_layer[:, :, layer_id, :]
    with torch.inference_mode():
        layer(hidden_states=hidden_batched, per_layer_input=per_layer_input,
              position_embeddings=text_model.rotary_emb(hidden_batched, pos, layer.self_attn.layer_type),
              attention_mask=causal_mask, position_ids=pos, shared_kv_states={}, past_key_values=None)
finally:
    for handle in handles: handle.remove()
    hf_module.apply_rotary_pos_emb = original_apply
    hf_module.eager_attention_forward = original_attention
records.update({"input_ids": ids, "positions": positions, "n": n, "layer": layer_id,
                "forward_id": forward_id, "rid": manifest["rid"],
                "model_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
                "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
                "hf_config_layer_type": layer.self_attn.layer_type,
                "weight_replay": "official compressed-tensors group dequantize + SGLang unpack_cols int4 nibble order; QAT BF16 dequant weights"})
out_path.parent.mkdir(parents=True, exist_ok=True)
torch.save(records, out_path)
print(json.dumps({"out": str(out_path), "forward_id": forward_id, "rid": manifest["rid"], "layer": layer_id,
                  "captured": sorted(k for k,v in records.items() if isinstance(v, torch.Tensor))}, indent=2))
