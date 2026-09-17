"""R1 hardening: compare Gemma fold set with quant_config=None vs real GGUFConfig."""
from __future__ import annotations
import json, os, sys, types
os.environ.setdefault("MASTER_ADDR","127.0.0.1"); os.environ.setdefault("MASTER_PORT","29651")
_v = types.ModuleType("vllm"); _vc = types.ModuleType("vllm._custom_ops")
def _rot(*a, **k): raise NotImplementedError("stub")
_vc.rotary_embedding=_rot; _v._custom_ops=_vc
sys.modules.setdefault("vllm",_v); sys.modules.setdefault("vllm._custom_ops",_vc)
import torch, gguf
from torch import nn
import sglang
from sglang.srt.distributed import init_distributed_environment, initialize_model_parallel
from sglang.srt.distributed.parallel_state import get_pp_group, get_tp_group, get_world_group
from sglang.srt.layers.layernorm import GemmaRMSNorm
from sglang.srt.layers.quantization.gguf import GGUFConfig
from sglang.srt.models.qwen3_5_text import Qwen3_5ForCausalLM, _gemma_norm_param_names
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

def init_dist():
    init_distributed_environment(world_size=1,rank=0,local_rank=0,
        distributed_init_method="tcp://127.0.0.1:29651",backend="gloo")
    initialize_model_parallel(tensor_model_parallel_size=1,pipeline_model_parallel_size=1,backend="gloo")
    from sglang.srt import runtime_context as rc
    from sglang.srt.server_args import ServerArgs
    rc._CONTEXT.set_server_args(ServerArgs(model_path=".",tp_size=1,pp_size=1))

def overrides():
    tp,pp,wg=get_tp_group(),get_pp_group(),get_world_group()
    return dict(world_size=1,world_rank=0,tp_size=1,tp_rank=0,pp_size=1,pp_rank=0,
        moe_ep_size=1,moe_ep_rank=0,moe_dp_size=1,moe_dp_rank=0,moe_tp_size=1,moe_tp_rank=0,
        attn_tp_size=1,attn_tp_rank=0,attn_cp_size=1,attn_cp_rank=0,dcp_enabled=False,
        dcp_size=1,dcp_rank=0,attn_dcp_size=1,attn_dcp_rank=0,attn_dp_size=1,attn_dp_rank=0,
        world_group=wg.device_group,tp_group=tp.device_group,pp_group=pp.device_group,
        moe_ep_group=tp.device_group,moe_dp_group=tp.device_group,moe_tp_group=tp.device_group,
        attn_tp_group=tp.device_group,attn_cp_group=tp.device_group,dcp_group=tp.device_group)

def build(cfg, qc):
    from sglang.srt.runtime_context import get_parallel
    with get_parallel().override(**overrides()), torch.device("meta"):
        return Qwen3_5ForCausalLM(config=cfg, quant_config=qc, prefix="")

def walk(m):
    s=set()
    for mn,mod in m.named_modules():
        if isinstance(mod,GemmaRMSNorm):
            for pn,_ in mod.named_parameters(recurse=False):
                s.add(f"{mn}.{pn}" if mn else pn)
    return s

def main():
    init_dist()
    out={}
    for key,path in {"m3":"/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
                     "m4":"/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf"}.items():
        cfg=build_gguf_config(path)
        n0=walk(build(cfg,None))
        n1=walk(build(cfg,GGUFConfig()))
        h1=set(_gemma_norm_param_names(build(cfg,GGUFConfig())))
        out[key]={"n_none":len(n0),"n_ggufcfg":len(n1),"sets_equal":n0==n1,
                  "raw_vs_helper_ggufcfg": n1==h1,
                  "ggufcfg_is_gguf": GGUFConfig().get_name()=="gguf"}
    json.dump(out,open(sys.argv[1],"w"),indent=2); print(json.dumps(out,indent=2))

main()
