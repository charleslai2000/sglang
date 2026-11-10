from typing import Any, Dict

import numpy as np
from transformers import Gemma4TextConfig


def _infer_gemma4_partial_rotary_factor(reader: Any, head_dim: int) -> float:
    """Recover active proportional-RoPE width from the GGUF frequency mask.

    Gemma4 GGUF's ``rope.dimension_count`` is the complete dimension handed
    to ggml_rope_ext, not the active proportional-RoPE width. The archive-side
    ``rope_freqs.weight`` encodes active frequencies as 1.0 and identity dims
    as 1e30; SGLang must recover the active width when rebuilding the HF config.
    """
    tensor = next(
        (tensor for tensor in reader.tensors if tensor.name == "rope_freqs.weight"),
        None,
    )
    if tensor is None:
        raise ValueError(
            "Gemma4 proportional RoPE requires the GGUF rope_freqs.weight mask"
        )

    factors = np.asarray(tensor.data, dtype=np.float32).reshape(-1)
    expected = head_dim // 2
    if factors.size != expected:
        raise ValueError(
            f"Gemma4 rope_freqs.weight has {factors.size} entries; expected {expected}"
        )
    active = np.flatnonzero(factors < 1e20)
    active_count = int(active.size)
    if (
        active_count == 0
        or not np.array_equal(active, np.arange(active_count))
        or not np.allclose(factors[:active_count], 1.0, rtol=0.0, atol=1e-6)
        or np.any(factors[active_count:] < 1e20)
    ):
        raise ValueError("Unsupported Gemma4 proportional RoPE frequency mask")
    return (2 * active_count) / head_dim


class Gemma4GGUFTextConfig(Gemma4TextConfig):
    """Gemma4 text config reconstructed from a native GGUF archive."""

    @classmethod
    def from_gguf(cls, gguf_path: str) -> "Gemma4GGUFTextConfig":
        from gguf import GGUFReader

        reader = GGUFReader(gguf_path)
        meta = {key: field.contents() for key, field in reader.fields.items()}
        shapes = {
            tensor.name: tuple(int(x) for x in tensor.shape)
            for tensor in reader.tensors
        }
        arch = "gemma4"

        def get(name: str) -> Any:
            return meta[f"{arch}.{name}"]

        def opt(name: str, default: Any = None) -> Any:
            return meta.get(f"{arch}.{name}", default)

        head_dim = int(get("attention.key_length"))
        swa_head_dim = int(get("attention.key_length_swa"))
        pattern = [bool(value) for value in get("attention.sliding_window_pattern")]
        if len(pattern) != int(get("block_count")):
            raise ValueError(
                "Gemma4 GGUF sliding-window pattern does not match block_count"
            )

        config = cls(
            vocab_size=shapes["token_embd.weight"][1],
            hidden_size=int(get("embedding_length")),
            intermediate_size=int(get("feed_forward_length")),
            num_hidden_layers=int(get("block_count")),
            num_attention_heads=int(get("attention.head_count")),
            num_key_value_heads=int(get("attention.head_count_kv")),
            # GGUF head dimensions are layer-role specific; Gemma4's runtime
            # resolves each from the corresponding rope_parameters entry.
            head_dim=head_dim,
            global_head_dim=head_dim,
            num_global_key_value_heads=int(get("attention.head_count_kv")),
            swa_head_dim=swa_head_dim,
            full_head_dim=head_dim,
            # Gemma4 GGUF stores the sliding/full head dimensions separately;
            # attention.head_count is the head count for both layer roles.
            # Deriving SWA heads by scaling with head_dim incorrectly halves
            # the Q width and causes fused QKV output/split mismatch.
            swa_num_attention_heads=int(get("attention.head_count")),
            swa_num_key_value_heads=int(get("attention.head_count_kv")),
            max_position_embeddings=int(get("context_length")),
            rms_norm_eps=float(get("attention.layer_norm_rms_epsilon")),
            sliding_window=int(get("attention.sliding_window")),
            layer_types=[
                "sliding_attention" if value else "full_attention" for value in pattern
            ],
            hidden_size_per_layer_input=int(get("embedding_length_per_layer_input")),
            vocab_size_per_layer_input=shapes["per_layer_token_embd.weight"][1],
            num_kv_shared_layers=int(get("attention.shared_kv_layers")),
            final_logit_softcapping=float(get("final_logit_softcapping")),
            attention_k_eq_v=False,
            attention_bias=False,
            hidden_activation="gelu_pytorch_tanh",
            tie_word_embeddings="output.weight" not in shapes,
            rope_parameters={
                "sliding_attention": {
                    "rope_type": "default",
                    "rope_theta": float(get("rope.freq_base_swa")),
                    "head_dim": swa_head_dim,
                },
                "full_attention": {
                    "rope_type": "proportional",
                    "head_dim": head_dim,
                    "partial_rotary_factor": _infer_gemma4_partial_rotary_factor(
                        reader, head_dim
                    ),
                    "rope_theta": float(get("rope.freq_base")),
                },
            },
            architectures=["Gemma4ForCausalLM"],
            dtype="bfloat16",
        )
        config._gguf_path = gguf_path
        config.model_type = "gemma4_text"
        return config
