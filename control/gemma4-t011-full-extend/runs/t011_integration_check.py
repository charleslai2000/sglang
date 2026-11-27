#!/usr/bin/env python3
"""Validate the integrated BF16-Ragged Full-Extend module against Triton.

This exercises the exact helper the backend calls
(:mod:`sglang.srt.layers.attention.bf16_ragged_extend`), so its numerics and
timings describe the integration rather than a private benchmark copy.

Run only under the project GPU lock with a bounded timeout.
"""

import argparse
import json
import time

import torch

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd
from sglang.srt.layers.attention.bf16_ragged_extend import (
    TEMPORARY_PREFIX_LIMIT_BYTES,
    BF16RaggedExtendState,
    bf16_ragged_extend,
    log2_lse_to_natural,
    prefix_bf16_bytes,
)

MiB = 1024 * 1024


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


def build_case(prefix_lens, extend_lens, q_heads, kv_heads, head_dim, seed):
    device, dtype = "cuda", torch.bfloat16
    torch.manual_seed(seed)
    total_prefix, total_new = sum(prefix_lens), sum(extend_lens)
    q = torch.randn((total_new, q_heads, head_dim), device=device, dtype=dtype) * 0.08
    k_new = (
        torch.randn((total_new, kv_heads, head_dim), device=device, dtype=dtype) * 0.08
    )
    v_new = torch.randn_like(k_new) * 0.08
    k_prefix = (
        torch.randn((total_prefix, kv_heads, head_dim), device=device) * 0.08
    ).to(torch.float8_e5m2)
    v_prefix = (
        torch.randn((total_prefix, kv_heads, head_dim), device=device) * 0.08
    ).to(torch.float8_e5m2)

    # Production FP8 pools expose a uint8 storage view of the FP8 bytes.
    k_pool = k_prefix.view(torch.uint8)
    v_pool = v_prefix.view(torch.uint8)

    def indptr(lens):
        out = torch.zeros(len(lens) + 1, device=device, dtype=torch.int32)
        torch.cumsum(
            torch.tensor(lens, device=device, dtype=torch.int32), dim=0, out=out[1:]
        )
        return out

    qo_indptr = indptr(extend_lens)
    kv_indptr = indptr(prefix_lens)
    extend_lens_t = torch.tensor(extend_lens, device=device, dtype=torch.int32)
    # Prefix slot ids: page_size 1, so slot == absolute pool position.
    kv_indices = torch.arange(total_prefix, device=device, dtype=torch.int64)
    # Triton needs a buffer holding prefix; new K/V arrive separately.
    k_tri = k_prefix
    v_tri = v_prefix
    return dict(
        q=q,
        k_new=k_new,
        v_new=v_new,
        k_pool=k_pool,
        v_pool=v_pool,
        k_tri=k_tri,
        v_tri=v_tri,
        qo_indptr=qo_indptr,
        kv_indptr=kv_indptr,
        kv_indices=kv_indices,
        extend_lens_t=extend_lens_t,
        prefix_lens=prefix_lens,
        extend_lens=extend_lens,
        total_prefix=total_prefix,
        total_new=total_new,
    )


def oracle_error(case, out, q_heads, kv_heads, head_dim, sm_scale):
    """FP32 dense oracle over the concatenated [prefix ; causal new] keys."""
    k_prefix = case["k_pool"].view(torch.float8_e5m2).float()
    v_prefix = case["v_pool"].view(torch.float8_e5m2).float()
    group = q_heads // kv_heads
    max_o = 0.0
    q_off = kv_off = 0
    for seq, (plen, nlen) in enumerate(zip(case["prefix_lens"], case["extend_lens"])):
        qs = case["q"][q_off : q_off + nlen]
        ks = case["k_new"][q_off : q_off + nlen]
        vs = case["v_new"][q_off : q_off + nlen]
        kp = k_prefix[kv_off : kv_off + plen]
        vp = v_prefix[kv_off : kv_off + plen]
        positions = [0, min(1, nlen - 1), nlen // 2, nlen - 1]
        for t in positions:
            for head in range(q_heads):
                kh = head // group
                keys = torch.cat((kp[:, kh], ks[: t + 1, kh]), dim=0)
                vals = torch.cat((vp[:, kh], vs[: t + 1, kh]), dim=0)
                logits = (keys @ qs[t, head].float()) * sm_scale
                ref_lse = torch.logsumexp(logits, 0)
                ref = torch.softmax(logits, 0) @ vals
                got = out[q_off + t, head].float()
                max_o = max(max_o, (got - ref).abs().max().item())
        q_off += nlen
        kv_off += plen
    return max_o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=2)
    args = ap.parse_args()

    assert torch.cuda.get_device_capability() == (8, 6)
    q_heads, kv_heads, head_dim = 8, 2, 512
    # Gemma4 Full RadixAttention sets scaling=1 (no 1/sqrt(d) factor).
    sm_scale = 1.0
    state = BF16RaggedExtendState(torch.device("cuda"))
    results = []

    shapes = [
        {"name": "single-4096-28672", "prefix": [28672], "extend": [4096], "seed": 11},
        {
            "name": "ragged-batch-unequal",
            "prefix": [1024, 2048, 512],
            "extend": [700, 300, 1500],
            "seed": 12,
        },
        {"name": "short-1024-7168", "prefix": [7168], "extend": [1024], "seed": 13},
    ]
    for spec in shapes:
        case = build_case(
            spec["prefix"],
            spec["extend"],
            q_heads,
            kv_heads,
            head_dim,
            seed=spec["seed"],
        )
        tb = prefix_bf16_bytes(case["total_prefix"], kv_heads, head_dim)
        assert tb <= TEMPORARY_PREFIX_LIMIT_BYTES, (tb, TEMPORARY_PREFIX_LIMIT_BYTES)

        def candidate():
            return bf16_ragged_extend(
                state,
                case["q"],
                case["k_new"],
                case["v_new"],
                case["k_pool"],
                case["v_pool"],
                torch.float8_e5m2,
                case["qo_indptr"],
                case["kv_indptr"],
                case["kv_indices"],
                case["extend_lens_t"],
                sm_scale,
            )

        o_tri = torch.empty_like(case["q"])
        max_extend = max(spec["extend"])

        def triton():
            extend_attention_fwd(
                case["q"],
                case["k_new"],
                case["v_new"],
                o_tri,
                case["k_tri"],
                case["v_tri"],
                case["qo_indptr"],
                case["kv_indptr"],
                case["kv_indices"],
                None,
                True,
                None,
                max_extend,
                1.0,
                1.0,
                sm_scale=sm_scale,
                page_size=1,
            )
            return o_tri

        for _ in range(args.warmup):
            candidate()
            triton()
        sync()
        cand_us = wall_us(candidate, args.reps)
        tri_us = wall_us(triton, args.reps)
        out = candidate()
        triton()
        sync()
        out_tri = o_tri
        max_o = oracle_error(case, out, q_heads, kv_heads, head_dim, sm_scale)
        results.append(
            {
                "case": spec["name"],
                "prefix_lens": spec["prefix"],
                "extend_lens": spec["extend"],
                "total_prefix": case["total_prefix"],
                "total_new": case["total_new"],
                "prefix_bf16_bytes": tb,
                "candidate_total_us": cand_us,
                "triton_total_us": tri_us,
                "net_latency_reduction": 1.0 - cand_us / tri_us,
                "fp32_oracle_max_abs_output": max_o,
                "vs_triton_max_abs_output": (out.float() - out_tri.float())
                .abs()
                .max()
                .item(),
            }
        )
        del case, out, out_tri, o_tri
        torch.cuda.empty_cache()

    payload = {
        "device": torch.cuda.get_device_name(),
        "capability": torch.cuda.get_device_capability(),
        "torch": torch.__version__,
        "flashinfer": __import__("flashinfer").__version__,
        "workspace_bytes": state.workspace.numel(),
        "temporary_prefix_limit_bytes": TEMPORARY_PREFIX_LIMIT_BYTES,
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
