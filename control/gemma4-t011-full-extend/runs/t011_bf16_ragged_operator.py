#!/usr/bin/env python3
"""Bounded BF16-ragged candidate vs production Triton Full Extend."""

import argparse
import json
import time

import torch
from flashinfer import BatchPrefillWithRaggedKVCacheWrapper
from flashinfer.cascade import merge_state
from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd

MiB = 1024 * 1024
TEMP_PREFIX_LIMIT = 128 * MiB


def sync():
    torch.cuda.synchronize()


def wall_us(fn, reps):
    fn()
    sync()
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    sync()
    return (time.perf_counter() - t0) * 1e6 / reps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--new-tokens", type=int, default=4096)
    ap.add_argument("--prefix-tokens", type=int, default=28672)
    ap.add_argument("--k-scale", type=float, default=1.0)
    ap.add_argument("--v-scale", type=float, default=1.0)
    args = ap.parse_args()
    assert torch.cuda.get_device_capability() == (8, 6)
    device, dtype = "cuda", torch.bfloat16
    n, p, hq, hkv, d = args.new_tokens, args.prefix_tokens, 8, 2, 512
    # Gemma4 Full RadixAttention sets scaling=1. Triton multiplies logits by
    # scaling * k_scale; it does not add a 1/sqrt(D) factor.
    scale = 1.0
    k_scale, v_scale = args.k_scale, args.v_scale
    # Exercise non-unit production quant/dequant scales. Current Gemma4 Full
    # RadixAttention uses scaling=1 and logit_cap=0.
    torch.manual_seed(7122026)
    q = torch.randn((n, hq, d), device=device, dtype=dtype) * 0.08
    kn = torch.randn((n, hkv, d), device=device, dtype=dtype) * 0.08
    vn = torch.randn_like(kn) * 0.08
    kp16 = torch.randn((p, hkv, d), device=device, dtype=dtype) * 0.08
    vp16 = torch.randn_like(kp16) * 0.08
    kp8 = (kp16 / k_scale).to(torch.float8_e5m2)
    vp8 = (vp16 / v_scale).to(torch.float8_e5m2)
    indices = torch.arange(p, device=device, dtype=torch.int64)
    prefix_bytes = 2 * p * hkv * d * torch.tensor([], dtype=dtype).element_size()
    if prefix_bytes > TEMP_PREFIX_LIMIT:
        raise RuntimeError(
            f"BF16 prefix allocation {prefix_bytes} exceeds {TEMP_PREFIX_LIMIT}"
        )

    # The production FP8 pool stores byte views; emulate its storage dtype/layout.
    k_pool, v_pool = kp8.view(torch.uint8), vp8.view(torch.uint8)
    qo_indptr = torch.tensor([0, n], device=device, dtype=torch.int32)
    prefix_indptr = torch.tensor([0, p], device=device, dtype=torch.int32)
    extend_indptr = torch.tensor([0, n], device=device, dtype=torch.int32)
    workspace = torch.empty(64 * MiB, device=device, dtype=torch.uint8)
    w_prefix = BatchPrefillWithRaggedKVCacheWrapper(workspace, "NHD", backend="fa2")
    w_extend = BatchPrefillWithRaggedKVCacheWrapper(workspace, "NHD", backend="fa2")
    o_tri = torch.empty_like(q)
    kv_indptr = prefix_indptr
    kv_indices = indices.to(torch.int64)
    k_full = torch.cat((kp8, kn.to(torch.float8_e5m2)), dim=0)
    v_full = torch.cat((vp8, vn.to(torch.float8_e5m2)), dim=0)
    triton_indptr = torch.tensor([0, p], device=device, dtype=torch.int32)
    plan_us_holder = []

    def plan():
        # Both BF16 ragged modules are plan-specialized; no per-forward host data.
        w_prefix.plan(
            qo_indptr,
            prefix_indptr,
            hq,
            hkv,
            d,
            d,
            causal=False,
            sm_scale=scale * k_scale,
            q_data_type=dtype,
            kv_data_type=dtype,
            o_data_type=dtype,
            logits_soft_cap=0.0,
            disable_split_kv=True,
        )
        w_extend.plan(
            qo_indptr,
            extend_indptr,
            hq,
            hkv,
            d,
            d,
            causal=True,
            sm_scale=scale,
            q_data_type=dtype,
            kv_data_type=dtype,
            o_data_type=dtype,
            logits_soft_cap=0.0,
            disable_split_kv=True,
        )

    def candidate():
        # Every call gathers valid prefix slots and materializes bounded BF16 K/V.
        idx = indices
        pk = k_pool.index_select(0, idx).view(torch.float8_e5m2).to(dtype)
        pv = v_pool.index_select(0, idx).view(torch.float8_e5m2).to(dtype)
        op, sp = w_prefix.forward_return_lse(q, pk, pv, causal=False, sm_scale=scale * k_scale)
        # Only prefix KV is stored quantized; new BF16 K/V uses unscaled scale.
        oe, se = w_extend.forward_return_lse(q, kn, vn, causal=True, sm_scale=scale)
        op = op * v_scale
        # FlashInfer FA2 and merge_state both use log2-domain LSE. Keep that
        # internal contract; convert only the returned merged LSE for oracle.
        return merge_state(oe, se, op, sp)

    def candidate_total():
        plan()
        return candidate()

    def triton():
        return extend_attention_fwd(
            q,
            kn,
            vn,
            o_tri,
            k_full,
            v_full,
            qo_indptr,
            triton_indptr,
            kv_indices,
            None,
            True,
            None,
            n,
            k_scale,
            v_scale,
            sm_scale=scale,
            page_size=1,
        )

    # Build kernels and plan once. Time plan separately (host planning + sync).
    plan()
    sync()
    t0 = time.perf_counter()
    for _ in range(args.reps):
        plan()
    sync()
    plan_us = (time.perf_counter() - t0) * 1e6 / args.reps
    for _ in range(args.warmup):
        candidate()
        triton()
    sync()
    # Full path timing includes gather+cast+two attention calls+merge; report plan too.
    cand_forward_us = wall_us(candidate, args.reps)
    tri_us = wall_us(triton, args.reps)
    cand_total_us = wall_us(candidate_total, args.reps)
    sync()
    allocated_before_candidate = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    out, lse = candidate()
    sync()
    candidate_peak_incremental = (
        torch.cuda.max_memory_allocated() - allocated_before_candidate
    )

    # Independent FP32 oracle: sampled causal positions, prefix values are the actual E5M2 values.
    max_o, max_lse = 0.0, 0.0
    LN2 = 0.6931471805599453
    for t in (0, 1, n // 2, n - 1):
        for head in range(hq):
            kh = head // (hq // hkv)
            prefix_logits = (kp8[:, kh].float() @ q[t, head].float()) * (scale * k_scale)
            new_logits = (kn[: t + 1, kh].float() @ q[t, head].float()) * scale
            logits = torch.cat((prefix_logits, new_logits), dim=0)
            prefix_values = vp8[:, kh].float() * v_scale
            values = torch.cat((prefix_values, vn[: t + 1, kh].float()), dim=0)
            ref_lse = torch.logsumexp(logits, 0)
            ref = torch.softmax(logits, 0) @ values
            max_o = max(max_o, (out[t, head].float() - ref).abs().max().item())
            max_lse = max(max_lse, (lse[t, head].float() * LN2 - ref_lse).abs().item())
    result = {
        "shape": {"new": n, "prefix": p, "q_heads": hq, "kv_heads": hkv, "head_dim": d},
        "logit_scale": scale,
        "effective_qk_scale_with_k_quant_scale": scale * k_scale,
        "device": torch.cuda.get_device_name(),
        "capability": torch.cuda.get_device_capability(),
        "torch": torch.__version__,
        "flashinfer": __import__("flashinfer").__version__,
        "k_scale": k_scale,
        "v_scale": v_scale,
        "prefix_bf16_kv_bytes": prefix_bytes,
        "prefix_gathered_fp8_transient_bytes": 2 * p * hkv * d,
        "temporary_prefix_limit_bytes": TEMP_PREFIX_LIMIT,
        "workspace_bytes": workspace.numel(),
        "plan_wall_us": plan_us,
        "candidate_forward_wall_us_including_gather_cast_attention_merge": cand_forward_us,
        "candidate_total_wall_us_including_plan": cand_total_us,
        "triton_complete_extend_wall_us": tri_us,
        "net_latency_reduction_vs_triton": 1.0 - cand_total_us / tri_us,
        "speedup_vs_triton": tri_us / cand_total_us,
        "fp32_oracle_sampled_max_abs_output": max_o,
        "flashinfer_lse_log2_converted_to_natural_for_oracle": True,
        "fp32_oracle_sampled_max_abs_lse": max_lse,
        "allocated_before_candidate_bytes": allocated_before_candidate,
        "candidate_peak_incremental_allocated_bytes": candidate_peak_incremental,
        "candidate_peak_total_allocated_bytes": torch.cuda.max_memory_allocated(),
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
