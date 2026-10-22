import pytest
import torch
from transformers import AutoConfig
from transformers.models.gemma4.modeling_gemma4 import (
    Gemma4TextRotaryEmbedding as HFGemma4TextRotaryEmbedding,
    apply_rotary_pos_emb as hf_apply_rotary_pos_emb,
)

from sglang.srt.layers.rotary_embedding.factory import get_rope


@pytest.mark.parametrize(
    "attention_type,head_size,theta,partial_factor,rope_type,active_angles,identity_angles",
    [
        ("global", 512, 1_000_000.0, 0.25, "proportional", 64, 192),
        ("swa", 256, 10_000.0, 1.0, "default", 128, 0),
    ],
)
def test_gemma4_rope_cache_and_qk_apply_matches_hf(
    attention_type,
    head_size,
    theta,
    partial_factor,
    rope_type,
    active_angles,
    identity_angles,
):
    config = AutoConfig.from_pretrained(
        "/data/sglang-hicache/gemma4/model", trust_remote_code=True
    ).text_config
    layer_type = "full_attention" if attention_type == "global" else "sliding_attention"
    positions = torch.tensor([0, 1, 2, 17, 255, 511, 512, 513, 514])
    q = torch.randn(len(positions), 4, head_size, dtype=torch.bfloat16)
    k = torch.randn(len(positions), 2, head_size, dtype=torch.bfloat16)

    hf_rope = HFGemma4TextRotaryEmbedding(config)
    cos, sin = hf_rope(q[None], positions[None], layer_type=layer_type)
    hf_q = hf_apply_rotary_pos_emb(q[None], cos, sin, unsqueeze_dim=2)[0]
    hf_k = hf_apply_rotary_pos_emb(k[None], cos, sin, unsqueeze_dim=2)[0]

    rope = get_rope(
        head_size,
        rotary_dim=head_size,
        max_position=1024,
        base=theta,
        rope_scaling={"rope_type": rope_type},
        partial_rotary_factor=partial_factor,
        is_neox_style=True,
    )
    inv_freq = rope._compute_inv_freq(theta)
    assert rope.head_size == head_size
    assert rope.rotary_dim == head_size  # full-head NeoX cache/application
    assert inv_freq.numel() == head_size // 2
    assert int(torch.count_nonzero(inv_freq)) == active_angles
    assert int(torch.count_nonzero(inv_freq == 0)) == identity_angles
    assert tuple(rope.cos_sin_cache.shape) == (1024, head_size)

    actual_q, actual_k = rope.forward_native(
        positions, q.clone(), k.clone()
    )
    torch.testing.assert_close(actual_q, hf_q, rtol=0, atol=0)
    torch.testing.assert_close(actual_k, hf_k, rtol=0, atol=0)
