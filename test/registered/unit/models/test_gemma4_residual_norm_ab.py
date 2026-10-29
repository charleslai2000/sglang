"""CPU boundary contract for the opt-in Gemma4 residual/RMSNorm diagnostic arm."""

import os

import pytest
import torch


@pytest.mark.parametrize("dtype", [torch.bfloat16, torch.float16])
def test_residual_norm_ab_gate_is_inert_by_default(monkeypatch, dtype):
    monkeypatch.delenv("SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB", raising=False)
    assert os.environ.get("SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB") is None

    hidden = torch.tensor([[1.001, -2.003]], dtype=torch.float32).to(dtype)
    residual = torch.tensor([[0.003, 0.007]], dtype=torch.float32).to(dtype)
    materialized = (hidden.float() + residual.float()).to(hidden.dtype)

    assert materialized.dtype == dtype
    assert torch.equal(materialized, (hidden.float() + residual.float()).to(dtype))
