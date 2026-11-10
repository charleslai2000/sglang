"""Gemma4 GGUF proportional-RoPE metadata contracts."""

import numpy as np
import pytest

from sglang.srt.configs.gemma4_gguf import _infer_gemma4_partial_rotary_factor


class _Tensor:
    def __init__(self, data):
        self.name = "rope_freqs.weight"
        self.data = np.asarray(data, dtype=np.float32)


class _Reader:
    def __init__(self, data):
        self.tensors = [] if data is None else [_Tensor(data)]


@pytest.mark.parametrize(
    ("active_count", "head_dim", "expected"),
    [(64, 512, 0.25), (128, 512, 0.5), (256, 512, 1.0)],
)
def test_infer_gemma4_partial_rope_from_gguf_mask(active_count, head_dim, expected):
    factors = np.concatenate(
        [np.ones(active_count), np.full(head_dim // 2 - active_count, 1e30)]
    )
    assert _infer_gemma4_partial_rotary_factor(_Reader(factors), head_dim) == expected


def test_infer_gemma4_partial_rope_requires_archive_mask():
    with pytest.raises(ValueError, match="requires the GGUF rope_freqs.weight mask"):
        _infer_gemma4_partial_rotary_factor(_Reader(None), 512)


@pytest.mark.parametrize(
    "factors",
    [
        [1.0] * 63 + [1e30] + [1.0] + [1e30] * 191,
        [1.0] * 64 + [1e30] * 36 + [1.0] + [1e30] * 155,
        [0.0] * 64 + [1e30] * 192,
    ],
)
def test_infer_gemma4_partial_rope_rejects_unsupported_mask(factors):
    with pytest.raises(ValueError, match="Unsupported Gemma4 proportional RoPE"):
        _infer_gemma4_partial_rotary_factor(_Reader(factors), 512)


def test_infer_gemma4_partial_rope_checks_head_dimension():
    with pytest.raises(ValueError, match="expected 256"):
        _infer_gemma4_partial_rotary_factor(_Reader([1.0] * 64), 512)
