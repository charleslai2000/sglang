"""Dense qwen35 GGUF loading, preserving llama.cpp's tiled V-head weights."""

import logging

import torch

logger = logging.getLogger(__name__)


def build_qwen35_name_map(config):
    config = getattr(config, "text_config", config)
    result = {
        "token_embd.weight": "model.embed_tokens.weight",
        "output_norm.weight": "model.norm.weight",
        "output.weight": "lm_head.weight",
    }
    common = {
        "attn_norm": "input_layernorm",
        "post_attention_norm": "post_attention_layernorm",
        "ffn_gate": "mlp.gate_proj",
        "ffn_up": "mlp.up_proj",
        "ffn_down": "mlp.down_proj",
    }
    attention = {
        "attn_q": "self_attn.q_proj",
        "attn_k": "self_attn.k_proj",
        "attn_v": "self_attn.v_proj",
        "attn_output": "self_attn.o_proj",
        "attn_q_norm": "self_attn.q_norm",
        "attn_k_norm": "self_attn.k_norm",
    }
    linear = {
        "attn_qkv": "linear_attn.in_proj_qkv",
        "attn_gate": "linear_attn.in_proj_z",
        "ssm_alpha": "linear_attn.in_proj_a",
        "ssm_beta": "linear_attn.in_proj_b",
        "ssm_conv1d": "linear_attn.conv1d",
        "ssm_out": "linear_attn.out_proj",
        "ssm_norm": "linear_attn.norm",
    }
    layer_types = getattr(config, "layer_types", None)
    if layer_types is None:
        layer_types = [
            "full_attention"
            if (i + 1) % config.full_attention_interval == 0
            else "linear_attention"
            for i in range(config.num_hidden_layers)
        ]
    for i, layer_type in enumerate(layer_types):
        if layer_type not in ("full_attention", "linear_attention"):
            raise ValueError(f"Unsupported qwen35 layer type: {layer_type}")
        modules = common | (attention if layer_type == "full_attention" else linear)
        for source, target in modules.items():
            result[f"blk.{i}.{source}.weight"] = f"model.layers.{i}.{target}.weight"
        if layer_type == "linear_attention":
            result[f"blk.{i}.ssm_a"] = f"model.layers.{i}.linear_attn.A_log"
            result[f"blk.{i}.ssm_dt.bias"] = f"model.layers.{i}.linear_attn.dt_bias"
    return result


def qwen35_gguf_weights_iterator(path, name_map):
    import gguf

    reader = gguf.GGUFReader(path)
    names = {t.name for t in reader.tensors}
    missing = set(name_map) - names
    # A tied embedding checkpoint legitimately omits output.weight.
    missing.discard("output.weight")
    unexpected = names - set(name_map)
    if missing or unexpected or len(names) != len(reader.tensors):
        raise ValueError(
            f"Incomplete qwen35 GGUF mapping: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    if len(set(name_map.values())) != len(name_map):
        raise ValueError("Colliding qwen35 GGUF parameter names")

    def is_linear(name):
        return name.endswith(".weight") and not ("norm" in name or ".conv1d." in name)

    # Quantized linear metadata must precede packed bytes, including BF16 shards.
    for tensor in reader.tensors:
        name = name_map[tensor.name]
        if is_linear(name):
            yield (
                name.removesuffix("weight") + "qweight_type",
                torch.tensor(int(tensor.tensor_type)),
            )

    for tensor in reader.tensors:
        name = name_map[tensor.name]
        if is_linear(name):
            # Copy packed rows unchanged. No dequantization or column permutation.
            value = torch.from_numpy(tensor.data.copy())
            if tensor.tensor_type == gguf.GGMLQuantizationType.BF16:
                # GGUFReader exposes BF16 as bytes; reinterpret without rounding.
                value = value.view(torch.bfloat16)
            yield name.removesuffix("weight") + "qweight", value
            continue
        if tensor.tensor_type not in (
            gguf.GGMLQuantizationType.F32,
            gguf.GGMLQuantizationType.F16,
            gguf.GGMLQuantizationType.BF16,
        ):
            raise ValueError(
                f"Expected unquantized state/norm/conv tensor: {tensor.name}"
            )
        value = torch.from_numpy(
            gguf.dequantize(tensor.data, tensor.tensor_type).copy()
        ).float()
        if tuple(value.shape) != tuple(reversed(tensor.shape.tolist())):
            raise ValueError(f"Invalid GGUF logical shape for {tensor.name}")
        if not torch.isfinite(value).all():
            raise ValueError(f"Non-finite GGUF parameter {tensor.name}")
        if name.endswith(".A_log"):
            if not (value < 0).all():
                raise ValueError(f"GGUF ssm_a must contain negative A: {tensor.name}")
            value = (-value).log()
        elif ".conv1d." in name:
            value = value.unsqueeze(1)  # [channels, kernel] -> [channels, 1, kernel]
        elif (
            name.endswith(".weight")
            and "norm" in name
            and ".linear_attn.norm." not in name
        ):
            # llama.cpp stores effective RMS scales; GemmaRMSNorm adds one at runtime.
            value = value - 1.0
        yield name, value
    logger.info(
        "qwen35 GGUF: %d/%d tensors mapped; packed qtypes preserved; V-head layout=tiled",
        len(names),
        len(reader.tensors),
    )
