"""Exact base-stack mapping for Gemma4 text GGUF archives."""

from __future__ import annotations

from typing import Any, Dict


_GLOBAL = {
    "token_embd.weight": "model.embed_tokens.weight",
    "output_norm.weight": "model.norm.weight",
    "per_layer_token_embd.weight": "model.embed_tokens_per_layer.weight",
    "per_layer_model_proj.weight": "model.per_layer_model_projection.weight",
    "per_layer_proj_norm.weight": "model.per_layer_projection_norm.weight",
}
_LAYER = {
    "attn_norm.weight": "input_layernorm.weight",
    "post_attention_norm.weight": "post_attention_layernorm.weight",
    "ffn_norm.weight": "pre_feedforward_layernorm.weight",
    "post_ffw_norm.weight": "post_feedforward_layernorm.weight",
    "attn_q": "self_attn.q_proj",
    "attn_k": "self_attn.k_proj",
    "attn_v": "self_attn.v_proj",
    "attn_output": "self_attn.o_proj",
    "attn_q_norm": "self_attn.q_norm",
    "attn_k_norm": "self_attn.k_norm",
    "ffn_gate": "mlp.gate_proj",
    "ffn_up": "mlp.up_proj",
    "ffn_down": "mlp.down_proj",
    "inp_gate": "per_layer_input_gate",
    "proj": "per_layer_projection",
    "post_norm": "post_per_layer_input_norm",
    "layer_output_scale": "layer_scalar",
}
_DIRECT_LAYER_TENSORS = {
    "attn_norm.weight": "input_layernorm.weight",
    "post_attention_norm.weight": "post_attention_layernorm.weight",
    "ffn_norm.weight": "pre_feedforward_layernorm.weight",
    "post_ffw_norm.weight": "post_feedforward_layernorm.weight",
}


def build_gemma4_name_map(config: Any) -> Dict[str, str]:
    mapping = dict(_GLOBAL)
    for layer_id, layer_type in enumerate(config.layer_types):
        for gguf_name, hf_name in _LAYER.items():
            source = f"blk.{layer_id}.{gguf_name}"
            if gguf_name in ("attn_q", "attn_k", "attn_v") and layer_id >= config.num_hidden_layers - config.num_kv_shared_layers and gguf_name in ("attn_k", "attn_v"):
                continue
            if gguf_name in ("attn_q", "attn_k", "attn_v"):
                mapping[f"{source}.weight"] = (
                    f"model.layers.{layer_id}.self_attn.{gguf_name[-1]}_proj.weight"
                )
                continue
            if gguf_name == "layer_output_scale":
                mapping[source + ".weight"] = f"model.layers.{layer_id}.layer_scalar"
                continue
            if gguf_name in _DIRECT_LAYER_TENSORS:
                mapping[source] = f"model.layers.{layer_id}.{_DIRECT_LAYER_TENSORS[gguf_name]}"
                continue
            if layer_id >= config.num_hidden_layers - config.num_kv_shared_layers:
                if gguf_name in ("attn_k", "attn_v", "attn_k_norm"):
                    continue
            target = f"model.layers.{layer_id}.{hf_name}"
            mapping[f"{source}.weight"] = f"{target}.weight"
    return mapping


def validate_gemma4_gguf_coverage(
    gguf_path: str, name_map: Dict[str, str], config: Any
) -> None:
    import gguf

    reader = gguf.GGUFReader(gguf_path)
    names = {tensor.name for tensor in reader.tensors}
    # rope_freqs is an archive-side cache, not a learned model parameter.
    unmapped = sorted(names - name_map.keys() - {"rope_freqs.weight"})
    # Gemma4 stores K/V weights on the K/V-shared suffix only once in GGUF.
    # The base model's layer shape may still expose per-layer keys.
    allowed_shared_kv = {
        f"blk.{layer_id}.{name}.weight"
        for layer_id in range(config.num_hidden_layers - config.num_kv_shared_layers)
        for name in ("attn_k", "attn_v")
    }
    extra = sorted(name_map.keys() - names - allowed_shared_kv)
    # Shared layers deliberately omit K/V projections and norms. No other source
    # tensor may be silently skipped, and map entries must not invent weights.
    if unmapped or extra:
        raise RuntimeError(
            f"Gemma4 GGUF tensor coverage mismatch: unmapped={unmapped[:12]}, invented={extra[:12]}"
        )
