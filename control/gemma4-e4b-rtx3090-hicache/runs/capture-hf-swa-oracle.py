#!/usr/bin/env python3
"""Run the independent pinned HF Gemma4 oracle on preserved SWA-boundary IDs."""
import json,sys,hashlib
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM
run=Path(sys.argv[1]); model_path=Path('/data/sglang-hicache/gemma4/model')
torch.set_num_threads(8)
m=AutoModelForCausalLM.from_pretrained(model_path,torch_dtype=torch.bfloat16,device_map='cpu',trust_remote_code=True,low_cpu_mem_usage=True).eval()
for n in (510,511,512,513,514):
 ids=json.loads((run/f'n{n}/e5m2-request.json').read_text())['prompt']
 pos=torch.arange(1,len(ids)+1).unsqueeze(0)
 with torch.inference_mode(): r=m(input_ids=torch.tensor([ids]),position_ids=pos,use_cache=False,return_dict=True,logits_to_keep=1)
 logits=r.logits[0,-1].float()
 res={'input_ids_sha256':hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),'n':len(ids),'positions':[1,len(ids)],'greedy':int(logits.argmax()),'top10':[(int(i),float(logits[i])) for i in torch.topk(logits,10).indices], 'logits':logits}
 torch.save(res,run/f'oracle-n{n}.pt');print(json.dumps({k:v for k,v in res.items() if k!='logits'}))
