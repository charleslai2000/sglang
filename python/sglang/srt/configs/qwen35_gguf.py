"""Text-only Qwen3.5 GGUF metadata to SGLang configuration."""

from sglang.srt.configs.qwen3_5 import Qwen3_5Config


def build_qwen35_gguf_config(path):
    from gguf import GGUFReader

    reader = GGUFReader(path)

    def get(key):
        if key not in reader.fields:
            raise ValueError(f"Missing required qwen35 GGUF field: {key}")
        return reader.fields[key].contents()

    if get("general.architecture") != "qwen35":
        raise ValueError("Expected dense qwen35 GGUF")
    head_dim = int(get("qwen35.attention.key_length"))
    state_dim = int(get("qwen35.ssm.state_size"))
    value_heads = int(get("qwen35.ssm.time_step_rank"))
    if int(get("qwen35.ssm.inner_size")) != state_dim * value_heads:
        raise ValueError("Unsupported qwen35 GDN dimensions")
    tied = not any(t.name == "output.weight" for t in reader.tensors)
    text = dict(
        vocab_size=len(get("tokenizer.ggml.tokens")),
        hidden_size=int(get("qwen35.embedding_length")),
        intermediate_size=int(get("qwen35.feed_forward_length")),
        num_hidden_layers=int(get("qwen35.block_count")),
        num_attention_heads=int(get("qwen35.attention.head_count")),
        num_key_value_heads=int(get("qwen35.attention.head_count_kv")),
        head_dim=head_dim,
        max_position_embeddings=int(get("qwen35.context_length")),
        rms_norm_eps=float(get("qwen35.attention.layer_norm_rms_epsilon")),
        rope_theta=float(get("qwen35.rope.freq_base")),
        partial_rotary_factor=int(get("qwen35.rope.dimension_count")) / head_dim,
        rope_parameters={
            "rope_type": "default",
            "rope_theta": float(get("qwen35.rope.freq_base")),
            "partial_rotary_factor": int(get("qwen35.rope.dimension_count")) / head_dim,
        },
        linear_conv_kernel_dim=int(get("qwen35.ssm.conv_kernel")),
        linear_key_head_dim=state_dim,
        linear_value_head_dim=state_dim,
        linear_num_key_heads=int(get("qwen35.ssm.group_count")),
        linear_num_value_heads=value_heads,
        full_attention_interval=int(get("qwen35.full_attention_interval")),
        tie_word_embeddings=tied,
        dtype="bfloat16",
        eos_token_id=int(get("tokenizer.ggml.eos_token_id")),
    )
    return Qwen3_5Config(
        text_config=text,
        tie_word_embeddings=tied,
        language_model_only=True,
        architectures=["Qwen3_5ForConditionalGeneration"],
        dtype="bfloat16",
    )
