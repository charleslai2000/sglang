"""Forward-scoped BF16 Ragged attention for Gemma4 Full (``head_dim=512``).

Design (T011 Forward-level plan reuse)
--------------------------------------
* One :class:`BF16RaggedForwardPlan` per extend *Forward*, created by
  ``TritonAttnBackend.init_forward_metadata`` from the batch's authoritative
  **host** lengths. Both FlashInfer ragged wrappers are planned exactly once
  there; all Full layers of the forward share those two plans.
* Each wrapper owns its own 8 MiB integer workspace (FlashInfer allocates it in
  ``__init__``), so the prefix and extend plans cannot overwrite each other.
  Only the float scratch buffer is shared, which is safe because runs are
  serialised on one stream.
* Nothing here re-plans or reads indptr back inside the attention hot path.
* The FP8 E5M2 pool stays authoritative. Prefix BF16 K/V is materialised once
  per KV **owner** per forward and reused by that owner's shared-KV consumers;
  it is never cached across forwards and the pool is never resized.
* FlashInfer FA2 writes LSE in the log2 domain and ``merge_state`` consumes that
  same domain, so the merge keeps log2. Only diagnostic comparison against a
  natural-log reference multiplies by ``ln 2``.
"""

from __future__ import annotations

import atexit
import json
import os
from typing import Dict, List, Optional, Tuple

import torch

#: Hard ceiling for the transient BF16 prefix K+V pair of a single forward.
TEMPORARY_PREFIX_LIMIT_BYTES = 128 * 1024 * 1024

#: Effective per-forward prefix budget. The frozen --mem-fraction-static leaves
#: only a few hundred MiB of activation headroom at extend peak, so the transient
#: prefix pair must stay well below the hard ceiling unless the operator raises it.
PREFIX_BUDGET_MB_ENV = "SGLANG_T011_BF16_PREFIX_BUDGET_MB"
DEFAULT_PREFIX_BUDGET_MB = 32


def prefix_budget_bytes() -> int:
    """Transient prefix budget for this process, clamped to the hard ceiling."""
    raw = os.environ.get(PREFIX_BUDGET_MB_ENV, "").strip()
    megab = DEFAULT_PREFIX_BUDGET_MB
    if raw:
        try:
            megab = int(raw)
        except ValueError:
            megab = DEFAULT_PREFIX_BUDGET_MB
    megab = max(1, min(megab, TEMPORARY_PREFIX_LIMIT_BYTES // (1024 * 1024)))
    return megab * 1024 * 1024

#: FlashInfer float scratch shared by both ragged wrappers. Kept minimal because
#: the frozen --mem-fraction-static leaves little headroom at extend peak;
#: split-KV is disabled, so the scratch only holds small scheduling temporaries.
WORKSPACE_BYTES = 8 * 1024 * 1024

#: Cap on the FP8 gather staging buffer so a long prefix does not need a second
#: full-size copy next to the BF16 destination.
_GATHER_CHUNK_TOKENS = 4096

_LN2 = 0.6931471805599453


def prefix_bf16_bytes(
    total_prefix_tokens: int, num_kv_heads: int, head_dim: int
) -> int:
    """Bytes of the transient BF16 K+V prefix pair (two tensors)."""
    return total_prefix_tokens * num_kv_heads * head_dim * 2 * 2


def _indptr(lens: List[int], device: torch.device) -> torch.Tensor:
    """Build an int32 ``[0, c1, c1+c2, ...]`` indptr on device from host lengths."""
    out = [0] * (len(lens) + 1)
    total = 0
    for i, value in enumerate(lens):
        total += int(value)
        out[i + 1] = total
    return torch.tensor(out, dtype=torch.int32, device=device)


class BF16RaggedExtendState:
    """Persistent FlashInfer resources owned by one attention backend."""

    __slots__ = (
        "workspace",
        "prefix_wrapper",
        "extend_wrapper",
        "device",
        "timing",
        "stats",
    )

    def __init__(self, device: torch.device) -> None:
        from flashinfer import BatchPrefillWithRaggedKVCacheWrapper

        self.device = device
        self.workspace = torch.empty(WORKSPACE_BYTES, dtype=torch.uint8, device=device)
        # NHD is the pool layout: [token, kv_head, head_dim]. Each wrapper owns a
        # private integer workspace, so the two plans are independent.
        self.prefix_wrapper = BatchPrefillWithRaggedKVCacheWrapper(
            self.workspace, "NHD", backend="fa2"
        )
        self.extend_wrapper = BatchPrefillWithRaggedKVCacheWrapper(
            self.workspace, "NHD", backend="fa2"
        )
        self.timing = _ComponentTiming()
        # Coverage counters, reported next to the component timing.
        self.stats: Dict[str, float] = {
            "plans": 0.0,
            "skip_no_prefix": 0.0,
            "skip_over_budget": 0.0,
            "max_prefix_bytes": 0.0,
            "owner_conversions": 0.0,
            "shared_reuses": 0.0,
        }
        self.timing.stats_ref = self.stats


class BF16RaggedForwardPlan:
    """One forward's shared plan plus its per-owner prefix conversions."""

    __slots__ = (
        "prefix_wrapper",
        "extend_wrapper",
        "qo_indptr",
        "kv_indptr",
        "extend_indptr",
        "total_prefix",
        "prefix_bytes",
        "num_qo_heads",
        "num_kv_heads",
        "head_dim",
        "sm_scale",
        "logits_soft_cap",
        "prefix_cache",
        "sample_timing",
    )

    def __init__(self, **kwargs) -> None:
        for name, value in kwargs.items():
            setattr(self, name, value)


class _ComponentTiming:
    """Opt-in per-component attribution inside a real forward.

    ``SGLANG_T011_BF16_TIMING_PATH`` enables event sampling for every
    ``_TIMING_STRIDE``-th forward; the JSON dump happens at interpreter exit.
    Off by default so the acceptance runs carry no instrumentation.
    """

    _TIMING_STRIDE = 64

    __slots__ = ("path", "stride", "index", "pending", "counters", "stats_ref")

    def __init__(self) -> None:
        self.path = os.environ.get("SGLANG_T011_BF16_TIMING_PATH") or None
        try:
            self.stride = max(
                1, int(os.environ.get("SGLANG_T011_BF16_TIMING_STRIDE", "64"))
            )
        except ValueError:
            self.stride = 64
        self.index = 0
        self.pending: List[Tuple[str, torch.cuda.Event, torch.cuda.Event]] = []
        self.counters: Dict[str, float] = {}
        self.stats_ref: Optional[Dict[str, float]] = None
        if self.path:
            atexit.register(self._dump)

    def next_forward(self) -> bool:
        """Advance the forward counter and report whether this forward is sampled."""
        if self.path is None:
            return False
        self.index += 1
        # Periodic dump so an abrupt service stop still leaves useful numbers;
        # the final atexit dump (graceful stop) is authoritative.
        if self.index % max(1, self.stride * 8) == 0:
            self._dump()
        return self.index % self.stride == 0

    def mark(self, name: str, start: torch.cuda.Event, end: torch.cuda.Event) -> None:
        self.pending.append((name, start, end))

    def _dump(self) -> None:
        try:
            torch.cuda.synchronize()
        except Exception:  # pragma: no cover - shutdown races are not interesting
            return
        for name, start, end in self.pending:
            self.counters[name] = self.counters.get(name, 0.0) + start.elapsed_time(end)
        self.pending.clear()
        if not self.path:
            return
        payload = {
            "forwards_seen": self.index,
            "stride": self.stride,
            "ms": self.counters,
            "coverage": dict(self.stats_ref or {}),
            "prefix_budget_bytes": prefix_budget_bytes(),
        }
        try:
            with open(self.path, "w") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            pass


def plan_forward(
    state: BF16RaggedExtendState,
    qo_indptr_host: List[int],
    prefix_lens_host: List[int],
    extend_lens_host: List[int],
    num_qo_heads: int,
    num_kv_heads: int,
    head_dim: int,
    sm_scale: float,
    logits_soft_cap: float,
) -> Optional[BF16RaggedForwardPlan]:
    """Plan both ragged wrappers once for this forward.

    ``qo_indptr_host`` must be the cumulative ``[0, ...]`` query offsets; the
    prefix/extend indptrs are derived from the same authoritative host lengths.
    Returns ``None`` when the forward has no live prefix or exceeds the
    transient-memory ceiling, which makes the caller fall back to Triton.
    """
    total_prefix = sum(int(v) for v in prefix_lens_host)
    if total_prefix <= 0:
        state.stats["skip_no_prefix"] += 1
        return None
    need_bytes = prefix_bf16_bytes(total_prefix, num_kv_heads, head_dim)
    state.stats["max_prefix_bytes"] = max(state.stats["max_prefix_bytes"], need_bytes)
    if need_bytes > prefix_budget_bytes():
        state.stats["skip_over_budget"] += 1
        return None
    state.stats["plans"] += 1

    device = state.device
    qo_indptr = torch.tensor(qo_indptr_host, dtype=torch.int32, device=device)
    kv_indptr = _indptr(prefix_lens_host, device)
    extend_indptr = _indptr(extend_lens_host, device)
    plan = BF16RaggedForwardPlan(
        prefix_wrapper=state.prefix_wrapper,
        extend_wrapper=state.extend_wrapper,
        qo_indptr=qo_indptr,
        kv_indptr=kv_indptr,
        extend_indptr=extend_indptr,
        total_prefix=total_prefix,
        prefix_bytes=need_bytes,
        num_qo_heads=num_qo_heads,
        num_kv_heads=num_kv_heads,
        head_dim=head_dim,
        sm_scale=sm_scale,
        logits_soft_cap=logits_soft_cap,
        prefix_cache={},
        sample_timing=state.timing.next_forward(),
    )

    timing = state.timing
    sampled = plan.sample_timing
    start = torch.cuda.Event(enable_timing=True) if sampled else None
    if sampled:
        start.record()
    state.prefix_wrapper.plan(
        qo_indptr,
        kv_indptr,
        num_qo_heads,
        num_kv_heads,
        head_dim,
        head_dim,
        causal=False,
        sm_scale=sm_scale,
        logits_soft_cap=logits_soft_cap,
        q_data_type=torch.bfloat16,
        kv_data_type=torch.bfloat16,
        o_data_type=torch.bfloat16,
        disable_split_kv=True,
    )
    state.extend_wrapper.plan(
        qo_indptr,
        extend_indptr,
        num_qo_heads,
        num_kv_heads,
        head_dim,
        head_dim,
        causal=True,
        sm_scale=sm_scale,
        logits_soft_cap=logits_soft_cap,
        q_data_type=torch.bfloat16,
        kv_data_type=torch.bfloat16,
        o_data_type=torch.bfloat16,
        disable_split_kv=True,
    )
    if sampled:
        end = torch.cuda.Event(enable_timing=True)
        end.record()
        timing.mark("plan", start, end)
    return plan


def _as_cache_dtype(tensor: torch.Tensor, dtype: torch.dtype) -> torch.Tensor:
    """Reinterpret a uint8 storage view of an FP8 pool buffer without copying."""
    return tensor.view(dtype) if tensor.dtype == torch.uint8 else tensor


def prefix_kv_for_owner(
    plan: BF16RaggedForwardPlan,
    state: BF16RaggedExtendState,
    owner_layer_id: int,
    k_pool: torch.Tensor,
    v_pool: torch.Tensor,
    kv_indices: torch.Tensor,
    cache_dtype: torch.dtype,
    out_dtype: torch.dtype,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Gather + dequantise this owner's prefix once per forward."""
    # Key on the pool buffers themselves so an owner and its Shared-KV consumers
    # resolve to one entry, and evict any previously converted owner as soon as a
    # different owner shows up: the transient BF16 pair is the largest buffer on
    # the extend path and must never be held for more than one owner at a time.
    owner_key = (k_pool.data_ptr(), v_pool.data_ptr())
    cached = plan.prefix_cache.get(owner_key)
    if cached is not None:
        state.stats["shared_reuses"] += 1
        return cached
    for stale in [key for key in plan.prefix_cache if key != owner_key]:
        del plan.prefix_cache[stale]

    timing = state.timing
    sampled = plan.sample_timing
    start = torch.cuda.Event(enable_timing=True) if sampled else None
    if sampled:
        start.record()

    total = plan.total_prefix
    slots = kv_indices[:total]
    shape = (total, plan.num_kv_heads, plan.head_dim)
    k_prefix = torch.empty(shape, dtype=out_dtype, device=k_pool.device)
    v_prefix = torch.empty(shape, dtype=out_dtype, device=v_pool.device)
    k_src = _as_cache_dtype(k_pool, cache_dtype)
    v_src = _as_cache_dtype(v_pool, cache_dtype)
    for offset in range(0, total, _GATHER_CHUNK_TOKENS):
        end = min(offset + _GATHER_CHUNK_TOKENS, total)
        chunk = slots[offset:end]
        k_prefix[offset:end].copy_(k_src.index_select(0, chunk).to(out_dtype))
        v_prefix[offset:end].copy_(v_src.index_select(0, chunk).to(out_dtype))

    if sampled:
        stop = torch.cuda.Event(enable_timing=True)
        stop.record()
        timing.mark("gather_cast", start, stop)

    plan.prefix_cache[owner_key] = (k_prefix, v_prefix)
    state.stats["owner_conversions"] += 1
    return k_prefix, v_prefix


def run_layer(
    plan: BF16RaggedForwardPlan,
    state: BF16RaggedExtendState,
    q: torch.Tensor,
    k_new: torch.Tensor,
    v_new: torch.Tensor,
    k_prefix: torch.Tensor,
    v_prefix: torch.Tensor,
    out: torch.Tensor,
    prefix_qk_scale: float = 1.0,
    prefix_v_scale: float = 1.0,
) -> None:
    """Run both ragged attentions for one layer using the forward's plans."""
    from flashinfer.cascade import merge_state

    timing = state.timing
    sampled = plan.sample_timing
    num_heads = plan.num_qo_heads
    head_dim = plan.head_dim
    q3 = q.view(-1, num_heads, head_dim)
    k3 = k_new.view(-1, plan.num_kv_heads, head_dim)
    v3 = v_new.view(-1, plan.num_kv_heads, head_dim)

    prefix_sm_scale = plan.sm_scale * prefix_qk_scale

    start = torch.cuda.Event(enable_timing=True) if sampled else None
    stop = torch.cuda.Event(enable_timing=True) if sampled else None
    if sampled:
        start.record()
    o_prefix, lse_prefix = plan.prefix_wrapper.forward_return_lse(
        q3,
        k_prefix,
        v_prefix,
        causal=False,
        sm_scale=prefix_sm_scale,
        logits_soft_cap=plan.logits_soft_cap,
    )
    if sampled:
        stop.record()
        timing.mark("prefix_attention", start, stop)

    if sampled:
        start = torch.cuda.Event(enable_timing=True)
        stop = torch.cuda.Event(enable_timing=True)
        start.record()
    o_extend, lse_extend = plan.extend_wrapper.forward_return_lse(
        q3,
        k3,
        v3,
        causal=True,
        sm_scale=plan.sm_scale,
        logits_soft_cap=plan.logits_soft_cap,
    )
    if sampled:
        stop.record()
        timing.mark("extend_attention", start, stop)

    if sampled:
        start = torch.cuda.Event(enable_timing=True)
        stop = torch.cuda.Event(enable_timing=True)
        start.record()
    if prefix_v_scale != 1.0:
        o_prefix = o_prefix * prefix_v_scale
    merged, _ = merge_state(o_extend, lse_extend, o_prefix, lse_prefix)
    out.view(-1, num_heads, head_dim).copy_(merged)
    if sampled:
        stop.record()
        timing.mark("merge", start, stop)


__all__ = [
    "TEMPORARY_PREFIX_LIMIT_BYTES",
    "PREFIX_BUDGET_MB_ENV",
    "DEFAULT_PREFIX_BUDGET_MB",
    "prefix_budget_bytes",
    "WORKSPACE_BYTES",
    "BF16RaggedExtendState",
    "BF16RaggedForwardPlan",
    "prefix_bf16_bytes",
    "plan_forward",
    "prefix_kv_for_owner",
    "run_layer",
]
