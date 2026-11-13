#!/usr/bin/env python3
"""Inspect Gemma4 config, shared-KV owner/type sequence and checkpoint scale tensors."""
import json
from pathlib import Path
from safetensors import safe_open
root=Path('/data/sglang-hicache/gemma4/model'); c=json.loads((root/'config.json').read_text()); t=c.get('text_config',c)
L=t['num_hidden_layers']; shared=t.get('num_kv_shared_layers',0); first=L-shared; types=t.get('layer_types',[])
print(json.dumps({'model_type':c.get('model_type'),'text_layers':L,'shared_layers':shared,'first_shared_layer':first,'swa_window':t.get('sliding_window'),'num_types':len(types),'layer_types':types},indent=2))
with safe_open(str(root/'model.safetensors'),framework='pt',device='cpu') as f:
 keys=list(f.keys())
 for i in range(L):
  if i>=first or i in [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]:
   q=[k for k in keys if k.startswith(f'model.layers.{i}.') and ('k_proj' in k or 'v_proj' in k or 'k_norm' in k or 'v_norm' in k)]
   print(f'layer={i:02d} type={types[i] if types else "?"} shared={i>=first} kv_tensors={q}')
 print('kv_scale_keys',[k for k in keys if 'kv_scale' in k.lower() or 'k_scale' in k.lower() or 'v_scale' in k.lower()][:100])
