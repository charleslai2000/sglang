"""Independent R2: per-tensor delta through the real loader (norm set + small controls)."""
from __future__ import annotations
import json, os, sys, types
os.environ.setdefault("MASTER_ADDR","127.0.0.1"); os.environ.setdefault("MASTER_PORT","29661")
_v = types.ModuleType("vllm"); _vc = types.ModuleType("vllm._custom_ops")
def _rot(*a, **k): raise NotImplementedError("stub")
_vc.rotary_embedding=_rot; _v._custom_ops=_vc
sys.modules.setdefault("vllm",_v); sys.modules.setdefault("vllm._custom_ops",_vc)
import torch, gguf
from torch import nn
import sglang
from sglang.srt.distributed import init_distributed_environment, initialize_model_parallel
from sglang.srt.distributed.parallel_state import get_pp_group, get_tp_group, get_world_group
from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
from sglang.srt.models.qwen3_5_text import Qwen3_5ForCausalLM, _gemma_norm_param_names, _gguf_runtime_param_name
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

def init_dist():
    init_distributed_environment(world_size=1,rank=0,local_rank=0,
        distributed_init_method="tcp://127.0.0.1:29661",backend="gloo")
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

class _Capture(nn.Module):
    def __init__(self): super().__init__(); self.captured={}
    def load_weights(self, body_weights): self.captured=dict(body_weights); return set(self.captured)
class _FakeSelf(nn.Module):
    def __init__(self, meta): super().__init__()
    def __init__(self, meta):
        super().__init__(); self.config=types.SimpleNamespace(tie_word_embeddings=False)
        self._is_gguf=True; self.model=_Capture(); self._meta=meta
    def named_modules(self,*a,**k): return self._meta.named_modules(*a,**k)
    def named_parameters(self,*a,**k): return iter(())

CONTROLS=("ssm_norm.weight","ssm_dt.bias","ssm_conv1d.weight","attn_q_norm.weight")
def keep(name): return ("norm" in name) or name.endswith("ssm_dt.bias")

def main():
    init_dist()
    from sglang.srt.runtime_context import get_parallel
    out={}
    for key,path in {"m3":"/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
                     "m4":"/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf"}.items():
        cfg=build_gguf_config(path); nm=build_qwen35_name_map(cfg)
        with get_parallel().override(**overrides()), torch.device("meta"):
            meta=Qwen3_5ForCausalLM(config=cfg, quant_config=None, prefix="")
        reader=gguf.GGUFReader(path)
        raw={}; weights=[]
        for t in reader.tensors:
            if not keep(t.name): continue
            hf=nm.get(t.name)
            if hf is None: continue
            tt=torch.tensor(t.data); raw[hf]=tt; weights.append((hf,tt))
        fake=_FakeSelf(meta)
        Qwen3_5ForCausalLM.load_weights(fake, weights)
        folder=set(_gemma_norm_param_names(meta))
        n_m1=n_0=0; folded_nonzero=[]; unfolded_shift=[]; fold_names=[]; unfolded_names=[]
        for name,t in fake.model.captured.items():
            full="model."+name
            if full not in raw: continue
            r=raw[full]; d=(t.float()-r.float())
            is_fold = _gguf_runtime_param_name(full) in folder
            uniq=torch.unique(d)
            exactly_m1 = (uniq.numel()==1 and float(uniq[0])==-1.0)
            exactly_0  = bool(torch.all(d==0))
            if is_fold:
                fold_names.append(full)
                if exactly_m1: n_m1+=1
                else: folded_nonzero.append({"name":full,"d":uniq.tolist()[:4]})
            else:
                unfolded_names.append(full)
                if exactly_0: n_0+=1
                else: unfolded_shift.append({"name":full,"d":uniq.tolist()[:4]})
        out[key]={"n_filtered_tensors":len(weights),"n_captured":len(fake.model.captured),
                  "n_fold_names":len(fold_names),"n_folded_shifted_m1":n_m1,
                  "folded_not_m1":folded_nonzero,
                  "n_nonfold_names":len(unfolded_names),"n_nonfold_zero":n_0,
                  "nonfold_shifted":unfolded_shift[:5],
                  "control_ssm_norm_present": any("ssm_norm" in n for n in unfolded_names)}
    json.dump(out,open(sys.argv[1],"w"),indent=2); print(json.dumps(out,indent=2))
main()
