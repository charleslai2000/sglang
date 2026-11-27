#!/usr/bin/env python3
"""Isolated FA2 Paged Prefix + Ragged Extend + MergeState vs Triton Extend.

Run only via the bounded T011 wrapper with the project GPU lock held.
"""

import argparse
import json
import time

import torch
from flashinfer import (
    BatchPrefillWithPagedKVCacheWrapper,
    BatchPrefillWithRaggedKVCacheWrapper,
)
from flashinfer.cascade import merge_state
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd


def sync():
    torch.cuda.synchronize()


def timed_cuda(fn, repeats):
    # CUDA event time; includes all work enqueued by fn, with synchronizing end.
    fn()
    sync()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(repeats):
        fn()
    end.record()
    end.synchronize()
    return start.elapsed_time(end) * 1000.0 / repeats


def run_case(new_tokens, prefix_tokens, reps, warmup):
    device = "cuda"
    q_heads, kv_heads, dim = 8, 2, 512
    dtype = torch.bfloat16
    scale_k = 1.0
    scale_v = 1.0
    torch.manual_seed(9173 + new_tokens + prefix_tokens)

    # Existing-cache representation is FP8 E5M2; current extend K/V retain BF16.
    q = torch.randn((new_tokens, q_heads, dim), device=device, dtype=dtype) * 0.08
    k_new = torch.randn((new_tokens, kv_heads, dim), device=device, dtype=dtype) * 0.08
    v_new = torch.randn_like(k_new) * 0.08
    k_prefix_bf16 = (
        torch.randn((prefix_tokens, kv_heads, dim), device=device, dtype=dtype) * 0.08
    )
    v_prefix_bf16 = torch.randn_like(k_prefix_bf16) * 0.08
    k_prefix = (k_prefix_bf16 / scale_k).to(torch.float8_e5m2)
    v_prefix = (v_prefix_bf16 / scale_v).to(torch.float8_e5m2)
    # FlashInfer NHD paged cache layout: [pages, page_size, kv_heads, head_dim].
    k_prefix_pages = k_prefix.unsqueeze(1)
    v_prefix_pages = v_prefix.unsqueeze(1)

    qo_indptr = torch.tensor([0, new_tokens], device=device, dtype=torch.int32)
    ragged_indptr = torch.tensor([0, new_tokens], device=device, dtype=torch.int32)
    paged_indptr = torch.tensor([0, prefix_tokens], device=device, dtype=torch.int32)
    paged_indices = torch.arange(prefix_tokens, device=device, dtype=torch.int32)
    last_page_len = torch.tensor([1], device=device, dtype=torch.int32)

    # The shared workspace and wrappers are included in persistent-memory accounting.
    base_alloc = torch.cuda.memory_allocated()
    workspace = torch.empty(64 * 1024 * 1024, device=device, dtype=torch.uint8)
    paged = BatchPrefillWithPagedKVCacheWrapper(workspace, "NHD", backend="fa2")
    ragged = BatchPrefillWithRaggedKVCacheWrapper(workspace, "NHD", backend="fa2")
    persistent_alloc = torch.cuda.memory_allocated() - base_alloc

    def plan_both():
        paged.plan(
            qo_indptr,
            paged_indptr,
            paged_indices,
            last_page_len,
            q_heads,
            kv_heads,
            dim,
            1,
            causal=False,
            sm_scale=dim**-0.5,
            q_data_type=dtype,
            kv_data_type=torch.float8_e5m2,
            o_data_type=dtype,
            disable_split_kv=True,
        )
        ragged.plan(
            qo_indptr,
            ragged_indptr,
            q_heads,
            kv_heads,
            dim,
            dim,
            causal=True,
            sm_scale=dim**-0.5,
            q_data_type=dtype,
            kv_data_type=dtype,
            o_data_type=dtype,
            disable_split_kv=True,
        )

    # Plan once before any timed forwards. Plan cost separately measured as CPU wall time
    # including synchronization, then also included in end-to-end FA2 path below.
    plan_both()
    sync()
    plan_start = time.perf_counter()
    for _ in range(reps):
        plan_both()
    sync()
    plan_us = (time.perf_counter() - plan_start) * 1e6 / reps
    plan_both()
    sync()

    def fa2_attention():
        o_prefix, lse_prefix = paged.forward_return_lse(
            q,
            (k_prefix_pages, v_prefix_pages),
            causal=False,
            sm_scale=dim**-0.5,
            k_scale=scale_k,
            v_scale=scale_v,
        )
        o_new, lse_new = ragged.forward_return_lse(
            q,
            k_new,
            v_new,
            causal=True,
            sm_scale=dim**-0.5,
        )
        return merge_state(o_new, lse_new, o_prefix, lse_prefix)

    def fa2_total():
        plan_both()
        return fa2_attention()

    # Triton reference uses prefix buffers and original-precision current K/V, same causal extend semantics.
    # Triton reads the paged prefix directly from FP8 pool buffers and receives
    # original-precision current K/V separately, matching production storage semantics.
    kbuf = torch.empty((prefix_tokens + new_tokens, kv_heads, dim), device=device, dtype=k_prefix.dtype)
    vbuf = torch.empty_like(kbuf)
    kbuf[:prefix_tokens].copy_(k_prefix)
    vbuf[:prefix_tokens].copy_(v_prefix)
    # Current tokens enter attention in BF16 while pool storage is FP8, as production.
    kbuf[prefix_tokens:].copy_(k_new.to(torch.float8_e5m2))
    vbuf[prefix_tokens:].copy_(v_new.to(torch.float8_e5m2))
    kv_indptr = torch.tensor([0, prefix_tokens], device=device, dtype=torch.int32)
    kv_indices = torch.arange(prefix_tokens, device=device, dtype=torch.int64)
    out_triton = torch.empty_like(q)

    def triton_total():
        extend_attention_fwd(
            q,
            k_new,
            v_new,
            out_triton,
            kbuf,
            vbuf,
            qo_indptr,
            kv_indptr,
            kv_indices,
            None,
            True,
            None,
            new_tokens,
            scale_k,
            scale_v,
            sm_scale=dim**-0.5,
            page_size=1,
        )
        return out_triton

    # Warm both implementations to compile and initialize workspaces.
    for _ in range(warmup):
        fa2_total()
        triton_total()
    sync()

    fa2_cuda_us = timed_cuda(fa2_attention, reps)
    triton_cuda_us = timed_cuda(triton_total, reps)
    # End-to-end FA2 wall time includes planning + both attention calls + merge + sync.
    fa2_total()
    sync()
    wall_start = time.perf_counter()
    for _ in range(reps):
        fa2_total()
    sync()
    fa2_total_wall_us = (time.perf_counter() - wall_start) * 1e6 / reps

    o_fa2, lse_fa2 = fa2_attention()
    o_tri = triton_total()
    sync()

    # Independent FP32 dense oracle on quantized prefix and BF16 current K/V.
    q32 = q.float()
    kp32 = k_prefix.float() * scale_k
    vp32 = v_prefix.float() * scale_v
    kn32, vn32 = k_new.float(), v_new.float()
    group = q_heads // kv_heads
    max_abs = 0.0
    max_lse_abs = 0.0
    for t in (0, min(1, new_tokens - 1), new_tokens // 2, new_tokens - 1):
        head_errors, lse_errors = [], []
        for h in range(q_heads):
            kh = h // group
            keys = torch.cat((kp32[:, kh], kn32[: t + 1, kh]), dim=0)
            vals = torch.cat((vp32[:, kh], vn32[: t + 1, kh]), dim=0)
            logits = (keys @ q32[t, h]) * (dim**-0.5)
            probs = torch.softmax(logits, dim=0)
            ref_o = probs @ vals
            ref_lse = torch.logsumexp(logits, dim=0)
            head_errors.append(ref_o)
            lse_errors.append(ref_lse)
        ref_o = torch.stack(head_errors)
        ref_lse = torch.stack(lse_errors)
        for actual_o, actual_lse in (
            (o_fa2[t].float(), lse_fa2[t].float()),
            (o_tri[t].float(), None),
        ):
            max_abs = max(max_abs, (actual_o - ref_o).abs().max().item())
            if actual_lse is not None:
                max_lse_abs = max(
                    max_lse_abs, (actual_lse - ref_lse).abs().max().item()
                )

    peak_alloc = torch.cuda.max_memory_allocated()
    result = {
        "new_tokens": new_tokens,
        "prefix_tokens": prefix_tokens,
        "q_heads": q_heads,
        "kv_heads": kv_heads,
        "head_dim": dim,
        "dtype_q_new_kv": str(dtype),
        "dtype_prefix_kv": str(k_prefix.dtype),
        "page_size": 1,
        "scale_k": scale_k,
        "scale_v": scale_v,
        "plan_wall_us_per_call": plan_us,
        "fa2_attention_merge_cuda_us": fa2_cuda_us,
        "fa2_plan_attention_merge_wall_us": fa2_total_wall_us,
        "triton_complete_extend_cuda_us": triton_cuda_us,
        "fa2_cuda_speedup_vs_triton": triton_cuda_us / fa2_cuda_us,
        "fa2_total_wall_speedup_vs_triton_cuda": triton_cuda_us / fa2_total_wall_us,
        "fa2_wrapper_persistent_alloc_bytes": persistent_alloc,
        "peak_allocated_bytes_process": peak_alloc,
        "fa2_vs_fp32_oracle_max_abs_output_sampled": max_abs,
        "fa2_vs_fp32_oracle_max_abs_lse_sampled": max_lse_abs,
        "triton_vs_fa2_max_abs_all_output": (o_tri.float() - o_fa2.float())
        .abs()
        .max()
        .item(),
    }
    del paged, ragged, workspace
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=2)
    args = ap.parse_args()
    assert torch.cuda.get_device_capability() == (8, 6)
    torch.cuda.init()
    meta = {
        "device": torch.cuda.get_device_name(),
        "capability": torch.cuda.get_device_capability(),
        "torch": torch.__version__,
        "flashinfer": __import__("flashinfer").__version__,
        "reps": args.reps,
        "warmup": args.warmup,
    }
    rows = []
    for n, p in ((1024, 7168), (4096, 12288), (4096, 28672)):
        torch.cuda.reset_peak_memory_stats()
        rows.append(run_case(n, p, args.reps, args.warmup))
        torch.cuda.empty_cache()
    with open(args.out, "w") as f:
        json.dump({"meta": meta, "cases": rows}, f, indent=2)
    print(json.dumps({"meta": meta, "cases": rows}, indent=2))


if __name__ == "__main__":
    main()
