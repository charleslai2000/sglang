"""Bounded BF16 Ragged Full-Attention probe for Gemma4 ``head_dim=512``.

The FP8/E5M2 KV pool remains the only persistent cache. For one extend forward
this module gathers the *live* prefix slots, converts them to a temporary BF16
view (bounded by :data:`TEMPORARY_PREFIX_LIMIT_BYTES`, never cached), then runs
two FlashInfer FA2 ragged attentions:

* non-causal prefix attention over the gathered BF16 prefix;
* causal extend attention over the original-precision new K/V.

Concatenating the two key sets is exactly the production semantics, so
``merge_state`` over the two partial states gives the same result. FlashInfer
exposes LSE in the log2 domain and ``merge_state`` consumes that same domain;
only the merged value is converted when a caller compares against natural-log
oracles.

The module deliberately holds no opinion about when it is legal to use the
path: :meth:`TritonAttnBackend._try_bf16_ragged_full_extend` owns the gating and
the Triton fallback.
"""

from __future__ import annotations

from typing import Optional, Tuple

import torch

#: Hard ceiling for the transient BF16 prefix K+V pair of a single forward.
TEMPORARY_PREFIX_LIMIT_BYTES = 128 * 1024 * 1024

#: FlashInfer workspace shared by both ragged wrappers (plan + run scratch).
WORKSPACE_BYTES = 64 * 1024 * 1024

#: Cap on the FP8 gather staging buffer so a long prefix does not allocate a
#: second full-size copy in addition to the BF16 destination.
_GATHER_CHUNK_TOKENS = 4096

_LN2 = 0.6931471805599453


def prefix_bf16_bytes(
    total_prefix_tokens: int, num_kv_heads: int, head_dim: int
) -> int:
    """Bytes of the transient BF16 K+V prefix pair (two tensors)."""
    return total_prefix_tokens * num_kv_heads * head_dim * 2 * 2


class BF16RaggedExtendState:
    """Lazily created FlashInfer workspace/wrappers, owned by one attention backend."""

    __slots__ = ("workspace", "prefix_wrapper", "extend_wrapper")

    def __init__(self, device: torch.device) -> None:
        from flashinfer import BatchPrefillWithRaggedKVCacheWrapper

        self.workspace = torch.empty(WORKSPACE_BYTES, dtype=torch.uint8, device=device)
        # NHD is the pool layout: [token, kv_head, head_dim].
        self.prefix_wrapper = BatchPrefillWithRaggedKVCacheWrapper(
            self.workspace, "NHD", backend="fa2"
        )
        self.extend_wrapper = BatchPrefillWithRaggedKVCacheWrapper(
            self.workspace, "NHD", backend="fa2"
        )


def _as_cache_dtype(tensor: torch.Tensor, dtype: torch.dtype) -> torch.Tensor:
    """Reinterpret a uint8 storage view of an FP8 pool buffer without copying."""
    return tensor.view(dtype) if tensor.dtype == torch.uint8 else tensor


def gather_prefix_bf16(
    k_pool: torch.Tensor,
    v_pool: torch.Tensor,
    kv_indices: torch.Tensor,
    cache_dtype: torch.dtype,
    out_dtype: torch.dtype,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Materialise the BF16 K/V prefix for ``kv_indices`` in bounded chunks."""
    total = kv_indices.numel()
    shape = (total, k_pool.shape[-2], k_pool.shape[-1])
    k_prefix = torch.empty(shape, dtype=out_dtype, device=k_pool.device)
    v_prefix = torch.empty(shape, dtype=out_dtype, device=v_pool.device)
    k_src = _as_cache_dtype(k_pool, cache_dtype)
    v_src = _as_cache_dtype(v_pool, cache_dtype)
    for start in range(0, total, _GATHER_CHUNK_TOKENS):
        end = min(start + _GATHER_CHUNK_TOKENS, total)
        slots = kv_indices[start:end]
        k_prefix[start:end].copy_(k_src.index_select(0, slots).to(out_dtype))
        v_prefix[start:end].copy_(v_src.index_select(0, slots).to(out_dtype))
    return k_prefix, v_prefix


def bf16_ragged_extend(
    state: BF16RaggedExtendState,
    q: torch.Tensor,
    k_new: torch.Tensor,
    v_new: torch.Tensor,
    k_pool: torch.Tensor,
    v_pool: torch.Tensor,
    cache_dtype: torch.dtype,
    qo_indptr: torch.Tensor,
    kv_indptr: torch.Tensor,
    kv_indices: torch.Tensor,
    extend_lens: torch.Tensor,
    sm_scale: float,
    logits_soft_cap: float = 0.0,
    prefix_qk_scale: float = 1.0,
    prefix_v_scale: float = 1.0,
) -> torch.Tensor:
    """Return merged BF16 attention output ``[tokens, q_heads, head_dim]``.

    ``sm_scale`` multiplies QK for the original-precision new K/V. Quantized
    prefix keys additionally carry the cache descale factor
    ``prefix_qk_scale``; prefix values likewise carry ``prefix_v_scale`` inside
    their partial state, matching the FP8 kernels' ``k_scale``/``v_scale``
    placement (before the softmax normalisation and before ``merge_state``).
    """
    from flashinfer.cascade import merge_state

    num_qo_heads = q.shape[1]
    num_kv_heads = k_new.shape[1]
    head_dim = q.shape[2]
    q2 = q.reshape(-1, num_qo_heads, head_dim)
    k2 = k_new.reshape(-1, num_kv_heads, head_dim)
    v2 = v_new.reshape(-1, num_kv_heads, head_dim)
    qo_indptr = qo_indptr.to(torch.int32)
    kv_indptr = kv_indptr.to(torch.int32)

    extend_indptr = torch.zeros_like(qo_indptr)
    torch.cumsum(extend_lens.to(torch.int32), dim=0, out=extend_indptr[1:])

    prefix_sm_scale = sm_scale * prefix_qk_scale
    state.prefix_wrapper.plan(
        qo_indptr,
        kv_indptr,
        q2.shape[1],
        k2.shape[1],
        head_dim,
        head_dim,
        causal=False,
        sm_scale=prefix_sm_scale,
        logits_soft_cap=logits_soft_cap,
        q_data_type=q2.dtype,
        kv_data_type=q2.dtype,
        o_data_type=q2.dtype,
        disable_split_kv=True,
    )
    state.extend_wrapper.plan(
        qo_indptr,
        extend_indptr,
        q2.shape[1],
        k2.shape[1],
        head_dim,
        head_dim,
        causal=True,
        sm_scale=sm_scale,
        logits_soft_cap=logits_soft_cap,
        q_data_type=q2.dtype,
        kv_data_type=q2.dtype,
        o_data_type=q2.dtype,
        disable_split_kv=True,
    )

    k_prefix, v_prefix = gather_prefix_bf16(
        k_pool, v_pool, kv_indices, cache_dtype, q2.dtype
    )
    o_prefix, lse_prefix = state.prefix_wrapper.forward_return_lse(
        q2,
        k_prefix,
        v_prefix,
        causal=False,
        sm_scale=prefix_sm_scale,
        logits_soft_cap=logits_soft_cap,
    )
    o_extend, lse_extend = state.extend_wrapper.forward_return_lse(
        q2,
        k2,
        v2,
        causal=True,
        sm_scale=sm_scale,
        logits_soft_cap=logits_soft_cap,
    )
    if prefix_v_scale != 1.0:
        o_prefix = o_prefix * prefix_v_scale
    merged, _ = merge_state(o_extend, lse_extend, o_prefix, lse_prefix)
    return merged


def log2_lse_to_natural(lse: torch.Tensor) -> torch.Tensor:
    """Convert a FlashInfer log2-domain LSE to natural log (for oracle checks)."""
    return lse * _LN2


__all__ = [
    "TEMPORARY_PREFIX_LIMIT_BYTES",
    "WORKSPACE_BYTES",
    "BF16RaggedExtendState",
    "bf16_ragged_extend",
    "gather_prefix_bf16",
    "log2_lse_to_natural",
    "prefix_bf16_bytes",
]
