"""Independent R1 enumeration: fold set exactness for the real qwen3_5 tree."""
from __future__ import annotations
import collections, json, os, sys
os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
os.environ.setdefault("MASTER_PORT", "29631")

import torch
from torch import nn
import types
# Construction-only shim: CPU-only platform selection in rotary_embedding/base.py
# falls through to `from vllm._custom_ops import rotary_embedding`. The meta build
# never runs forward, so this symbol is never invoked. Module *names* enumerated
# below are independent of this shim.
_v = types.ModuleType("vllm"); _vc = types.ModuleType("vllm._custom_ops")
def _rot(*a, **k): raise NotImplementedError("stub")
_vc.rotary_embedding = _rot; _v._custom_ops = _vc
sys.modules.setdefault("vllm", _v); sys.modules.setdefault("vllm._custom_ops", _vc)
import sglang
from sglang.srt.distributed import init_distributed_environment, initialize_model_parallel
from sglang.srt.distributed.parallel_state import get_pp_group, get_tp_group, get_world_group
from sglang.srt.layers.layernorm import GemmaRMSNorm
from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
from sglang.srt.models.qwen3_5_text import (
    Qwen3_5ForCausalLM, _gemma_norm_param_names, _gguf_runtime_param_name,
)
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

MODELS = {
    "m3": "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
    "m4": "/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf",
}

def init_dist():
    init_distributed_environment(world_size=1, rank=0, local_rank=0,
        distributed_init_method="tcp://127.0.0.1:29631", backend="gloo")
    initialize_model_parallel(tensor_model_parallel_size=1, pipeline_model_parallel_size=1, backend="gloo")
    from sglang.srt import runtime_context as rc
    from sglang.srt.server_args import ServerArgs
    rc._CONTEXT.set_server_args(ServerArgs(model_path=".", tp_size=1, pp_size=1))

def overrides():
    tp, pp, wg = get_tp_group(), get_pp_group(), get_world_group()
    return dict(world_size=1, world_rank=0, tp_size=1, tp_rank=0, pp_size=1, pp_rank=0,
        moe_ep_size=1, moe_ep_rank=0, moe_dp_size=1, moe_dp_rank=0, moe_tp_size=1, moe_tp_rank=0,
        attn_tp_size=1, attn_tp_rank=0, attn_cp_size=1, attn_cp_rank=0, dcp_enabled=False,
        dcp_size=1, dcp_rank=0, attn_dcp_size=1, attn_dcp_rank=0, attn_dp_size=1, attn_dp_rank=0,
        world_group=wg.device_group, tp_group=tp.device_group, pp_group=pp.device_group,
        moe_ep_group=tp.device_group, moe_dp_group=tp.device_group, moe_tp_group=tp.device_group,
        attn_tp_group=tp.device_group, attn_cp_group=tp.device_group, dcp_group=tp.device_group)

def build_meta(cfg):
    from sglang.srt.runtime_context import get_parallel
    with get_parallel().override(**overrides()), torch.device("meta"):
        return Qwen3_5ForCausalLM(config=cfg, quant_config=None, prefix="")

def main():
    init_dist()
    import gguf
    out = {"sglang_file": sglang.__file__, "models": {}}
    for key, path in MODELS.items():
        cfg = build_gguf_config(path)
        name_map = build_qwen35_name_map(cfg)
        meta = build_meta(cfg)

        # (1) my own walk of GemmaRMSNorm modules -> runtime param names, RAW
        raw_gemma = {}
        for mn, mod in meta.named_modules():
            if isinstance(mod, GemmaRMSNorm):
                for pn, p in mod.named_parameters(recurse=False):
                    full = f"{mn}.{pn}" if mn else pn
                    raw_gemma[full] = (type(mod).__name__, tuple(p.shape))
        # (2) helper set
        helper = set(_gemma_norm_param_names(meta))
        # (3) full runtime param set
        all_params = {n for n, _ in meta.named_parameters()}
        # (4) incoming feedable HF names (from authoritative name map)
        reader = gguf.GGUFReader(path)
        feed = sorted({name_map[t.name] for t in reader.tensors if t.name in name_map})

        # collision analysis on the normalization
        norm_map = collections.defaultdict(list)
        for n in all_params:
            norm_map[_gguf_runtime_param_name(n)].append(n)
        collisions = {k: v for k, v in norm_map.items() if len(v) > 1}

        # (A) false-negative: Gemma param reachable by an incoming name but NOT in helper
        incoming_norm = {_gguf_runtime_param_name(n): n for n in feed}
        gemma_reached = {}   # gemma runtime param -> incoming name that reaches it
        gemma_unreached = []
        for full in raw_gemma:
            key_n = _gguf_runtime_param_name(full)
            # find incoming whose normalized == key_n
            hit = None
            for inc in feed:
                if _gguf_runtime_param_name(inc) == key_n:
                    hit = inc; break
            if hit is None:
                gemma_unreached.append(full)
            else:
                gemma_reached[full] = hit
                if full not in helper:
                    print(f"!!! {key}: Gemma param {full} reachable but NOT in helper set")

        # (B) false-positive: incoming name folded (norm-name in helper) but dest not GemmaRMSNorm
        false_pos = []
        for inc in feed:
            if _gguf_runtime_param_name(inc) in helper:
                # destination runtime param
                dest = incoming_norm.get(_gguf_runtime_param_name(inc))
                # params_dict keys are the raw names (model. prefix intact)
                if dest is None:
                    # maybe dest is model.X while inc is model.X.self_attn...; resolve
                    cand = [n for n in all_params if _gguf_runtime_param_name(n) == _gguf_runtime_param_name(inc)]
                    dest = cand[0] if cand else None
                if dest is not None and raw_gemma.get(dest) is None:
                    false_pos.append((inc, dest))

        # (C) helper vs raw gemma (raw, unnormalized): helper should be normalized raw
        helper_expected = {_gguf_runtime_param_name(n) for n in raw_gemma}
        out["models"][key] = {
            "n_total_gguf_tensors": len(reader.tensors),
            "n_feedable": len(feed),
            "n_runtime_params": len(all_params),
            "n_raw_gemma_params": len(raw_gemma),
            "gemma_role_counts": dict(sorted(collections.Counter(
                ("model.norm" if n == "model.norm.weight" else
                 "input_layernorm" if n.endswith(".input_layernorm.weight") else
                 "post_attention_layernorm" if n.endswith(".post_attention_layernorm.weight") else
                 "q_norm" if n.endswith(".q_norm.weight") else
                 "k_norm" if n.endswith(".k_norm.weight") else "OTHER:"+n)
                for n in raw_gemma).items())),
            "helper_equals_normalized_raw_gemma": helper == helper_expected,
            "helper_minus_expected": sorted(helper - helper_expected)[:5],
            "expected_minus_helper": sorted(helper_expected - helper)[:5],
            "n_gemma_reached_by_incoming": len(gemma_reached),
            "gemma_unreached_by_incoming": gemma_unreached,
            "false_positive_folded_non_gemma": false_pos,
            "normalization_collisions": collisions,
            "linear_attn_norm_in_helper": any("linear_attn.norm" in n for n in helper),
            "sample_raw_gemma_names": sorted(raw_gemma)[:4] + sorted(raw_gemma)[-3:],
            "sample_incoming_qk": sorted(n for n in feed if "q_norm" in n or "k_norm" in n)[:3],
        }
    json.dump(out, open(sys.argv[1], "w"), indent=2)
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
