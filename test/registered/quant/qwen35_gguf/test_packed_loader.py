"""Regression for tuple QKV shards: scalar qtypes and byte-preserving row splits."""

from functools import partial
from types import SimpleNamespace

import torch

from sglang.srt.layers.linear import MergedColumnParallelLinear
from sglang.srt.models.qwen3_5 import Qwen3_5GatedDeltaNet


def test_qkv_scalar_types():
    module = SimpleNamespace(output_sizes=[2, 2, 6, 6], tp_size=1, tp_rank=0)
    param = torch.nn.Parameter(torch.zeros(4, dtype=torch.uint8), requires_grad=False)
    param.is_gguf_weight_type = True
    param.shard_weight_type = {}
    original = partial(MergedColumnParallelLinear.weight_loader, module)
    loader = Qwen3_5GatedDeltaNet._make_packed_weight_loader(module, original)
    loader(param, torch.tensor(21), (0, 1, 2))
    loader(param, torch.tensor(23), 3)
    assert param.tolist() == [21, 21, 21, 23]
    assert param.shard_weight_type == {0: 21, 1: 21, 2: 21, 3: 23}


def test_qkv_packed_rows_remain_exact():
    module = SimpleNamespace(output_sizes=[2, 2, 6, 6], tp_size=1, tp_rank=0)
    param = torch.nn.parameter.UninitializedParameter(requires_grad=False)
    param.is_gguf_weight = True
    param.output_dim = 0
    param.data_container, param.shard_id, param.shard_id_map = [], [], {}
    original = partial(MergedColumnParallelLinear.weight_loader, module)
    loader = Qwen3_5GatedDeltaNet._make_packed_weight_loader(module, original)
    packed = torch.arange(170, dtype=torch.uint8).reshape(10, 17)
    loader(param, packed, (0, 1, 2))
    assert [tuple(v.shape) for v in param.data_container] == [(2, 17), (2, 17), (6, 17)]
    assert torch.equal(torch.cat(param.data_container), packed)
    assert param.shard_id == [0, 1, 2]
