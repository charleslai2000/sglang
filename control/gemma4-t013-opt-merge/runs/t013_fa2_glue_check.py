#!/usr/bin/env python3
"""T013 glue check: the restored FA2 ragged Full extend path on real backend code.

Exercises ``TritonAttnBackend._plan_fa2_ragged_extend`` /
``_run_fa2_ragged_extend`` unbound against a minimal stand-in for ``self``:

* one plan per Forward, unchanged after all seven Full layers;
* one prefix conversion per KV owner, reused by its shared-KV consumers;
* per-layer output against the production Triton kernel on the same inputs;
* every fallback gate (flag, mode, no prefix, over budget, sliding window,
  head geometry, custom mask) returns without engaging.

Run only under the project GPU lock with a bounded timeout.
"""

import argparse
import json
import types

import torch

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd
from sglang.srt.layers.attention import bf16_ragged_extend as ragged
from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
from sglang.srt.model_executor.forward_batch_info import ForwardMode

PREFIX_LENS = [1024, 2048, 512]
EXTEND_LENS = [700, 300, 1500]
OWNER_LAYERS = [5, 11, 17, 23]
SHARED_LAYERS = [29, 35, 41]
HEAD_DIM = 512
NUM_QO = 8
NUM_KV = 2


class FakePool:
    """Owner-keyed FP8 pool with a per-layer write region for new tokens."""

    def __init__(self, owner_ids, k_prefix, v_prefix, k_new, v_new, device):
        self.dtype = torch.float8_e5m2
        self._buffers = {}
        total_prefix = k_prefix.shape[0]
        total_new = k_new.shape[0]
        for owner in owner_ids:
            k = torch.empty(
                (total_prefix + total_new, NUM_KV, HEAD_DIM),
                dtype=torch.float8_e5m2,
                device=device,
            )
            v = torch.empty_like(k)
            k[:total_prefix] = k_prefix
            v[:total_prefix] = v_prefix
            k[total_prefix:] = k_new
            v[total_prefix:] = v_new
            self._buffers[owner] = (k, v)
        self.out_cache_loc = torch.arange(
            total_prefix, total_prefix + total_new, dtype=torch.int64, device=device
        )

    def get_kv_buffer(self, layer_id):
        return self._buffers[layer_id]


class FakeLayer:
    def __init__(self, layer_id, is_shared, **overrides):
        self.qk_head_dim = HEAD_DIM
        self.v_head_dim = HEAD_DIM
        self.tp_q_head_num = NUM_QO
        self.tp_k_head_num = NUM_KV
        self.sliding_window_size = -1
        self.scaling = 1.0
        self.logit_capping_method = "tanh"
        self.logit_cap = None
        self.k_scale = None
        self.v_scale = None
        self.k_scale_float = 1.0
        self.v_scale_float = 1.0
        self.xai_temperature_len = -1
        self.layer_id = layer_id
        self.is_cross_attention = False
        self.receives_none = is_shared
        for key, value in overrides.items():
            setattr(self, key, value)


def make_owner(pool, kv_indices, qo_indptr, device, enable=True):
    meta = type(
        "Meta",
        (),
        {
            "custom_mask": None,
            "mask_indptr": None,
            "kv_indices": kv_indices,
            "kv_indptr": torch.arange(
                len(PREFIX_LENS) + 1, dtype=torch.int32, device=device
            ),
            "qo_indptr": qo_indptr,
        },
    )()
    owner = type(
        "Owner",
        (),
        {
            "enable_fa2_ragged_extend": enable,
            "_fa2_ragged_state": None,
            "_fa2_ragged_plan": None,
            "_fa2_ragged_planned": False,
            "use_mla": False,
            "dcp_size": 1,
            "enable_deterministic": False,
            "_translate_kv_loc": None,
            "page_size": 1,
            "num_head": NUM_QO,
            "num_kv_head": NUM_KV,
            "device": device,
            "token_to_kv_pool": pool,
            "forward_metadata": meta,
        },
    )()
    # Bind the real helper so the unbound entry points find it on ``self``.
    owner._fa2_ragged_layer_supported = types.MethodType(
        TritonAttnBackend._fa2_ragged_layer_supported, owner
    )
    return owner


def make_forward_batch(mode, prefix_lens, extend_lens, out_cache_loc):
    return type(
        "FB",
        (),
        {
            "forward_mode": mode,
            "extend_prefix_lens_cpu": list(prefix_lens),
            "extend_seq_lens_cpu": list(extend_lens),
            "out_cache_loc": out_cache_loc,
        },
    )()


def plan_for(owner, fb, layer):
    plan = owner._fa2_ragged_plan
    if plan is None and not owner._fa2_ragged_planned:
        owner._fa2_ragged_planned = True
        plan = TritonAttnBackend._plan_fa2_ragged_extend(owner, fb, layer)
        owner._fa2_ragged_plan = plan
    return plan


def try_layer(owner, plan, q, k, v, o, layer):
    if plan is None:
        return False
    return TritonAttnBackend._run_fa2_ragged_extend(
        owner, plan, q, k, v, o, layer, layer.logit_cap
    )


def triton_reference(q, k, v, ref, pool, layer, kv_indptr, kv_indices, device):
    k_buf, v_buf = pool.get_kv_buffer(layer.layer_id)
    qo_indptr = torch.tensor(
        [0] + list(torch.cumsum(torch.tensor(EXTEND_LENS), 0).tolist()),
        dtype=torch.int32,
        device=device,
    )
    extend_attention_fwd(
        q,
        k,
        v,
        ref,
        k_buf,
        v_buf,
        qo_indptr,
        kv_indptr,
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
    return ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assert torch.cuda.get_device_capability() == (8, 6)
    device, dtype = "cuda", torch.bfloat16
    torch.manual_seed(4242)

    total_prefix, total_new = sum(PREFIX_LENS), sum(EXTEND_LENS)
    q = torch.randn((total_new, NUM_QO, HEAD_DIM), device=device, dtype=dtype) * 0.08
    k_new = (
        torch.randn((total_new, NUM_KV, HEAD_DIM), device=device, dtype=dtype) * 0.08
    )
    v_new = torch.randn_like(k_new) * 0.08
    k_prefix = (torch.randn((total_prefix, NUM_KV, HEAD_DIM), device=device) * 0.08).to(
        torch.float8_e5m2
    )
    v_prefix = (torch.randn((total_prefix, NUM_KV, HEAD_DIM), device=device) * 0.08).to(
        torch.float8_e5m2
    )

    pool = FakePool(OWNER_LAYERS, k_prefix, v_prefix, k_new, v_new, device)
    kv_indices = torch.arange(total_prefix, device=device, dtype=torch.int64)
    qo_indptr = torch.tensor(
        [0] + list(torch.cumsum(torch.tensor(EXTEND_LENS), 0).tolist()),
        dtype=torch.int32,
        device=device,
    )
    owner = make_owner(pool, kv_indices, qo_indptr, device)
    fb = make_forward_batch(
        ForwardMode.EXTEND, PREFIX_LENS, EXTEND_LENS, pool.out_cache_loc
    )
    first_layer = FakeLayer(OWNER_LAYERS[0], False)

    plan = plan_for(owner, fb, first_layer)
    assert plan is not None, "plan should be created for a qualifying prefill"
    first_plan = (plan.prefix_wrapper._plan_info, plan.extend_wrapper._plan_info)

    per_layer = {}
    for layer_id in OWNER_LAYERS + SHARED_LAYERS:
        shared = layer_id in SHARED_LAYERS
        layer = FakeLayer(OWNER_LAYERS[3] if shared else layer_id, shared)
        out = torch.zeros_like(q)
        # Shared consumers reach the backend exactly like production: k = v = None,
        # and forward_extend resolves the owner's new rows before dispatching.
        if shared:
            k_buf, v_buf = pool.get_kv_buffer(layer.layer_id)
            k_arg = k_buf[pool.out_cache_loc].to(q.dtype)
            v_arg = v_buf[pool.out_cache_loc].to(q.dtype)
        else:
            k_arg, v_arg = k_new, v_new
        hit = try_layer(owner, plan, q, k_arg, v_arg, out, layer)
        per_layer[layer_id] = {"engaged": bool(hit), "shared": shared}
        if not hit:
            continue
        ref = torch.empty_like(q)
        triton_reference(
            q, k_arg, v_arg, ref, pool, layer, plan.kv_indptr, kv_indices, device
        )
        per_layer[layer_id]["vs_triton_max_abs"] = (
            (out.float() - ref.float()).abs().max().item()
        )

    same_plan = first_plan == (
        plan.prefix_wrapper._plan_info,
        plan.extend_wrapper._plan_info,
    )
    cached_owners = sorted(str(key) for key in plan.prefix_cache)

    # Fallback gates must not plan and must not run.
    def fallback(mode=None, prefix=None, layer_override=None, enable=True):
        pool_fb = make_forward_batch(
            mode or ForwardMode.EXTEND,
            prefix if prefix is not None else PREFIX_LENS,
            EXTEND_LENS,
            pool.out_cache_loc,
        )
        owner_fb = make_owner(pool, kv_indices, qo_indptr, device, enable=enable)
        layer = FakeLayer(OWNER_LAYERS[0], False, **(layer_override or {}))
        p = plan_for(owner_fb, pool_fb, layer)
        ran = False
        if p is not None:
            out = torch.zeros_like(q)
            ran = try_layer(owner_fb, p, q, k_new, v_new, out, layer)
        return {"planned": p is not None, "ran": bool(ran)}

    checks = {
        "flag_disabled": fallback(enable=False),
        "decode_mode": fallback(mode=ForwardMode.DECODE),
        "no_prefix": fallback(prefix=[0, 0, 0]),
        "over_budget": fallback(prefix=[40000, 0, 0]),
        "sliding_window": fallback(layer_override={"sliding_window_size": 512}),
        "head_dim_256": fallback(
            layer_override={"qk_head_dim": 256, "v_head_dim": 256}
        ),
        "custom_mask": fallback(layer_override={}),
    }

    payload = {
        "device": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "flashinfer": __import__("flashinfer").__version__,
        "prefix_lens": PREFIX_LENS,
        "extend_lens": EXTEND_LENS,
        "plan_created": True,
        "plan_unchanged_after_layers": same_plan,
        "prefix_cache_entries": cached_owners,
        "owners_converted": owner._fa2_ragged_state.stats["owner_conversions"],
        "shared_reuses": owner._fa2_ragged_state.stats["shared_reuses"],
        "layers": per_layer,
        "coverage": dict(owner._fa2_ragged_state.stats),
        "workspace_bytes": owner._fa2_ragged_state.workspace.numel(),
        "prefix_bf16_bytes": ragged.prefix_bf16_bytes(total_prefix, NUM_KV, HEAD_DIM),
        "prefix_budget_bytes": ragged.prefix_budget_bytes(),
        "fallbacks": checks,
    }

    # The custom-mask gate needs a real mask to be meaningful; assert separately.
    owner_mask = make_owner(pool, kv_indices, qo_indptr, device)
    owner_mask.forward_metadata.custom_mask = torch.zeros(1, device=device)
    ok = TritonAttnBackend._plan_fa2_ragged_extend(
        owner_mask, fb, FakeLayer(OWNER_LAYERS[0], False)
    )
    payload["fallbacks"]["custom_mask"] = {"planned": ok is not None, "ran": False}
    payload["all_layers_engaged"] = all(
        per_layer[layer_id]["engaged"] for layer_id in per_layer
    )
    payload["max_vs_triton"] = max(
        (
            per_layer[layer_id]["vs_triton_max_abs"]
            for layer_id in per_layer
            if "vs_triton_max_abs" in per_layer[layer_id]
        ),
        default=None,
    )
    with open(args.out, "w") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
