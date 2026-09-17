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

from gguf import GGUFReader

from sglang.srt.layers.quantization.gguf import GGUFConfig
from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
from sglang.srt.models import qwen3_5_text
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

path = sys.argv[1]
config = build_gguf_config(path)
with torch.device("meta"):
    model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=GGUFConfig())
params = dict(model.named_parameters(remove_duplicate=False))
print("param count:", len(params))
for key in sorted(params):
    if "in_proj_ba" in key or "dt_bias" in key or "A_log" in key or "conv1d" in key:
        print("  ", key)

name_map = build_qwen35_name_map(config)
reader = GGUFReader(path)
produced = []
for t in reader.tensors:
    if t.name not in name_map:
        continue
    name = name_map[t.name]
    if t.tensor_type.name != "F32":
        produced.append(name.replace("weight", "qweight"))
        produced.append(name.replace("weight", "qweight_type"))
    else:
        produced.append(name)

loaded_ids = set()


def recorder(param, loaded_weight, *args, **kwargs):
    loaded_ids.add(id(param))


required = set()
for name, param in model.named_parameters(remove_duplicate=False):
    if name == "lm_head.weight" and getattr(config, "tie_word_embeddings", False):
        continue
    required.add(name)
    if hasattr(param, "_weight_loader"):
        param._weight_loader = recorder
    else:
        param.weight_loader = recorder

model.load_weights([(n, torch.zeros(1)) for n in produced])
loaded = {
    name
    for name, param in model.named_parameters(remove_duplicate=False)
    if id(param) in loaded_ids
}
missing = sorted(required - loaded)
print("produced runtime names:", len(produced))
print("required params:", len(required), "loaded:", len(loaded), "missing:", len(missing))
for n in missing[:30]:
    print("  MISSING", n)
