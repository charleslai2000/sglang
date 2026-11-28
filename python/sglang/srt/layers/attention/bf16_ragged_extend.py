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

Sub-batch groups (T015)
-----------------------
The transient budget is per forward, but a forward's prefix is the sum over its
requests, so a batch of several medium prefixes used to be rejected even though
each request fitted comfortably. Measured on the C-8 and three-tier workloads that
was the dominant reason for low FA2 coverage (over-budget skips were 58-84 % of all
skips, largest forward ~3x the budget).

* Requests are partitioned, in batch order, into consecutive groups whose prefix
  fits the same budget (``max_group_tokens``); a request is never split or moved.
* Each group gets its own prefix plan at forward level (one wrapper each, sharing
  the split-KV scratch workspace, which is disabled) and is reused by every Full
  layer of that forward.
* The causal extend attention is still one whole-batch computation. Only the
  non-causal prefix attention is grouped; each group's partial state is merged with
  the extend state of exactly its own Q rows, which is the same merge the
  single-group path performs because groups are contiguous row ranges.
* The transient BF16 pair is one group's worth of tokens, reused sequentially by
  every group of every layer, so the peak equals the existing budget rather than
  the forward's total prefix.
* A single request whose own prefix exceeds the budget still rejects the whole
  forward (unchanged Triton fallback): a partially covered batch is never produced.
* With one group the plan tensors, wrappers and kernels are exactly the T013 path,
  so accepted single-group evidence keeps applying bit for bit.
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


def max_group_tokens(num_kv_heads: int, head_dim: int) -> int:
    """Tokens a single sub-batch group may carry under the transient budget.

    A group's BF16 K/V pair must fit the same per-forward budget that used to cap a
    whole forward, so the transient peak never grows.
    """
    per_token = prefix_bf16_bytes(1, num_kv_heads, head_dim)
    return max(1, prefix_budget_bytes() // per_token)


def _partition_groups(lens: List[int], cap_tokens: int) -> List[Tuple[int, int]]:
    """Greedy consecutive partition so every group's prefix fits ``cap_tokens``.

    Requests are never split and never reordered, so the group of a request is a
    contiguous row range of the batch — which is what lets the merge write the
    original Q order back without a gather.
    """
    groups: List[Tuple[int, int]] = []
    lo = 0
    used = 0
    for index, length in enumerate(lens):
        if index > lo and used + length > cap_tokens:
            groups.append((lo, index))
            lo = index
            used = 0
        used += length
    if lo < len(lens):
        groups.append((lo, len(lens)))
    return groups


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
        "group_wrappers",
        "over_budget_samples",
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
        # Sub-batch groups need one wrapper each (FlashInfer keeps the plan in
        # Python-side tensors, so the wrappers can share the scratch workspace that
        # only split-KV would use, and split-KV is disabled here). Created lazily
        # and kept for the process lifetime: they hold ~a few hundred bytes each.
        self.group_wrappers: List[object] = []
        self.timing = _ComponentTiming()
        # Coverage counters, reported next to the component timing.
        self.stats: Dict[str, float] = {
            "plans": 0.0,
            "skip_no_prefix": 0.0,
            "skip_over_budget": 0.0,
            "max_prefix_bytes": 0.0,
            "owner_conversions": 0.0,
            "shared_reuses": 0.0,
            "subbatch_plans": 0.0,
            "group_gathers": 0.0,
            "subbatch_groups": 0.0,
            "skip_request_over_budget": 0.0,
        }
        # Diagnostic only (enabled with the timing path): the shape of the forwards
        # that the transient budget rejects, so the coverage loss is attributable.
        self.over_budget_samples: List[Dict[str, float]] = []
        self.timing.stats_ref = self.stats
        self.timing.samples_ref = self.over_budget_samples


class BF16RaggedGroupPlan:
    """One sub-batch group: its own prefix plan over a contiguous request range."""

    __slots__ = (
        "wrapper",
        "qo_indptr",
        "kv_indptr",
        "req_lo",
        "req_hi",
        "row_lo",
        "row_hi",
        "tok_lo",
        "tok_hi",
    )

    def __init__(self, **kwargs) -> None:
        for name, value in kwargs.items():
            setattr(self, name, value)


class BF16RaggedForwardPlan:
    """One forward's shared plan plus its per-owner prefix conversions."""

    __slots__ = (
        "prefix_wrapper",
        "extend_wrapper",
        "groups",
        "subbatched",
        "scratch_k",
        "scratch_v",
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

    __slots__ = (
        "path",
        "stride",
        "index",
        "pending",
        "counters",
        "stats_ref",
        "samples_ref",
    )

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
        self.samples_ref: Optional[List[Dict[str, float]]] = None
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
            "over_budget_samples": list(self.samples_ref or []),
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
    lens = [int(v) for v in prefix_lens_host]
    extend_lens = [int(v) for v in extend_lens_host]
    total_prefix = sum(lens)
    if total_prefix <= 0:
        state.stats["skip_no_prefix"] += 1
        return None
    need_bytes = prefix_bf16_bytes(total_prefix, num_kv_heads, head_dim)
    state.stats["max_prefix_bytes"] = max(state.stats["max_prefix_bytes"], need_bytes)
    cap_tokens = max_group_tokens(num_kv_heads, head_dim)
    if max(lens) > cap_tokens:
        # Requirement: a single request that alone exceeds the transient budget keeps
        # the previous whole-forward Triton fallback — never a partially covered batch.
        state.stats["skip_over_budget"] += 1
        state.stats["skip_request_over_budget"] += 1
        if state.timing.path and len(state.over_budget_samples) < 256:
            state.over_budget_samples.append(
                {
                    "requests": len(lens),
                    "total_tokens": total_prefix,
                    "max_request_tokens": max(lens) if lens else 0,
                    "bytes": need_bytes,
                    "reason": "single_request_over_budget",
                }
            )
        return None
    group_ranges = _partition_groups(lens, cap_tokens)
    state.stats["plans"] += 1
    if len(group_ranges) > 1:
        state.stats["subbatch_plans"] += 1
        state.stats["subbatch_groups"] += len(group_ranges)

    device = state.device
    qo_indptr = torch.tensor(qo_indptr_host, dtype=torch.int32, device=device)
    kv_indptr = _indptr(prefix_lens_host, device)
    extend_indptr = _indptr(extend_lens_host, device)

    # Row/token offsets let every group address its own slice of the batch's Q rows
    # and of the flattened prefix indices; groups are consecutive, so both are
    # contiguous ranges and the merge writes the original Q order back in place.
    row_offsets = [0]
    for value in extend_lens:
        row_offsets.append(row_offsets[-1] + value)
    token_offsets = [0]
    for value in lens:
        token_offsets.append(token_offsets[-1] + value)

    single_group = len(group_ranges) == 1
    groups: List[BF16RaggedGroupPlan] = []
    for group_index, (req_lo, req_hi) in enumerate(group_ranges):
        if group_index == 0:
            wrapper = state.prefix_wrapper
        else:
            while len(state.group_wrappers) < group_index:
                from flashinfer import BatchPrefillWithRaggedKVCacheWrapper

                state.group_wrappers.append(
                    BatchPrefillWithRaggedKVCacheWrapper(
                        state.workspace, "NHD", backend="fa2"
                    )
                )
            wrapper = state.group_wrappers[group_index - 1]
        if single_group:
            group_qo_indptr = qo_indptr
            group_kv_indptr = kv_indptr
        else:
            group_qo: List[int] = [0]
            for value in extend_lens[req_lo:req_hi]:
                group_qo.append(group_qo[-1] + value)
            group_qo_indptr = torch.tensor(
                group_qo, dtype=torch.int32, device=device
            )
            group_kv_indptr = _indptr(lens[req_lo:req_hi], device)
        groups.append(
            BF16RaggedGroupPlan(
                wrapper=wrapper,
                qo_indptr=group_qo_indptr,
                kv_indptr=group_kv_indptr,
                req_lo=req_lo,
                req_hi=req_hi,
                row_lo=row_offsets[req_lo],
                row_hi=row_offsets[req_hi],
                tok_lo=token_offsets[req_lo],
                tok_hi=token_offsets[req_hi],
            )
        )

    plan = BF16RaggedForwardPlan(
        prefix_wrapper=state.prefix_wrapper,
        extend_wrapper=state.extend_wrapper,
        groups=groups,
        subbatched=not single_group,
        scratch_k=None,
        scratch_v=None,
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
    for group in groups:
        group.wrapper.plan(
            group.qo_indptr,
            group.kv_indptr,
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


def _ensure_scratch(
    plan: BF16RaggedForwardPlan, out_dtype: torch.dtype, device: torch.device
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Allocate the per-group transient pair once, sized to the largest group.

    The scratch is reused by every group of every layer of this forward, so the
    transient peak is one group (<= the per-forward budget) instead of one forward.
    """
    needed = max(group.tok_hi - group.tok_lo for group in plan.groups)
    shape = (needed, plan.num_kv_heads, plan.head_dim)
    if (
        plan.scratch_k is None
        or plan.scratch_k.dtype != out_dtype
        or plan.scratch_k.shape[0] < needed
    ):
        plan.scratch_k = torch.empty(shape, dtype=out_dtype, device=device)
        plan.scratch_v = torch.empty(shape, dtype=out_dtype, device=device)
    return plan.scratch_k, plan.scratch_v


def gather_group_prefix(
    plan: BF16RaggedForwardPlan,
    state: BF16RaggedExtendState,
    group: BF16RaggedGroupPlan,
    k_pool: torch.Tensor,
    v_pool: torch.Tensor,
    kv_indices: torch.Tensor,
    cache_dtype: torch.dtype,
    out_dtype: torch.dtype,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Materialise one group's BF16 prefix K/V from the authoritative FP8 pool."""
    timing = state.timing
    sampled = plan.sample_timing
    start = torch.cuda.Event(enable_timing=True) if sampled else None
    if sampled:
        start.record()

    scratch_k, scratch_v = _ensure_scratch(plan, out_dtype, k_pool.device)
    count = group.tok_hi - group.tok_lo
    slots = kv_indices[group.tok_lo : group.tok_hi]
    k_prefix = scratch_k[:count]
    v_prefix = scratch_v[:count]
    k_src = _as_cache_dtype(k_pool, cache_dtype)
    v_src = _as_cache_dtype(v_pool, cache_dtype)
    for offset in range(0, count, _GATHER_CHUNK_TOKENS):
        end = min(offset + _GATHER_CHUNK_TOKENS, count)
        chunk = slots[offset:end]
        k_prefix[offset:end].copy_(k_src.index_select(0, chunk).to(out_dtype))
        v_prefix[offset:end].copy_(v_src.index_select(0, chunk).to(out_dtype))

    if sampled:
        stop = torch.cuda.Event(enable_timing=True)
        stop.record()
        timing.mark("gather_cast", start, stop)
    # Counted separately from ``owner_conversions`` so the single-group (T013)
    # coverage numbers stay comparable across releases.
    state.stats["group_gathers"] += 1
    return k_prefix, v_prefix


def run_layer_subbatched(
    plan: BF16RaggedForwardPlan,
    state: BF16RaggedExtendState,
    q: torch.Tensor,
    k_new: torch.Tensor,
    v_new: torch.Tensor,
    out: torch.Tensor,
    k_pool: torch.Tensor,
    v_pool: torch.Tensor,
    kv_indices: torch.Tensor,
    cache_dtype: torch.dtype,
    prefix_qk_scale: float = 1.0,
    prefix_v_scale: float = 1.0,
) -> None:
    """One Full layer for an over-budget forward, split into bounded prefix groups.

    The causal extend attention still runs once over the whole batch; only the
    (non-causal) prefix attention is split, and each group's partial state is
    merged with the extend state of exactly its own Q rows, so the result is the
    same merge the single-group path performs — just bounded in transient memory.
    """
    from flashinfer.cascade import merge_state

    timing = state.timing
    sampled = plan.sample_timing
    num_heads = plan.num_qo_heads
    head_dim = plan.head_dim
    q3 = q.view(-1, num_heads, head_dim)
    k3 = k_new.view(-1, plan.num_kv_heads, head_dim)
    v3 = v_new.view(-1, plan.num_kv_heads, head_dim)
    out3 = out.view(-1, num_heads, head_dim)
    prefix_sm_scale = plan.sm_scale * prefix_qk_scale
    out_dtype = q.dtype

    start = torch.cuda.Event(enable_timing=True) if sampled else None
    if sampled:
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
        stop = torch.cuda.Event(enable_timing=True)
        stop.record()
        timing.mark("extend_attention", start, stop)

    for group in plan.groups:
        k_prefix, v_prefix = gather_group_prefix(
            plan,
            state,
            group,
            k_pool,
            v_pool,
            kv_indices,
            cache_dtype,
            out_dtype,
        )
        q_group = q3[group.row_lo : group.row_hi]
        start = torch.cuda.Event(enable_timing=True) if sampled else None
        if sampled:
            start.record()
        o_prefix, lse_prefix = group.wrapper.forward_return_lse(
            q_group,
            k_prefix,
            v_prefix,
            causal=False,
            sm_scale=prefix_sm_scale,
            logits_soft_cap=plan.logits_soft_cap,
        )
        if sampled:
            stop = torch.cuda.Event(enable_timing=True)
            stop.record()
            timing.mark("prefix_attention", start, stop)

        start = torch.cuda.Event(enable_timing=True) if sampled else None
        if sampled:
            start.record()
        if prefix_v_scale != 1.0:
            o_prefix = o_prefix * prefix_v_scale
        merged, _ = merge_state(
            o_extend[group.row_lo : group.row_hi],
            lse_extend[group.row_lo : group.row_hi],
            o_prefix,
            lse_prefix,
        )
        out3[group.row_lo : group.row_hi].copy_(merged)
        if sampled:
            stop = torch.cuda.Event(enable_timing=True)
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
    "BF16RaggedGroupPlan",
    "max_group_tokens",
    "gather_group_prefix",
    "run_layer_subbatched",
    "prefix_bf16_bytes",
    "plan_forward",
    "prefix_kv_for_owner",
    "run_layer",
]
