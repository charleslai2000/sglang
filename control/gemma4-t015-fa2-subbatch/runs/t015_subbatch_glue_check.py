#!/usr/bin/env python3
"""T015: prove that group-splitting the prefix attention is numerically equivalent.

Builds one synthetic batch (distinct prompts, real FP8 pool-shaped K/V), computes
the layer output twice with the real FlashInfer FA2 wrappers:

  reference : one forward-level plan over the whole prefix (today's covered path)
  subbatch  : the same forward planned as consecutive bounded groups, prefix
              attention per group, merged into the extend state per group

Both use the module's own code path (``plan_forward`` + ``run_layer`` /
``run_layer_subbatched``), so this checks the partition, the per-group planning,
the transient-buffer reuse and the merge ordering — not a re-implementation.

Usage: t015_subbatch_glue_check.py [--budget-mb 128]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
for _path in (
    str(ROOT / "python"),
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
    str(ROOT / "python/sglang/kernels/aot/python"),
):
    while _path in sys.path:
        sys.path.remove(_path)
sys.path[:0] = [
    "/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package",
    str(ROOT / "python"),
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
    str(ROOT / "python/sglang/kernels/aot/python"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-mb", type=int, default=128)
    parser.add_argument("--out", default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--prefix-lens",
        default="15360,15360,15360,15360",
        help="comma-separated prefix length per synthetic request",
    )
    parser.add_argument("--expect", choices=("subbatch", "skip", "single"), default="subbatch")
    args = parser.parse_args()

    import os

    os.environ["SGLANG_T011_BF16_PREFIX_BUDGET_MB"] = str(args.budget_mb)

    import torch

    from sglang.srt.layers.attention import bf16_ragged_extend as ragged

    torch.manual_seed(args.seed)
    device = torch.device("cuda")
    num_qo_heads, num_kv_heads, head_dim = 8, 2, 512
    sm_scale = head_dim**-0.5
    extend_len = 1024
    prefix_lens = [int(v) for v in args.prefix_lens.split(",") if v.strip()]

    total_prefix = sum(prefix_lens)
    total_tokens = total_prefix + extend_len * len(prefix_lens)
    print(
        json.dumps(
            {
                "budget_mb": args.budget_mb,
                "prefix_lens": prefix_lens,
                "total_prefix_tokens": total_prefix,
                "prefix_bytes": ragged.prefix_bf16_bytes(
                    total_prefix, num_kv_heads, head_dim
                ),
                "cap_tokens": ragged.max_group_tokens(num_kv_heads, head_dim),
            }
        )
    )

    # FP8 pool holding the prefix at arbitrary slots plus the new tokens, exactly
    # like the real pool: K/V in fp8_e5m2, gathered through kv_indices.
    kv_indices = torch.randperm(
        total_tokens - extend_len * len(prefix_lens), device=device
    )[:total_prefix].to(torch.int64)
    pool_tokens = int(kv_indices.max()) + 1
    k_pool = torch.randn(
        pool_tokens, num_kv_heads, head_dim, device=device, dtype=torch.float32
    ).to(torch.float8_e5m2)
    v_pool = torch.randn(
        pool_tokens, num_kv_heads, head_dim, device=device, dtype=torch.float32
    ).to(torch.float8_e5m2)

    q = torch.randn(
        extend_len * len(prefix_lens),
        num_qo_heads * head_dim,
        device=device,
        dtype=torch.bfloat16,
    )
    k_new = torch.randn(
        extend_len * len(prefix_lens),
        num_kv_heads * head_dim,
        device=device,
        dtype=torch.bfloat16,
    )
    v_new = torch.randn(
        extend_len * len(prefix_lens),
        num_kv_heads * head_dim,
        device=device,
        dtype=torch.bfloat16,
    )

    extend_lens = [extend_len] * len(prefix_lens)
    qo_indptr_host = [0]
    for value in extend_lens:
        qo_indptr_host.append(qo_indptr_host[-1] + value)

    state = ragged.BF16RaggedExtendState(device)

    def run_once(force_single_group: bool):
        plan = ragged.plan_forward(
            state,
            qo_indptr_host,
            prefix_lens,
            extend_lens,
            num_qo_heads,
            num_kv_heads,
            head_dim,
            sm_scale,
            0.0,
        )
        if plan is None:
            return None, None
        out = torch.zeros_like(q)
        if force_single_group or not plan.subbatched:
            # reference: one plan over the whole prefix (today's covered path)
            k_prefix, v_prefix = ragged.prefix_kv_for_owner(
                plan,
                state,
                0,
                k_pool,
                v_pool,
                kv_indices,
                torch.float8_e5m2,
                q.dtype,
            )
            ragged.run_layer(plan, state, q, k_new, v_new, k_prefix, v_prefix, out)
        else:
            ragged.run_layer_subbatched(
                plan,
                state,
                q,
                k_new,
                v_new,
                out,
                k_pool,
                v_pool,
                kv_indices,
                torch.float8_e5m2,
            )
        torch.cuda.synchronize()
        return plan, out

    cap = ragged.max_group_tokens(num_kv_heads, head_dim)

    if args.expect == "skip":
        plan = ragged.plan_forward(
            state,
            qo_indptr_host,
            prefix_lens,
            extend_lens,
            num_qo_heads,
            num_kv_heads,
            head_dim,
            sm_scale,
            0.0,
        )
        result = {
            "budget_mb": args.budget_mb,
            "cap_tokens": cap,
            "prefix_lens": prefix_lens,
            "expect": "skip",
            "plan_is_none": plan is None,
            "coverage_stats": dict(state.stats),
        }
        text = json.dumps(result, indent=2)
        print(text)
        if args.out:
            pathlib.Path(args.out).write_text(text + "\n")
        return
    reference_state_budget = ragged.prefix_budget_bytes()
    # Reference must not be budget-limited: raise the process budget for that one
    # call by driving the module's own helper through a wide environment override.
    import sglang.srt.layers.attention.bf16_ragged_extend as mod

    original = mod.prefix_budget_bytes
    try:
        mod.prefix_budget_bytes = lambda: total_prefix * num_kv_heads * head_dim * 2 * 2
        ref_plan, out_ref = run_once(force_single_group=False)
    finally:
        mod.prefix_budget_bytes = original
    assert not ref_plan.subbatched, "reference unexpectedly sub-batched"

    sub_plan, out_sub = run_once(force_single_group=False)
    assert sub_plan.subbatched, "sub-batched path not engaged"
    groups = [(g.req_lo, g.req_hi, g.tok_hi - g.tok_lo) for g in sub_plan.groups]

    def stats(a, b):
        diff = (a.float() - b.float()).abs()
        return {
            "max_abs": float(diff.max()),
            "mean_abs": float(diff.mean()),
            "ref_absmax": float(a.float().abs().max()),
        }

    rows = extend_len
    per_request = {
        f"req{i}": stats(
            out_sub[i * rows : (i + 1) * rows], out_ref[i * rows : (i + 1) * rows]
        )
        for i in range(len(prefix_lens))
    }
    result = {
        "budget_mb": args.budget_mb,
        "cap_tokens": cap,
        "reference_budget_bytes": reference_state_budget,
        "groups": groups,
        "groups_count": len(groups),
        "group_token_counts": [g[2] for g in groups],
        "coverage_stats": dict(state.stats),
        "overall": stats(out_sub, out_ref),
        "per_request": per_request,
        "bitwise_equal": bool(torch.equal(out_sub, out_ref)),
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
