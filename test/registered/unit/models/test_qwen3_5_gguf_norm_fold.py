#!/usr/bin/env python3
"""Focused regression tests for the CONTRACT-DRIVEN GGUF norm "+1" fold.

Covers, with the real runtime module classes (no GPU):

  * ``_gemma_norm_param_names`` selects exactly the ``GemmaRMSNorm`` params and
    structurally excludes ``linear_attn.norm`` (a real ``RMSNormGated``);
  * the ``.self_attn`` name bridge: the incoming GGUF q/k-norm name carries a
    ``.self_attn`` segment the runtime parameter does not, so the fold must
    still match (mirrors ``models/qwen3_5.py`` normalization);
  * ``_gguf_fold_absolute_norms`` subtracts exactly 1.0 for members only;
  * the HF-format path (``_is_gguf=False``) is inert;
  * ``Qwen3_5ForCausalLM.load_weights`` applies the fold on the GGUF path and
    not on the HF path, with ``linear_attn.norm`` unchanged as control.

Run:  PYTHONPATH=<tree>/python python test_gguf_norm_fold_v2.py
"""
from __future__ import annotations

from types import SimpleNamespace

import torch
from torch import nn

from sglang.kernels.ops.attention.fla.layernorm_gated import RMSNorm as RMSNormGated
from sglang.srt.layers.layernorm import GemmaRMSNorm
from sglang.srt.models.qwen3_5_text import (
    Qwen3_5ForCausalLM,
    _gemma_norm_param_names,
    _gguf_fold_absolute_norms,
    _gguf_runtime_param_name,
)

HID = 8


def _tiny_tree() -> nn.Module:
    """A miniature mirror of the real module nesting (runtime names)."""

    class Tiny(nn.Module):
        def __init__(self):
            super().__init__()
            self.model = nn.Module()
            self.model.norm = GemmaRMSNorm(HID)
            layer = nn.Module()
            layer.input_layernorm = GemmaRMSNorm(HID)
            layer.post_attention_layernorm = GemmaRMSNorm(HID)
            layer.q_norm = GemmaRMSNorm(HID)  # runtime name: no .self_attn
            layer.k_norm = GemmaRMSNorm(HID)
            linear = nn.Module()
            linear.norm = RMSNormGated(HID, device="cpu", dtype=torch.float32)
            layer.linear_attn = linear
            self.model.layers = nn.ModuleList([layer])
            self.mlp = nn.Linear(HID, HID)

    return Tiny()


EXPECTED = {
    "model.norm.weight",
    "model.layers.0.input_layernorm.weight",
    "model.layers.0.post_attention_layernorm.weight",
    "model.layers.0.q_norm.weight",
    "model.layers.0.k_norm.weight",
}


def test_target_set_is_exactly_gemma_norm_params():
    names = _gemma_norm_param_names(_tiny_tree())
    assert names == EXPECTED, sorted(names)


def test_linear_attn_norm_excluded_structurally():
    tree = _tiny_tree()
    # sanity: the control really is a RMSNormGated and named as such
    assert isinstance(tree.model.layers[0].linear_attn.norm, RMSNormGated)
    assert not isinstance(tree.model.layers[0].linear_attn.norm, GemmaRMSNorm)
    names = _gemma_norm_param_names(tree)
    assert "model.layers.0.linear_attn.norm.weight" not in names
    assert any("linear_attn.norm" in n for n in tree.state_dict())


def test_runtime_name_bridge_strips_self_attn():
    assert (
        _gguf_runtime_param_name("model.layers.0.self_attn.q_norm.weight")
        == "model.layers.0.q_norm.weight"
    )
    assert (
        _gguf_runtime_param_name("model.layers.0.linear_attn.norm.weight")
        == "model.layers.0.linear_attn.norm.weight"
    )


def test_fold_matches_gguf_q_norm_despite_self_attn_segment():
    names = _gemma_norm_param_names(_tiny_tree())
    t = torch.full((HID,), 3.0)
    folded = _gguf_fold_absolute_norms(
        "model.layers.0.self_attn.q_norm.weight", t, names
    )
    assert torch.all(folded == 2.0)
    control = _gguf_fold_absolute_norms(
        "model.layers.0.linear_attn.norm.weight", t, names
    )
    assert torch.all(control == 3.0)
    other = _gguf_fold_absolute_norms("model.layers.0.mlp.gate_proj.weight", t, names)
    assert torch.all(other == 3.0)
    # empty target set (HF path) => inert
    inert = _gguf_fold_absolute_norms(
        "model.layers.0.self_attn.q_norm.weight", t, frozenset()
    )
    assert torch.all(inert == 3.0)


class _Capture(nn.Module):
    def __init__(self):
        super().__init__()
        self.captured = {}

    def load_weights(self, body_weights):
        self.captured = dict(body_weights)
        return set(self.captured)


class _FakeSelf(nn.Module):
    def __init__(self, is_gguf, tree):
        super().__init__()
        self.config = SimpleNamespace(tie_word_embeddings=False)
        self._is_gguf = is_gguf
        self.model = _Capture()
        self._tree = tree

    def named_modules(self, *a, **k):
        return self._tree.named_modules(*a, **k)

    def named_parameters(self, *a, **k):
        return iter(())


_FEED = [
    "model.norm.weight",
    "model.layers.0.input_layernorm.weight",
    "model.layers.0.post_attention_layernorm.weight",
    "model.layers.0.self_attn.q_norm.weight",
    "model.layers.0.self_attn.k_norm.weight",
    "model.layers.0.linear_attn.norm.weight",
    "model.layers.0.mlp.gate_proj.weight",
]


def _run_load(is_gguf, raw=3.0):
    tree = _tiny_tree()
    weights = [(n, torch.full((HID,), raw)) for n in _FEED]
    fake = _FakeSelf(is_gguf, tree)
    Qwen3_5ForCausalLM.load_weights(fake, weights)
    return fake.model.captured


def test_load_weights_gguf_folds_five_roles_only():
    cap = _run_load(is_gguf=True)
    for name in (
        "norm.weight",
        "layers.0.input_layernorm.weight",
        "layers.0.post_attention_layernorm.weight",
        "layers.0.self_attn.q_norm.weight",
        "layers.0.self_attn.k_norm.weight",
    ):
        assert torch.all(cap[name] == 2.0), f"{name} not folded"
    assert torch.all(cap["layers.0.linear_attn.norm.weight"] == 3.0)
    assert torch.all(cap["layers.0.mlp.gate_proj.weight"] == 3.0)


def test_load_weights_hf_path_inert():
    cap = _run_load(is_gguf=False)
    for name in _FEED:
        short = name[len("model.") :]
        assert torch.all(cap[short] == 3.0), f"{name} shifted on HF path"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} passed")
