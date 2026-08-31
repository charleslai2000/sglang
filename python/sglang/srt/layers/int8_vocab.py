"""Block-128 INT8 tied embedding/lm_head.

Qwen3.5-4B's vocab embedding is 248320x2560 FP16 (~1.27GB) and is TIED with
the LM head (one shared matrix). On 6GB cards this is the largest single
weight. This layer stores ONE INT8 matrix + ONE per-block-128 absmax scale
vector (per-row scale, block 128), shared by embedding lookup and lm_head,
cutting the footprint from ~1.27GB to ~0.64GB while keeping weight tying.

Quantization: q = round(w / block_absmax * 127) (int8), dequant:
w_hat = q * block_absmax / 127 — the 1/127 factor is applied at dequant.

Embedding lookup:  gather int8 row -> multiply by per-block scale -> fp16
LM head:          block-wise matmul with per-block scale applied to logits
                  (avoids per-token systematic logit bias of pure per-row
                  scaling on the output dimension).

Used only when the checkpoint carries sm75_int8_vocab in its config.
"""

from typing import Optional

import torch
from torch import nn


class Int8Block128VocabEmbedding(nn.Module):
    def __init__(
        self,
        num_embeddings: int,
        embedding_dim: int,
        org_num_embeddings: Optional[int] = None,
        enable_tp: bool = True,
        **kwargs,
    ):
        super().__init__()
        self.num_embeddings = num_embeddings
        self.embedding_dim = embedding_dim
        assert embedding_dim % 128 == 0, "block-128 int8 needs hidden % 128 == 0"
        self.num_blocks = embedding_dim // 128
        self.weight = nn.Parameter(
            torch.empty(num_embeddings, embedding_dim, dtype=torch.int8),
            requires_grad=False,
        )
        self.scale = nn.Parameter(
            torch.empty(num_embeddings, self.num_blocks, dtype=torch.float16),
            requires_grad=False,
        )

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Embedding lookup + dequant. input_ids: [..., N] -> [..., N, H] fp16."""
        w = self.weight[input_ids]  # [..., N, H] int8
        s = self.scale[input_ids]  # [..., N, nb]
        out = (
            w.float()
            .view(*w.shape[:-1], self.num_blocks, 128)
            .mul_(s.float().unsqueeze(-1) * (1.0 / 127.0))
        )
        return out.reshape(w.shape).to(torch.float16)

    def forward_lm_head(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Logits via block-wise int8 matmul with per-block scale.

        hidden_states: [N, H] fp16 -> logits [N, V] in model dtype (fp32 accum).

        The per-block-128 scale s[v,b] must be folded into the weight blocks
        BEFORE the contraction over b (logits[n,v] = sum_b s[v,b]*dot_b), so
        each wc chunk is scaled by its scale row first.

        The int8 weight is dequantized in vocab chunks so peak transient
        memory stays bounded: a full fp32 materialization would be
        V*H*4B = 2.37GB on Qwen3.5-4B (V=248320, H=2560) and OOMs the 6GB
        card. Each chunk is c*H*4B (8192 rows -> ~80MB).
        """
        V, H = self.weight.shape
        w8 = self.weight.view(V, self.num_blocks, 128)  # [V, nb, 128] int8
        xv = hidden_states.view(-1, self.num_blocks, 128).float()  # [N, nb, 128]
        N = xv.shape[0]
        logits = torch.empty(N, V, dtype=torch.float32, device=xv.device)
        chunk = 8192
        for start in range(0, V, chunk):
            wc = w8[start : start + chunk].float()  # [c, nb, 128] fp32
            sc = (
                self.scale[start : start + chunk].float().unsqueeze(-1)
                * (1.0 / 127.0)
            )  # [c, nb, 1]
            logits[:, start : start + chunk] = torch.einsum(
                "nbc,vbc->nv", xv, wc * sc
            )
        return logits.to(hidden_states.dtype)
