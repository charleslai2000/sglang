#!/usr/bin/env python3
"""Probe: can the Qwen3.5 text model be instantiated on meta in a CPU process?"""
import os
import sys

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")

import torch


def main() -> None:
    from sglang.test.layer_ut_utils import init_single_process_dist

    init_single_process_dist()
    from sglang.srt.runtime_context import get_context

    override = get_context().override_server_args(tp_size=1)
    override.install()
    # Harness-local shim: the real bootstrap calls initialize_dp_attention with a
    # full ModelConfig; a single-rank CPU process only needs the two globals it
    # publishes (dp_size=1, dp_rank=0, dp attention disabled).
    from sglang.srt.layers import dp_attention as _dpa

    _dpa._ATTN_DP_SIZE = 1
    _dpa._ATTN_DP_RANK = 0
    _dpa.get_flags().dp.enabled = False
    _dpa.get_flags().dp.max_len_with_idle = False
    from sglang.srt.configs.qwen3_5 import Qwen3_5TextConfig

    config = Qwen3_5TextConfig(
        vocab_size=248320,
        hidden_size=5120,
        intermediate_size=17408,
        num_hidden_layers=64,
        num_attention_heads=24,
        num_key_value_heads=4,
        head_dim=256,
        rms_norm_eps=1e-6,
        rope_theta=1e7,
        max_position_embeddings=262144,
        linear_conv_kernel_dim=4,
        linear_key_head_dim=128,
        linear_value_head_dim=128,
        linear_num_key_heads=16,
        linear_num_value_heads=48,
        full_attention_interval=4,
        partial_rotary_factor=0.25,
        tie_word_embeddings=False,
        architectures=["Qwen3_5ForCausalLM"],
    )
    print("config ok, model_type=", config.model_type)
    from sglang.srt.models import qwen3_5_text

    with torch.device("meta"):
        model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=None)
    names = list(dict(model.named_parameters()).keys())
    print("param count:", len(names))
    for name in names:
        print(name)


if __name__ == "__main__":
    main()
