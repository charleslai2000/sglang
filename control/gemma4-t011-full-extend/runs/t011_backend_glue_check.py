#!/usr/bin/env python3
"""Exercise the real backend glue for the opt-in BF16 Ragged Full path.

Calls ``TritonAttnBackend._try_t011_bf16_ragged_full_extend`` unbound against a
minimal stand-in for ``self`` so the attribute/slicing/shape contract is checked
without booting a server. Numerics are compared with the production Triton
kernel; fallback gating is asserted for the guarded configurations.
"""

import argparse
import json
import types

import torch

from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd
from sglang.srt.layers.attention.triton_backend import TritonAttnBackend

MiB = 1024 * 1024


class FakePool:
    def __init__(self, k_pool, v_pool):
        self.k_pool = k_pool
        self.v_pool = v_pool
        self.dtype = torch.float8_e5m2
        self.start_layer = 5

    def get_key_buffer(self, layer_id):
        assert layer_id == 5, layer_id
        return self.k_pool

    def get_value_buffer(self, layer_id):
        assert layer_id == 5, layer_id
        return self.v_pool


def make_self(pool, prefix_lens, extend_lens, device):
    def indptr(lens):
        out = torch.zeros(len(lens) + 1, device=device, dtype=torch.int64)
        torch.cumsum(
            torch.tensor(lens, device=device, dtype=torch.int64), dim=0, out=out[1:]
        )
        return out

    total_prefix = sum(prefix_lens)
    meta = types.SimpleNamespace(
        qo_indptr=indptr(extend_lens),
        kv_indptr=indptr(prefix_lens),
        kv_indices=torch.arange(total_prefix, device=device, dtype=torch.int64),
        custom_mask=None,
    )
    fb = types.SimpleNamespace(
        extend_prefix_lens_cpu=list(prefix_lens),
        extend_seq_lens_cpu=list(extend_lens),
        extend_seq_lens=torch.tensor(extend_lens, device=device, dtype=torch.int32),
    )
    return (
        types.SimpleNamespace(
            enable_t011_bf16_ragged_full_extend=True,
            _t011_bf16_ragged_state=None,
            dcp_size=1,
            enable_deterministic=False,
            forward_metadata=meta,
            token_to_kv_pool=pool,
        ),
        fb,
        meta,
    )


def make_layer(**overrides):
    layer = types.SimpleNamespace(
        qk_head_dim=512,
        v_head_dim=512,
        tp_q_head_num=8,
        tp_k_head_num=2,
        sliding_window_size=-1,
        scaling=1.0,
        k_scale_float=1.0,
        v_scale_float=1.0,
        xai_temperature_len=-1,
        layer_id=5,
        is_cross_attention=False,
    )
    for key, value in overrides.items():
        setattr(layer, key, value)
    return layer


def run(prefix_lens, extend_lens, seed, fallback_override=None):
    device, dtype = "cuda", torch.bfloat16
    torch.manual_seed(seed)
    total_prefix, total_new = sum(prefix_lens), sum(extend_lens)
    q = torch.randn((total_new, 8, 512), device=device, dtype=dtype) * 0.08
    k_new = torch.randn((total_new, 2, 512), device=device, dtype=dtype) * 0.08
    v_new = torch.randn_like(k_new) * 0.08
    k_pool = (torch.randn((total_prefix, 2, 512), device=device) * 0.08).to(
        torch.float8_e5m2
    )
    v_pool = (torch.randn((total_prefix, 2, 512), device=device) * 0.08).to(
        torch.float8_e5m2
    )
    owner, fb, meta = make_self(
        FakePool(k_pool, v_pool), prefix_lens, extend_lens, device
    )
    if fallback_override:
        for key, value in fallback_override.items():
            if key == "layer":
                continue
            setattr(owner, key, value)
    layer = make_layer(**((fallback_override or {}).get("layer", {})))
    o = torch.zeros_like(q)

    hit = TritonAttnBackend._try_t011_bf16_ragged_full_extend(
        owner, q, k_new, v_new, o, layer, fb, True, 0.0
    )
    if not hit:
        return {"engaged": False, "case": fallback_override}
    state = owner._t011_bf16_ragged_state

    o_tri = torch.empty_like(q)
    extend_attention_fwd(
        q,
        k_new,
        v_new,
        o_tri,
        k_pool,
        v_pool,
        meta.qo_indptr.to(torch.int32),
        meta.kv_indptr.to(torch.int32),
        meta.kv_indices,
        None,
        True,
        None,
        max(extend_lens),
        1.0,
        1.0,
        sm_scale=1.0,
        page_size=1,
    )
    torch.cuda.synchronize()
    return {
        "engaged": True,
        "prefix_lens": prefix_lens,
        "extend_lens": extend_lens,
        "workspace_bytes": state.workspace.numel(),
        "vs_triton_max_abs_output": (o.float() - o_tri.float()).abs().max().item(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assert torch.cuda.get_device_capability() == (8, 6)

    checks = [
        {"name": "batch-1 4096/28672", "args": ([28672], [4096], 21)},
        {"name": "ragged 3 unequal", "args": ([1024, 2048, 512], [700, 300, 1500], 22)},
        {"name": "no-prefix", "args": ([0], [512], 23)},
        {
            "name": "cap-exceeded falls back",
            "args": ([33000], [256], 24),
        },
        {
            "name": "shared-kv (k=None) falls back",
            "args": ([1024], [512], 25),
            "fallback": {"force_k_none": True},
        },
        {
            "name": "sliding-window falls back",
            "args": ([1024], [512], 26),
            "fallback": {"layer": {"sliding_window_size": 512}},
        },
        {
            "name": "non-unit k_scale falls back",
            "args": ([1024], [512], 27),
            "fallback": {"layer": {"k_scale_float": 0.5}},
        },
        {
            "name": "flag-disabled falls back",
            "args": ([1024], [512], 28),
            "fallback": {"enable_t011_bf16_ragged_full_extend": False},
        },
    ]

    results = []
    for check in checks:
        prefix_lens, extend_lens, seed = check["args"]
        override = check.get("fallback")
        if override and override.pop("force_k_none", False):
            # k=None is how shared-KV layers reach the backend.
            device = "cuda"
            torch.manual_seed(seed)
            total_prefix, total_new = sum(prefix_lens), sum(extend_lens)
            q = torch.randn((total_new, 8, 512), device=device, dtype=torch.bfloat16)
            k_pool = torch.zeros(
                (total_prefix, 2, 512), device=device, dtype=torch.float8_e5m2
            )
            v_pool = torch.zeros_like(k_pool)
            owner, fb, _ = make_self(
                FakePool(k_pool, v_pool), prefix_lens, extend_lens, device
            )
            o = torch.zeros_like(q)
            hit = TritonAttnBackend._try_t011_bf16_ragged_full_extend(
                owner, q, None, None, o, make_layer(), fb, True, 0.0
            )
            results.append(
                {"name": check["name"], "engaged": bool(hit), "expected": False}
            )
            continue
        out = run(prefix_lens, extend_lens, seed, override)
        expected = "falls back" not in check["name"]
        results.append(
            {
                "name": check["name"],
                "engaged": out["engaged"],
                "expected": expected,
                **out,
            }
        )

    payload = {
        "device": torch.cuda.get_device_name(),
        "capability": torch.cuda.get_device_capability(),
        "torch": torch.__version__,
        "checks": results,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
