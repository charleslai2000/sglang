#!/usr/bin/env python3
import sys

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")

import torch

from sglang.test.layer_ut_utils import init_single_process_dist

init_single_process_dist()
from sglang.srt.layers import dp_attention
from sglang.srt.runtime_context import get_context

override = get_context().override_server_args(tp_size=1)
override.install()
dp_attention._ATTN_DP_SIZE = 1
dp_attention._ATTN_DP_RANK = 0
dp_attention.get_flags().dp.enabled = False
dp_attention.get_flags().dp.max_len_with_idle = False

from sglang.srt.configs.qwen3_5 import Qwen3_5TextConfig
from sglang.srt.models import qwen3_5, qwen3_5_text

config = Qwen3_5TextConfig(
    vocab_size=248320,
    hidden_size=5120,
    intermediate_size=17408,
    num_hidden_layers=2,
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
    rope_parameters={"rope_type": "default", "rope_theta": 1e7, "partial_rotary_factor": 0.25},
    tie_word_embeddings=False,
    architectures=["Qwen3_5ForCausalLM"],
)

with torch.device("meta"):
    model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=None)

body = model.model
want = [n for n in dict(body.named_parameters()).keys() if "A_log" in n or "dt_bias" in n]
print("body params with A_log/dt_bias:")
for n in want:
    p = dict(body.named_parameters())[n]
    print("  ", n, "has weight_loader:", hasattr(p, "weight_loader"), "has _weight_loader:", hasattr(p, "_weight_loader"))

recorded = set()
for n, p in model.named_parameters(remove_duplicate=False):
    def rec(param, loaded_weight, *a, _n=n, **k):
        recorded.add(_n)
    if hasattr(p, "_weight_loader"):
        p._weight_loader = rec
    else:
        p.weight_loader = rec

print("wrapper params with linear_attn.A_log:")
for n in dict(model.named_parameters()).keys():
    if "linear_attn.A_log" in n or "linear_attn.dt_bias" in n:
        print("  ", n)

names = [
    "model.layers.0.linear_attn.A_log",
    "model.layers.0.linear_attn.dt_bias",
]
model.load_weights([(n, torch.zeros(1)) for n in names])
print("recorded after load:", sorted(recorded))
print("body params_dict lookup:")
pd = dict(body.named_parameters())
for n in ["layers.0.linear_attn.A_log", "layers.0.linear_attn.dt_bias"]:
    print("  ", n, "in body params_dict:", n in pd)
