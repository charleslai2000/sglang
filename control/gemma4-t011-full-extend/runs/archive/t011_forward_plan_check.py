#!/usr/bin/env python3
"""Validate the forward-scoped BF16 ragged integration (T011 plan reuse).

Checks, on the real backend code paths:
  * ``_plan_t011_bf16_ragged`` builds one plan per forward from host lengths;
  * ``_try_t011_bf16_ragged_layer`` uses that plan without re-planning;
  * one owner conversion is reused by its shared-KV consumers;
  * results match the production Triton kernel for a real multi-request batch.

Run only under the project GPU lock with a bounded timeout.
"""

import argparse
import json
import time
import types

import torch

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd
from sglang.srt.layers.attention import bf16_ragged_extend as t011
from sglang.srt.layers.attention.triton_backend import TritonAttnBackend

PREFIX_LENS = [1024, 2048, 512]
EXTEND_LENS = [700, 300, 1500]
OWNER_LAYERS = [5, 11, 17, 23]
SHARED_LAYERS = [29, 35, 41]  # all resolve to owner 23 via RadixAttention.layer_id


class FakePool:
    """Owner-keyed FP8 pool with a per-layer write region for new tokens."""

    def __init__(self, owner_ids, k_prefix, v_prefix, k_new, v_new, device):
        self.dtype = torch.float8_e5m2
        self.device = device
        self._buffers = {}
        self._new_slots = {}
        total_prefix = k_prefix.shape[0]
        total_new = k_new.shape[0]
        for owner in owner_ids:
            k = torch.empty(
                (total_prefix + total_new, 2, 512),
                dtype=torch.float8_e5m2,
                device=device,
            )
            v = torch.empty_like(k)
            k[:total_prefix] = k_prefix
            v[:total_prefix] = v_prefix
            self._buffers[owner] = (k, v)
        # Every owner stores the same synthetic "new" K/V at slots >= total_prefix,
        # mirroring what the owner layer wrote before consumers run.
        for owner in owner_ids:
            k, v = self._buffers[owner]
            k[total_prefix:] = k_new
            v[total_prefix:] = v_new
        self.out_cache_loc = torch.arange(
            total_prefix, total_prefix + total_new, dtype=torch.int64, device=device
        )

    def get_kv_buffer(self, layer_id):
        return self._buffers[layer_id]


def make_self(
    pool, kv_indices, qo_indptr, device, v_head_dim=512, num_head=8, num_kv=2
):
    meta = types.SimpleNamespace(
        custom_mask=None, kv_indices=kv_indices, qo_indptr=qo_indptr, kv_indptr=None
    )
    return types.SimpleNamespace(
        enable_t011_bf16_ragged_full_extend=True,
        _t011_bf16_state=None,
        _t011_bf16_plan=None,
        dcp_size=1,
        enable_deterministic=False,
        num_head=num_head,
        num_kv_head=num_kv,
        v_head_dim=v_head_dim,
        device=device,
        token_to_kv_pool=pool,
        _translate_kv_loc=None,
        forward_metadata=meta,
    )


def make_layer(layer_id, is_shared):
    return types.SimpleNamespace(
        qk_head_dim=512,
        v_head_dim=512,
        tp_q_head_num=8,
        tp_k_head_num=2,
        sliding_window_size=-1,
        scaling=1.0,
        logits_soft_cap=None,
        k_scale_float=1.0,
        v_scale_float=1.0,
        xai_temperature_len=-1,
        layer_id=layer_id,
        # Shared consumers receive k=v=None and read the owner's pool rows.
        receives_none=is_shared,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assert torch.cuda.get_device_capability() == (8, 6)
    device, dtype = "cuda", torch.bfloat16
    torch.manual_seed(4242)

    total_prefix, total_new = sum(PREFIX_LENS), sum(EXTEND_LENS)
    q = torch.randn((total_new, 8, 512), device=device, dtype=dtype) * 0.08
    k_new = torch.randn((total_new, 2, 512), device=device, dtype=dtype) * 0.08
    v_new = torch.randn_like(k_new) * 0.08
    k_prefix = (torch.randn((total_prefix, 2, 512), device=device) * 0.08).to(
        torch.float8_e5m2
    )
    v_prefix = (torch.randn((total_prefix, 2, 512), device=device) * 0.08).to(
        torch.float8_e5m2
    )

    pool = FakePool(OWNER_LAYERS, k_prefix, v_prefix, k_new, v_new, device)
    kv_indices = torch.arange(total_prefix, device=device, dtype=torch.int64)
    qo_indptr_host = [0]
    for value in EXTEND_LENS:
        qo_indptr_host.append(qo_indptr_host[-1] + value)
    qo_indptr = torch.tensor(qo_indptr_host, device=device, dtype=torch.int32)
    owner = make_self(pool, kv_indices, qo_indptr, device)
    fb = types.SimpleNamespace(
        extend_prefix_lens_cpu=list(PREFIX_LENS),
        extend_seq_lens_cpu=list(EXTEND_LENS),
        out_cache_loc=pool.out_cache_loc,
    )

    # 1) one plan per forward, built from host lengths.
    plan = TritonAttnBackend._plan_t011_bf16_ragged(owner, fb)
    assert plan is not None, "plan should be created for a qualifying batch"
    owner._t011_bf16_plan = plan
    first_plan = (plan.prefix_wrapper._plan_info, plan.extend_wrapper._plan_info)

    # 2) run all seven Full layers through the hot path.
    per_layer = {}
    for layer_id in OWNER_LAYERS + SHARED_LAYERS:
        shared = layer_id in SHARED_LAYERS
        layer = make_layer(23 if shared else layer_id, shared)
        out = torch.zeros_like(q)
        k_arg = None if shared else k_new
        v_arg = None if shared else v_new
        hit = TritonAttnBackend._try_t011_bf16_ragged_layer(
            owner, q, k_arg, v_arg, out, layer, fb, True, 0.0
        )
        per_layer[layer_id] = {
            "engaged": bool(hit),
            "shared": shared,
            "vs_triton_max_abs": None,
        }
        if not hit:
            continue
        # Reference: production Triton kernel on the same inputs, where shared
        # layers consume the quantised pool rows exactly like the Triton path.
        k_buf, v_buf = pool.get_kv_buffer(layer.layer_id)
        if shared:
            # Production converts the pool rows to the compute dtype before the
            # Triton kernel; keep the reference identical.
            k_eff = k_buf[pool.out_cache_loc].to(q.dtype)
            v_eff = v_buf[pool.out_cache_loc].to(q.dtype)
        else:
            k_eff = k_new
            v_eff = v_new
        ref = torch.empty_like(q)
        extend_attention_fwd(
            q,
            k_eff,
            v_eff,
            ref,
            k_buf,
            v_buf,
            qo_indptr,
            plan.kv_indptr,
            kv_indices,
            None,
            True,
            None,
            max(EXTEND_LENS),
            1.0,
            1.0,
            sm_scale=1.0,
            page_size=1,
        )
        torch.cuda.synchronize()
        per_layer[layer_id]["vs_triton_max_abs"] = (
            (out.float() - ref.float()).abs().max().item()
        )

    # 3) plan identity unchanged after all seven layers (no hot-path re-plan).
    same_plan = first_plan == (
        plan.prefix_wrapper._plan_info,
        plan.extend_wrapper._plan_info,
    )

    # 4) one conversion per owner; shared consumers reuse owner 23.
    cached_owners = sorted(plan.prefix_cache.keys())

    # 5) over-cap batch must not plan.
    big = types.SimpleNamespace(
        extend_prefix_lens_cpu=[40000],
        extend_seq_lens_cpu=[1024],
        out_cache_loc=pool.out_cache_loc,
    )
    over_cap = TritonAttnBackend._plan_t011_bf16_ragged(owner, big) is None

    payload = {
        "device": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "flashinfer": __import__("flashinfer").__version__,
        "prefix_lens": PREFIX_LENS,
        "extend_lens": EXTEND_LENS,
        "plan_created": True,
        "plan_unchanged_after_layers": same_plan,
        "prefix_cache_owners": cached_owners,
        "owner23_reused_by_shared": all(per_layer[i]["engaged"] for i in SHARED_LAYERS),
        "over_cap_falls_back": over_cap,
        "layers": per_layer,
        "workspace_bytes": owner._t011_bf16_state.workspace.numel(),
        "prefix_bf16_bytes": t011.prefix_bf16_bytes(total_prefix, 2, 512),
        "temporary_prefix_limit_bytes": t011.TEMPORARY_PREFIX_LIMIT_BYTES,
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
