"""R1 corrected: exact fold set, no false pos/neg, real runtime names."""
from __future__ import annotations
import collections, json, os, sys, types
os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
os.environ.setdefault("MASTER_PORT", "29641")
_v = types.ModuleType("vllm"); _vc = types.ModuleType("vllm._custom_ops")
def _rot(*a, **k): raise NotImplementedError("stub")
_vc.rotary_embedding = _rot; _v._custom_ops = _vc
sys.modules.setdefault("vllm", _v); sys.modules.setdefault("vllm._custom_ops", _vc)

import torch, gguf
from torch import nn
import sglang
from sglang.srt.distributed import init_distributed_environment, initialize_model_parallel
from sglang.srt.distributed.parallel_state import get_pp_group, get_tp_group, get_world_group
from sglang.srt.layers.layernorm import GemmaRMSNorm
from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
from sglang.srt.models.qwen3_5_text import Qwen3_5ForCausalLM, _gemma_norm_param_names, _gguf_runtime_param_name, _gguf_fold_absolute_norms
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

MODELS = {"m3": "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
          "m4": "/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf"}

def init_dist():
    init_distributed_environment(world_size=1, rank=0, local_rank=0,
        distributed_init_method="tcp://127.0.0.1:29641", backend="gloo")
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
    res = {"sglang_file": sglang.__file__, "models": {}}
    for key, path in MODELS.items():
        cfg = build_gguf_config(path)
        name_map = build_qwen35_name_map(cfg)
        meta = build_meta(cfg)
        raw = {}
        for mn, mod in meta.named_modules():
            if isinstance(mod, GemmaRMSNorm):
                for pn, _ in mod.named_parameters(recurse=False):
                    raw[(f"{mn}.{pn}" if mn else pn)] = type(mod).__name__
        all_params = [n for n, _ in meta.named_parameters()]
        helper = set(_gemma_norm_param_names(meta))
        reader = gguf.GGUFReader(path)
        feed = sorted({name_map[t.name] for t in reader.tensors if t.name in name_map})

        norm_to_params = collections.defaultdict(list)
        for n in all_params:
            norm_to_params[_gguf_runtime_param_name(n)].append(n)
        collisions = {k: v for k, v in norm_to_params.items() if len(v) > 1}

        folded, unfolded, falsepos, unreached = [], [], [], []
        for inc in feed:
            nk = _gguf_runtime_param_name(inc)
            dests = norm_to_params.get(nk, [])
            is_gemma_dest = any(d in raw for d in dests)
            will_fold = nk in helper
            if will_fold:
                folded.append(inc)
                if not is_gemma_dest:
                    falsepos.append({"incoming": inc, "resolved_params": dests})
            else:
                if is_gemma_dest:
                    unreached.append({"incoming": inc, "resolved_params": dests})
        # every gemma param must be reached by >=1 folded incoming
        reached = set()
        for inc in folded:
            nk = _gguf_runtime_param_name(inc)
            for d in norm_to_params.get(nk, []):
                reached.add(d)
        missed = sorted(set(raw) - reached)

        res["models"][key] = {
            "n_feedable": len(feed),
            "n_gemma": len(raw),
            "helper_equals_norm_raw": helper == {_gguf_runtime_param_name(n) for n in raw},
            "normalization_collisions": collisions,
            "n_folded_incoming": len(folded),
            "false_positive_folded_non_gemma": falsepos,
            "gemma_dest_unreached": unreached,
            "gemma_params_missed": missed,
            "qk_runtime_names_sample": [n for n in sorted(raw) if n.endswith(("q_norm.weight","k_norm.weight"))][:3],
            "input_ln_sample": [n for n in sorted(raw) if "input_layernorm" in n][:2],
            "linear_attn_in_helper": any("linear_attn.norm" in n for n in helper),
            "raw_role_counts": dict(sorted(collections.Counter(
                ("model.norm" if n=="model.norm.weight" else "input_ln" if n.endswith(".input_layernorm.weight")
                 else "post_attn_ln" if n.endswith(".post_attention_layernorm.weight")
                 else "q_norm" if n.endswith(".q_norm.weight") else "k_norm" if n.endswith(".k_norm.weight")
                 else "OTHER:"+n) for n in raw).items())),
        }
    json.dump(res, open(sys.argv[1], "w"), indent=2)
    print(json.dumps(res, indent=2)[:6000])

if __name__ == "__main__":
    main()
