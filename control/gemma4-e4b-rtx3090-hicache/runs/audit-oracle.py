#!/usr/bin/env python3
"""Audit pinned HF Gemma4 Oracle and fixed-output tolerance against current bytes."""
import hashlib,json,os,sys
from pathlib import Path
import numpy as np
import torch
from transformers import __version__
from safetensors import safe_open
root=Path('/data/sglang-hicache/gemma4'); model=root/'model'; run=root/'runs/targeted-bf16-logits-fixed-same-run'; source=root/'runs/targeted-bf16-request/oracle_layers.py'; tol=json.loads((root/'runs/targeted-bf16-request/tolerance.json').read_text())
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d'
model_sha=sha(model/'model.safetensors'); assert model_sha==expected,(model_sha,expected)
source_text=source.read_text(); assert 'AutoModelForCausalLM.from_pretrained' in source_text and 'trust_remote_code=True' in source_text and 'torch_dtype=torch.bfloat16' in source_text
import transformers.models.gemma4.modeling_gemma4 as hfmod
oracle=torch.load(run/'oracle-positions-1-8-all-layers.pt',map_location='cpu',weights_only=True)
assert oracle['input_ids'].tolist()==[[6974,886,2822,13315,1003,506,7217,236761]]
assert oracle['positions'].tolist()==[[1,2,3,4,5,6,7,8]]
# Validate checkpoint tensor identities and final norm formula against HF code.
with safe_open(model/'model.safetensors',framework='pt',device='cpu') as sf:
 tensors=list(sf.keys()); norm=sf.get_tensor('model.language_model.norm.weight').float()
model_config=json.loads((model/'config.json').read_text())
identity={'transformers_version':__version__,'model_class':'AutoModelForCausalLM / Gemma4ForCausalLM','source_script_sha256':sha(source),'model_revision':'6cd26aaa2357fb2bad8c51699a7558a4d1a965bb','model_safetensors_sha256':model_sha,'config_sha256':sha(model/'config.json'),'hf_modeling_gemma4_sha256':sha(Path(hfmod.__file__)),'oracle_artifact_sha256':sha(run/'oracle-positions-1-8-all-layers.pt'),'checkpoint_keys':len(tensors),'checkpoint_norm_key':'model.language_model.norm.weight','checkpoint_norm_shape':list(norm.shape),'checkpoint_norm_min':norm.min().item(),'checkpoint_norm_max':norm.max().item(),'positions':oracle['positions'].tolist(),'input_ids':oracle['input_ids'].tolist(),'tolerance':tol}
assert __version__=='5.12.1'; assert tol['metrics']['full_vocab_logits_max_abs_error']==0.5 and tol['metrics']['full_vocab_logits_mean_abs_error']==0.1 and tol['metrics']['greedy_token_ids_must_match']
out=Path(sys.argv[1]);out.write_text(json.dumps(identity,indent=2)+'\n');print(json.dumps(identity,indent=2))
