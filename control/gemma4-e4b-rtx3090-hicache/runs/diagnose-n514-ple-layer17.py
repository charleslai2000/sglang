import torch
from pathlib import Path
from transformers import AutoModelForCausalLM
from compressed_tensors.compressors import ModelCompressor
root=Path('/data/sglang-hicache/gemma4/runs/20261022T172926Z-e5m2-swa-boundary');fid='e154f270660c4b83a79dfbf467aa9d0a';lid=17
hf=torch.load(root/'hf-oracle/n514-layer17-ple-bound.pt',weights_only=True)
m=AutoModelForCausalLM.from_pretrained('/data/sglang-hicache/gemma4/model',torch_dtype=torch.bfloat16,device_map='cpu',trust_remote_code=True,low_cpu_mem_usage=True).eval();ModelCompressor.from_compression_config(m.config.quantization_config).decompress_model(m)
for mod in m.modules():
 if isinstance(mod,torch.nn.Linear): mod.to('cuda')
t=m.model.language_model;l=t.layers[lid]; rec={}
def hk(name):
 def f(mod,args,out):rec[name]=(out[0] if isinstance(out,tuple) else out).detach().float().cpu()
 return f
for n in ['input_layernorm','post_attention_layernorm','pre_feedforward_layernorm','mlp','post_feedforward_layernorm','per_layer_input_gate','per_layer_projection','post_per_layer_input_norm']:
 getattr(l,n).register_forward_hook(hk(n))
l.self_attn.config._attn_implementation='eager';x=torch.load(root/'bf16'/f'forward.{fid}.layer_output.16',weights_only=True)['output'].unsqueeze(0).to('cuda',torch.bfloat16);ple=hf['value'].unsqueeze(0).to('cuda',torch.bfloat16);pos=torch.tensor([hf['positions']],device='cuda');mask=torch.triu(torch.full((1,1,514,514),float('-inf'),device='cuda',dtype=x.dtype),diagonal=1)
with torch.inference_mode(): y=l(hidden_states=x,per_layer_input=ple,position_embeddings=t.rotary_emb(x,pos,l.self_attn.layer_type),attention_mask=mask,position_ids=pos,shared_kv_states={},past_key_values=None)
sg=torch.load(root/'bf16'/f'forward.{fid}.layer_output.17',weights_only=True)['output'].float().cpu()
for k,v in rec.items():
 s='attention input: not captured'
 print(k,tuple(v.shape),float(v.norm()),float(v.abs().max()))
print('Y CPU/HF rel,max',float((sg-y.float().cpu()[0]).norm()/sg.norm()),float((sg-y.float().cpu()[0]).abs().max()))
