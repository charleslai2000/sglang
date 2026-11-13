#!/usr/bin/env python3
"""Capture all HF Gemma4 hidden states for exact 510–514 prompts at positions 1..N."""
import json,sys
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM
root=Path(sys.argv[1]);torch.set_num_threads(8)
m=AutoModelForCausalLM.from_pretrained('/data/sglang-hicache/gemma4/model',torch_dtype=torch.bfloat16,device_map='cpu',trust_remote_code=True,low_cpu_mem_usage=True).eval()
for n in (510,511,512,513,514):
 ids=json.loads((root/f'n{n}/bf16-request.json').read_text())['prompt']; pos=torch.arange(1,len(ids)+1).unsqueeze(0)
 with torch.inference_mode(): out=m(input_ids=torch.tensor([ids]),position_ids=pos,use_cache=False,return_dict=True,output_hidden_states=True,logits_to_keep=1)
 torch.save({'input_ids':ids,'positions':pos[0],'hidden_states':[x.cpu() for x in out.hidden_states],'logits':out.logits[0,-1].float()},root/f'oracle-layers-n{n}.pt')
 print(f'captured n={n} hidden_states={len(out.hidden_states)}')
