"""CPU-only regression tests for Falcon-H1's mixed BF16/GPTQ checkpoint path."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from sglang.srt.models.falcon_h1 import FalconH1ForCausalLM


MODEL_SOURCE = Path(__file__).parents[3] / "python/sglang/srt/models/falcon_h1.py"


class _FakeParam:
    def __init__(self):
        self.loaded = []

    def weight_loader(self, _param, tensor, shard_id=None):
        self.loaded.append((tensor, shard_id))


class TestFalconH1MixedGPTQ(unittest.TestCase):
    def test_attention_is_unquantized_and_ffn_keeps_global_quant_config(self):
        tree = ast.parse(MODEL_SOURCE.read_text())
        layer = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef)
            and n.name == "FalconH1HybridAttentionDecoderLayer"
        )
        calls = {
            n.func.id if isinstance(n.func, ast.Name) else n.func.attr: n
            for n in ast.walk(layer)
            if isinstance(n, ast.Call)
            and (
                isinstance(n.func, ast.Name) or isinstance(n.func, ast.Attribute)
            )
            and (n.func.id if isinstance(n.func, ast.Name) else n.func.attr)
            in {"QKVParallelLinear", "RowParallelLinear", "FalconH1MLP"}
        }
        for name in ("QKVParallelLinear", "RowParallelLinear"):
            call = calls[name]
            quant = next(k.value for k in call.keywords if k.arg == "quant_config")
            self.assertIsInstance(quant, ast.Constant)
            self.assertIsNone(quant.value, name)
        ffn = calls["FalconH1MLP"]
        quant = next(k.value for k in ffn.keywords if k.arg == "quant_config")
        self.assertIsInstance(quant, ast.Name)
        self.assertEqual(quant.id, "quant_config")

    def test_independent_qkv_names_stack_without_qkqkv_mutation(self):
        obj = object.__new__(FalconH1ForCausalLM)
        torch.nn.Module.__init__(obj)
        params = {"model.layers.0.qkv_proj.weight": _FakeParam()}
        with patch.object(obj, "named_parameters", return_value=params.items()):
            loaded = obj.load_weights(
                [
                    ("model.layers.0.self_attn.q_proj.weight", torch.tensor([1.])),
                    ("model.layers.0.self_attn.k_proj.weight", torch.tensor([2.])),
                    ("model.layers.0.self_attn.v_proj.weight", torch.tensor([3.])),
                ]
            )
        self.assertNotIn("model.layers.0.qkqkv_proj.weight", loaded)
        self.assertEqual(loaded, {"model.layers.0.qkv_proj.weight"})
        self.assertEqual(
            [sid for _, sid in params["model.layers.0.qkv_proj.weight"].loaded],
            ["q", "k", "v"],
        )


if __name__ == "__main__":
    unittest.main()
