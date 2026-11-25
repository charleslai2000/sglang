#!/usr/bin/env python3
"""Capture PyTorch/CUPTI CUDA activities for one serialized SGLang request window."""
import argparse,json,os,requests,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--output',required=True);p.add_argument('--input-len',type=int,required=True);p.add_argument('--output-len',type=int,required=True);a=p.parse_args()
import torch
from sglang.benchmark.utils import get_tokenizer
RUN=Path(__file__).resolve().parent;ROOT=Path('/tmp/sglang-f1-r16b-clean')
tok=get_tokenizer('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4');url=f'http://127.0.0.1:{a.port}/v1/completions'
ids=tok.encode(' '.join(['The']*a.input_len))[:a.input_len]
req={'model':'falcon-h1-r16c','prompt':ids,'max_tokens':a.output_len,'temperature':0.,'ignore_eos':True,'stream':False,'return_token_ids':True,'return_cached_tokens_details':True,'seed':20261012}
# Profile runs in the client process only as a direct diagnostic first; this is not accepted as a scheduler GPU profile unless CUDA kernels are present and scheduler API correlation is demonstrated.
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True,profile_memory=True) as prof:
 r=requests.post(url,json=req,timeout=300);r.raise_for_status();torch.cuda.synchronize()
prof.export_chrome_trace(a.output)
print('response bytes',len(r.content),'trace',a.output,'events',len(prof.events()))
for e in prof.key_averages():
 if e.device_type.name=='CUDA' or 'cuda' in e.key.lower():print(e.key,e.count,e.self_cuda_time_total,e.cuda_time_total)
