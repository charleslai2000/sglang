#!/usr/bin/env python3
"""Invoke existing SGLang serving benchmark with a preconstructed shared-prefix multi-turn DatasetRow set."""
import argparse, asyncio, os, random, sys
from pathlib import Path
import numpy as np
ROOT=Path('/tmp/sglang-f1-r16b-clean'); sys.path.insert(0,str(ROOT/'python'))
from sglang.benchmark import serving as s
from sglang.benchmark.datasets.generated_shared_prefix import sample_generated_shared_prefix_requests
from sglang.benchmark.utils import get_tokenizer
async def main():
 port=int(sys.argv[1]);out=sys.argv[2];random.seed(20261011);np.random.seed(20261011)
 tok=get_tokenizer('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4')
 rows=sample_generated_shared_prefix_requests(num_groups=8,prompts_per_group=8,system_prompt_len=2048,question_len=128,output_len=32,range_ratio=1.0,tokenizer=tok,seed=20261011,num_turns=4,ordered=True,fast_prepare=False)
 for r in rows:
  # serving multi-turn dispatcher expects a prompt whose first element is one conversation turn (messages).
  if not isinstance(r.prompt,list):raise TypeError(f'not multi-turn: {type(r.prompt)}')
  r.prompt=[[{'role':'user','content':turn}] for turn in r.prompt]
  r.output_len=32
 args=argparse.Namespace(backend='sglang-oai-chat',model='falcon-h1-r16b',tokenizer='/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4',served_model_name='falcon-h1-r16b',dataset_name='generated-shared-prefix',dataset_path='',seed=20261011,port=port,host='127.0.0.1',base_url=None,request_rate=float('inf'),max_concurrency=4,disable_tqdm=True,disable_stream=False,return_logprob=False,top_logprobs_num=0,token_ids_logprob=None,logprob_start_len=-1,return_routed_experts=False,cache_report=True,temperature=0.0,top_p=1.0,extra_request_body={},profile=False,pd_separated=False,flush_cache=False,flush_cache_timeout=60.,warmup_requests=1,use_trace_timestamps=False,mooncake_slowdown_factor=1.,mooncake_num_rounds=1,profile_prefill_url=None,profile_decode_url=None,plot_throughput=False,output_details=True,output_file=out,sharegpt_output_len=None,random_input_len=0,random_output_len=32,random_range_ratio=0.,tag='gsp-four-round',lora_name=None,lora_request_distribution='uniform',lora_zipf_alpha=1.5,print_requests=False,ready_check_timeout_sec=0,disable_ignore_eos=True,tokenize_prompt=False,cache_report=True)
 s.set_global_args(args)
 result=await s.benchmark(backend=args.backend,api_url=f'http://127.0.0.1:{port}/v1/chat/completions',base_url=f'http://127.0.0.1:{port}',model_id=args.served_model_name,tokenizer=tok,input_requests=rows,request_rate=float('inf'),max_concurrency=4,disable_tqdm=True,lora_names=None,lora_request_distribution=None,lora_zipf_alpha=None,extra_request_body={},profile=False,pd_separated=False,warmup_requests=1)
 print('GSP_MULTI_TURN_RESULT',result.get('completed'),result.get('output_throughput'))
if __name__=='__main__':asyncio.run(main())
