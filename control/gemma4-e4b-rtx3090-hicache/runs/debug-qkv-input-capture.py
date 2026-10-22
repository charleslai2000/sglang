#!/usr/bin/env python3
"""Instrument only exact-request HF/SGLang layer-17 projection inputs and outputs.

Usage: debug-qkv-input-capture.py RUN_DIR OUTPUT.pt
"""
import json, sys
from pathlib import Path
import numpy as np, torch
from compressed_tensors.quantization.lifecycle.forward import dequantize
from transformers import AutoModelForCausalLM

run=Path(sys.argv[1]); out=Path(sys.argv[2]); root=run/'bf16'; component_dir=run/'components'/'component'
manifest_pairs=[(p,json.loads(p.read_text())) for p in root.glob('forward.*.manifest')]
manifest=next((m for _,m in manifest_pairs if m.get('forward_mode')=='EXTEND' and len(m.get('input_ids',[]))==514 and m.get('model_identity',{}).get('model_sha256')=='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d'),None)
if manifest is None: raise RuntimeError('exact N514 manifest not found')
fid=manifest['forward_id'];rid=manifest['rid'][0]
def load_comp(boundary):
 x=json.loads((component_dir/f'component.{rid}.{fid}.layer17.{boundary}.json').read_text())
 assert x['forward_id']==fid and x['rid']==rid and x['forward_mode']=='EXTEND' and x['extend_prefix_lens']==[0] and x['extend_seq_lens']==[514]
 assert x['step_input_ids']==manifest['input_ids'] and x['step_positions']==manifest['positions'] and x['shape'][0]==514
 return torch.tensor(x['value']).float()
attn_input=load_comp('attention_norm_input')
model=AutoModelForCausalLM.from_pretrained('/data/sglang-hicache/gemma4/model',torch_dtype=torch.bfloat16,device_map='cpu',trust_remote_code=True,low_cpu_mem_usage=True).eval()
layer=model.model.language_model.layers[17]
def dequant(linear):
 if not hasattr(linear,'weight_packed'): return
 args=linear.quantization_scheme.weights; rows,cols=map(int,linear.weight_shape.tolist());packed=linear.weight_packed.cpu().numpy().astype(np.uint32,copy=True);u=np.empty((rows,cols),np.uint32)
 for i in range(8):u[:,i::8]=packed&15;packed>>=4
 w=dequantize(torch.from_numpy(u.astype(np.int32))-8,linear.weight_scale.cpu(),args=args,dtype=torch.bfloat16)
 for k in ('weight_packed','weight_scale','weight_shape'): del linear._parameters[k]
 linear.register_parameter('weight',torch.nn.Parameter(w,requires_grad=False))
for nm in ('q_proj','k_proj','v_proj'): dequant(getattr(layer.self_attn,nm))
records={'rid':rid,'forward_id':fid,'input_ids':manifest['input_ids'],'positions':manifest['positions'],'source_hidden':torch.load(root/f'forward.{fid}.layer_output.16',weights_only=True)['output'].float(),'input_layernorm':attn_input}
for name in ('q_proj','k_proj','v_proj'):
 x=getattr(layer.self_attn,name); inp=x.register_forward_pre_hook(lambda m,args,n=name: records.__setitem__(n+'_input',args[0].detach().float().cpu())); hook=x.register_forward_hook(lambda m,args,out,n=name: records.__setitem__(n+'_output',out.detach().float().cpu()));
 with torch.inference_mode(): x(attn_input.to(torch.bfloat16))
 inp.remove();hook.remove()
for b in ('q','k','v'): records['sglang_'+b]=load_comp(b)
out.parent.mkdir(parents=True,exist_ok=True);torch.save(records,out);print(out)
