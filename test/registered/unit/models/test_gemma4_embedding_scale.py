import math

import pytest
import torch

from sglang.srt.models.gemma3_causal import Gemma3TextScaledWordEmbedding


@pytest.mark.parametrize(
    "device", ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]
)
@pytest.mark.parametrize("dtype", [torch.bfloat16, torch.float16])
def test_gemma_scaled_embedding_matches_low_precision_scale(device, dtype):
    embedding = Gemma3TextScaledWordEmbedding(
        num_embeddings=32,
        embedding_dim=2560,
        padding_idx=0,
        embed_scale=math.sqrt(2560),
    ).to(device=device, dtype=dtype)
    with torch.no_grad():
        embedding.weight.copy_(
            torch.linspace(
                -1, 1, embedding.weight.numel(), device=device, dtype=dtype
            ).reshape_as(embedding.weight)
        )

    ids = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]], device=device)
    raw = torch.nn.functional.embedding(ids, embedding.weight)
    expected = raw * torch.tensor(math.sqrt(2560), device=device, dtype=dtype)

    actual = embedding(ids)
    assert embedding.embed_scale.dtype == dtype
    assert torch.equal(actual, expected)
