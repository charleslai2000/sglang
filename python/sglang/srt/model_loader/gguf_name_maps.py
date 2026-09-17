# Copyright 2023-2026 SGLang Team
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Per-architecture GGUF -> HF tensor name maps.

``GGUFModelLoader`` normally derives this map from ``gguf.get_tensor_name_map``,
which only covers architectures upstream gguf-py knows, and from a meta-device
``AutoModelForCausalLM.from_config`` to enumerate the HF parameter names. Neither
works for an architecture that lives outside transformers, so those are supplied
here instead.

A builder returns the complete ``{gguf_tensor_name: hf_param_name}`` map. Any
GGUF tensor left out of the map is skipped by ``gguf_quant_weights_iterator``,
which is how dummy tensors are dropped.
"""

from typing import Callable, Dict

from transformers import PretrainedConfig

# Sandwich naming: ffn_norm is the pre-FFN norm.
_MUSE_GLIMMER_LAYER_TENSORS = {
    "attn_norm": "input_layernorm",
    "post_attention_norm": "post_attn_norm",
    "ffn_norm": "post_attention_layernorm",
    "post_ffw_norm": "post_ffn_norm",
    "attn_q": "self_attn.q_proj",
    "attn_k": "self_attn.k_proj",
    "attn_v": "self_attn.v_proj",
    "attn_output": "self_attn.o_proj",
    "attn_gate": "self_attn.output_gate_proj",
    "ffn_gate": "mlp.gate_proj",
    "ffn_up": "mlp.up_proj",
    "ffn_down": "mlp.down_proj",
}

_MUSE_GLIMMER_GLOBAL_TENSORS = {
    "token_embd": "model.embed_tokens",
    "output_norm": "model.norm",
    "output": "lm_head",
}

# attn_q_norm/attn_k_norm omitted: Muse Glimmer's QK-norm is non-parametric.


def build_muse_glimmer_name_map(config: PretrainedConfig) -> Dict[str, str]:
    name_map = {
        f"{gguf}.weight": f"{hf}.weight"
        for gguf, hf in _MUSE_GLIMMER_GLOBAL_TENSORS.items()
    }
    for layer in range(config.num_hidden_layers):
        for gguf, hf in _MUSE_GLIMMER_LAYER_TENSORS.items():
            name_map[f"blk.{layer}.{gguf}.weight"] = f"model.layers.{layer}.{hf}.weight"
    return name_map


_QWEN35_GLOBAL_TENSORS = {
    "token_embd.weight": "model.embed_tokens.weight",
    "output_norm.weight": "model.norm.weight",
    "output.weight": "lm_head.weight",
}

# Full-attention layer: QKV/O plus the parametric QK-norms. The model's
# ``load_weights`` strips ``.self_attn`` before the stacked-param mapping runs.
_QWEN35_ATTENTION_LAYER_TENSORS = {
    "attn_norm.weight": "input_layernorm.weight",
    "post_attention_norm.weight": "post_attention_layernorm.weight",
    "attn_q.weight": "self_attn.q_proj.weight",
    "attn_k.weight": "self_attn.k_proj.weight",
    "attn_v.weight": "self_attn.v_proj.weight",
    "attn_output.weight": "self_attn.o_proj.weight",
    "attn_q_norm.weight": "self_attn.q_norm.weight",
    "attn_k_norm.weight": "self_attn.k_norm.weight",
    "ffn_gate.weight": "mlp.gate_proj.weight",
    "ffn_up.weight": "mlp.up_proj.weight",
    "ffn_down.weight": "mlp.down_proj.weight",
}

# GatedDeltaNet/SSM layer. ``attn_qkv`` is the fused q/k/v input projection and
# ``attn_gate`` the z gate; both are consumed through the model's
# ``stacked_params_mapping`` (in_proj_qkv + in_proj_z -> in_proj_qkvz).
# ``ssm_alpha`` is in_proj_a and ``ssm_beta`` in_proj_b, matching HF's
# ``b, a = torch.split(in_proj_ba(...))`` order. ``ssm_a``/``ssm_dt`` are bare
# direct parameters (A_log / dt_bias), not ``.weight`` tensors.
_QWEN35_LINEAR_LAYER_TENSORS = {
    "attn_norm.weight": "input_layernorm.weight",
    "post_attention_norm.weight": "post_attention_layernorm.weight",
    "attn_qkv.weight": "linear_attn.in_proj_qkv.weight",
    "attn_gate.weight": "linear_attn.in_proj_z.weight",
    "ssm_alpha.weight": "linear_attn.in_proj_a.weight",
    "ssm_beta.weight": "linear_attn.in_proj_b.weight",
    "ssm_conv1d.weight": "linear_attn.conv1d.weight",
    "ssm_norm.weight": "linear_attn.norm.weight",
    "ssm_out.weight": "linear_attn.out_proj.weight",
    "ssm_dt.bias": "linear_attn.dt_bias",
    "ssm_a": "linear_attn.A_log",
    "ffn_gate.weight": "mlp.gate_proj.weight",
    "ffn_up.weight": "mlp.up_proj.weight",
    "ffn_down.weight": "mlp.down_proj.weight",
}


def build_qwen35_name_map(config: PretrainedConfig) -> Dict[str, str]:
    """Exact ``qwen35`` GGUF -> HF checkpoint name map for the text backbone.

    The layer inventory is driven by ``config.layers_block_type`` so a linear
    layer never asks for attention-only tensors (or vice versa). Every base
    layer role appears in ``_QWEN35_LINEAR_LAYER_TENSORS`` /
    ``_QWEN35_ATTENTION_LAYER_TENSORS``; a role missing from both tables cannot
    be silently produced here, and ``validate_qwen35_gguf_coverage`` rejects any
    source tensor the base stack does not consume.
    """
    name_map = dict(_QWEN35_GLOBAL_TENSORS)
    layer_types = config.layers_block_type
    num_layers = config.num_hidden_layers
    if len(layer_types) < num_layers:
        raise ValueError(
            f"qwen35 config has {len(layer_types)} layer types for "
            f"{num_layers} hidden layers"
        )
    for layer in range(num_layers):
        layer_tensors = (
            _QWEN35_ATTENTION_LAYER_TENSORS
            if layer_types[layer] == "attention"
            else _QWEN35_LINEAR_LAYER_TENSORS
        )
        for gguf, hf in layer_tensors.items():
            name_map[f"blk.{layer}.{gguf}"] = f"model.layers.{layer}.{hf}"
    return name_map


def validate_qwen35_gguf_coverage(
    gguf_path: str,
    name_map: Dict[str, str],
    config: PretrainedConfig,
) -> None:
    """Fail closed when a base-model GGUF tensor would be skipped silently.

    ``gguf_quant_weights_iterator`` only yields tensors present in the map, so a
    missing entry is a silent weight drop. Tensors belonging to a bundled
    MTP/draft block (``blk.<N>.*`` with ``N >= num_hidden_layers``) are not part
    of the base stack and are allowed to stay unmapped.
    """
    import gguf

    reader = gguf.GGUFReader(gguf_path)
    base_layers = config.num_hidden_layers
    unmapped_required = []
    for tensor in reader.tensors:
        name = tensor.name
        if name in name_map:
            continue
        parts = name.split(".")
        is_draft_block = (
            len(parts) >= 2
            and parts[0] == "blk"
            and parts[1].isdigit()
            and int(parts[1]) >= base_layers
        )
        if is_draft_block:
            continue
        unmapped_required.append(name)
    if unmapped_required:
        preview = ", ".join(repr(name) for name in unmapped_required[:8])
        raise RuntimeError(
            f"qwen35 GGUF has {len(unmapped_required)} tensor(s) with no base "
            f"model mapping: {preview}"
        )


# Keyed by HF ``config.model_type`` (loader.py looks it up with that), which is
# not the GGUF ``general.architecture`` that GGUF_NATIVE_CONFIG_BUILDERS uses:
# llama.cpp spells the arch "muse-glimmer" while the HF config says "muse_glimmer".
GGUF_HF_NAME_MAP_BUILDERS: Dict[str, Callable[[PretrainedConfig], Dict[str, str]]] = {
    "muse_glimmer": build_muse_glimmer_name_map,
    "qwen3_5_text": build_qwen35_name_map,
}

GGUF_HF_NAME_MAP_VALIDATORS: Dict[
    str, Callable[[str, Dict[str, str], PretrainedConfig], None]
] = {
    "qwen3_5_text": validate_qwen35_gguf_coverage,
}
