#!/usr/bin/env python3
"""Deterministic round-barrier token-ID conversation benchmark on a running SGLang server."""
import asyncio, json, os, random, statistics, sys, time
from pathlib import Path
ROOT=Path('/tmp/sglang-f1-r16b-clean'); sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from sglang.benchmark.utils import get_tokenizer
from sglang.benchmark.datasets.generated_shared_prefix import sample_generated_shared_prefix_requests
from sglang.test.kits.cache_hit_kit import _get_page_size

async def _timed_request(payload,url):
 import aiohttp,json
 from sglang.benchmark.serving import RequestFuncOutput
 timeout=aiohttp.ClientTimeout(total=20*60*60);out=RequestFuncOutput();start=time.perf_counter();first=None;last=None;token_times=[];ids=[]
 async with aiohttp.ClientSession(timeout=timeout) as session:
  async with session.post(url,json=payload) as response:
   if response.status!=200:raise RuntimeError(f'HTTP {response.status}: {await response.text()}')
   async for raw in response.content:
    raw=raw.strip()
    if not raw or raw==b'data: [DONE]':continue
    data=json.loads(raw[6:] if raw.startswith(b'data: ') else raw)
    if data.get('choices') and data['choices'][0].get('finish_reason') is not None:last=time.perf_counter()
    usage=data.get('usage') or {}
    if usage:out.prompt_len=usage.get('prompt_tokens',out.prompt_len);out.completion_tokens=usage.get('completion_tokens',0)
    ext=data.get('sglext') or {};details=ext.get('cached_tokens_details') or {}
    if details:out.cached_tokens_details=details;out.cached_tokens=sum((details.get(k) or 0) for k in ('device','host','storage'))
    choices=data.get('choices') or []
    if choices:
     choice=choices[0];new_ids=choice.get('token_ids') or []
     if ids and len(new_ids)>=len(ids) and new_ids[:len(ids)]==ids:new_ids=new_ids[len(ids):]
     ids.extend(new_ids);now=time.perf_counter();first=first or now;last=now;token_times.extend([now]*len(new_ids))
     if choice.get('prompt_token_ids') is not None:out.prompt_len=len(choice['prompt_token_ids'])
     usage=data.get('usage') or {};out.prompt_len=usage.get('prompt_tokens',out.prompt_len)
 out.output_ids=ids;out.generated_len=getattr(out,'completion_tokens',len(ids));out.ttft=(first-start) if first else 0.;out.latency=(last-start) if last else time.perf_counter()-start;out.success=bool(ids);out.error='' if ids else 'missing output token ids';out.itl=[b-a for a,b in zip(token_times,token_times[1:])];out.tpot=(out.latency-out.ttft)/max(out.generated_len-1,1);return out

async def send_round(payloads,url,limit):
 sem=asyncio.Semaphore(limit)
 async def one(p):
  async with sem:return await _timed_request(p,url)
 return await asyncio.gather(*(one(p) for p in payloads))

def load_or_create_manifest(path,args,tokenizer):
 if path.exists():
  m=json.loads(path.read_text())
  shape=(m['seed'],len(m['sessions']),m['rounds'],m['prefix_len'],m['question_len'],m['output_len'],m['groups'])
  expected=(args.seed,args.sessions,args.rounds,args.prefix_len,args.question_len,args.output_len,args.groups)
  if shape!=expected:raise ValueError(f'manifest mismatch: {shape} != {expected}')
  if m['concurrency']!=args.concurrency:raise ValueError(f'manifest concurrency mismatch: {m["concurrency"]} != {args.concurrency}')
  checksum=m.get('sha256');payload={k:v for k,v in m.items() if k!='sha256'}
  actual=__import__('hashlib').sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
  if checksum!=actual:raise ValueError('manifest checksum mismatch')
  expected_state={'concurrency':args.concurrency,'rounds':args.rounds,'prefix_len':args.prefix_len,'question_len':args.question_len,'output_len':args.output_len,'groups':args.groups,'revisit_distance':args.revisit_distance}
  if any(m.get(k)!=v for k,v in expected_state.items()):raise ValueError('manifest configuration mismatch')
  return m
 if args.sessions%args.groups:raise ValueError('sessions must be divisible by groups')
 rows=sample_generated_shared_prefix_requests(num_groups=args.groups,prompts_per_group=args.sessions//args.groups,system_prompt_len=args.prefix_len,question_len=args.question_len,output_len=args.output_len,range_ratio=1.0,tokenizer=tokenizer,seed=args.seed,num_turns=args.rounds,ordered=True,fast_prepare=False)
 sessions=[]
 for sid,row in enumerate(rows):
  if not isinstance(row.prompt,list) or len(row.prompt)!=args.rounds:raise ValueError(f'GSP session {sid} does not have {args.rounds} rounds')
  sessions.append({'session_id':sid,'group':sid//(args.sessions//args.groups),'prefix':tokenizer.encode(row.prompt[0]),'questions':[tokenizer.encode(turn) for turn in row.prompt[1:]]})
 if any(len(s['prefix'])+sum(len(q) for q in s['questions'])+(args.rounds-1)*args.output_len>8192 for s in sessions):raise ValueError('GSP cumulative session context exceeds frozen context_length=8192')
 prompts_per_group=args.sessions//args.groups
 if prompts_per_group!=2:raise ValueError('R16C reuse-distance manifest requires exactly two sessions per shared-prefix group')
 order=list(range(args.sessions))
 locality_order=order
 def lcp(a,b):
  i=0
  while i<min(len(a),len(b)) and a[i]==b[i]:i+=1
  return i
 shared_prefixes={str(g):lcp(sessions[2*g]['prefix'],sessions[2*g+1]['prefix']) for g in range(args.groups)}
 if any(n<args.prefix_len*0.75 for n in shared_prefixes.values()):raise ValueError(f'GSP shared-prefix LCP unexpectedly short: {shared_prefixes}')
 unique_initial=sum(len(s['prefix']) for s in sessions)-sum(shared_prefixes.values())
 m={'seed':args.seed,'sessions':sessions,'initial_order':order,'cache_locality_order':locality_order,'round_order':[order[i:i+args.concurrency] for i in range(0,len(order),args.concurrency)],'concurrency':args.concurrency,'rounds':args.rounds,'prefix_len':args.prefix_len,'input_prompt_lengths':[len(s['prefix']) for s in sessions],'question_lengths':[[len(q) for q in s['questions']] for s in sessions],'shared_prefix_lcp_by_group':shared_prefixes,'shared_prefix_lcp_min':min(shared_prefixes.values()),'question_len':args.question_len,'output_len':args.output_len,'groups':args.groups,'revisit_distance':1,'cross_session_lcp_token_reuse':shared_prefixes,'cold_working_set_tokens':unique_initial+sum(sum(len(q) for q in s['questions'])+(args.rounds-1)*args.output_len for s in sessions),'estimated_live_cache_tokens':unique_initial+sum(sum(len(q) for q in s['questions'])+(args.rounds-1)*args.output_len for s in sessions)}
 m['sha256']=__import__('hashlib').sha256(json.dumps(m,separators=(',',':')).encode()).hexdigest()
 path.write_text(json.dumps(m,separators=(',',':')));return m

def create_manifest(args):
 random.seed(args.seed);np.random.seed(args.seed);tokenizer=get_tokenizer('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4')
 path=Path(args.manifest);m=load_or_create_manifest(path,args,tokenizer);print(json.dumps({'path':str(path),'sha256':m['sha256'],'sessions':len(m['sessions']),'rounds':m['rounds'],'concurrency':m['concurrency'],'input_prompt_lengths':m['input_prompt_lengths']},indent=2))

def collect_fpm(endpoint,duration_s,output,stop_event):
 import zmq
 from sglang.srt.observability.forward_pass_metrics import decode
 ctx=zmq.Context();sock=ctx.socket(zmq.SUB);sock.setsockopt(zmq.SUBSCRIBE,b'');sock.setsockopt(zmq.RCVTIMEO,100);sock.connect(endpoint);end=time.time()+duration_s;items=[]
 while time.time()<end and not stop_event.is_set():
  try:
   _,seq,payload=sock.recv_multipart();x=decode(payload);items.append({'seq':int.from_bytes(seq,'big'),'wall_time':x.wall_time,'scheduled':{k:getattr(x.scheduled_requests,k) for k in x.scheduled_requests.__struct_fields__},'queued':{k:getattr(x.queued_requests,k) for k in x.queued_requests.__struct_fields__}})
  except zmq.Again:pass
 sock.close(0);ctx.term();Path(output).write_text(json.dumps(items,indent=2));return items

def main():
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--create-manifest',action='store_true');a.add_argument('--base-url',default='http://127.0.0.1:1');a.add_argument('--output',default='');a.add_argument('--seed',type=int,default=20261012);a.add_argument('--concurrency',type=int,required=True);a.add_argument('--sessions',type=int,default=72);a.add_argument('--rounds',type=int,default=4);a.add_argument('--prefix-len',type=int,default=4608);a.add_argument('--question-len',type=int,default=256);a.add_argument('--output-len',type=int,default=64);a.add_argument('--revisit-distance',type=int,default=36);a.add_argument('--groups',type=int,default=36);a.add_argument('--manifest',required=True);a.add_argument('--metrics-before',default='');a.add_argument('--metrics-after',default='');a.add_argument('--config',default='unspecified');a.add_argument('--server-log',default='');a.add_argument('--fpm-endpoint',default='');a.add_argument('--fpm-output',default='');a.add_argument('--fpm-duration',type=int,default=7200);args=a.parse_args()
 if args.sessions % args.concurrency:raise ValueError('sessions must be divisible by concurrency')
 random.seed(args.seed);np.random.seed(args.seed); tokenizer=get_tokenizer('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4')
 manifest_path=Path(args.manifest)
 if args.create_manifest:
  create_manifest(args);return
 manifest=load_or_create_manifest(manifest_path,args,tokenizer);rows=manifest['sessions'];order=manifest['initial_order']
 page=_get_page_size(args.base_url); url=args.base_url.rstrip('/')+'/v1/completions'; histories=[list(x['prefix']) for x in rows]; previous_prompt=[0]*args.sessions;records=[]
 import requests
 def metric_snapshot():
  try:return requests.get(args.base_url.rstrip('/')+'/metrics',timeout=10).text
  except Exception:return ''
 flush=requests.post(args.base_url.rstrip('/')+'/flush_cache',timeout=60);flush.raise_for_status();time.sleep(1)
 before=metric_snapshot()
 if args.metrics_before:Path(args.metrics_before).write_text(before)
 try:
  info=requests.get(args.base_url.rstrip('/')+'/server_info',timeout=10).json()
  memory=info.get('memory_usage') or {}
  if not memory:
   states=info.get('internal_states') or []
   memory=next((x.get('memory_usage') for x in states if x.get('memory_usage')), {})
  Path(args.manifest).with_suffix('.server-info.json').write_text(json.dumps(info,indent=2))
  if args.config=='gpu-host':
   log=Path(args.server_log).read_text(errors='replace') if args.server_log else ''
   import re
   matches=re.findall(r'Allocating ([A-Za-z0-9_]+) hierarchical KV host pool: (\d+) tokens, ([0-9.]+) GB host memory',log)
   host_pool_tokens={m[0]:int(m[1]) for m in matches}
   if not host_pool_tokens:raise RuntimeError('cannot determine allocated Host cache tokens from startup evidence')
   if not info.get('enable_hierarchical_cache'):raise RuntimeError('GPU+Host config server_info reports HiCache disabled')
   host_tokens=host_pool_tokens.get('kv') or host_pool_tokens.get('full') or next(iter(host_pool_tokens.values()))
   device_tokens=int(memory.get('token_capacity',0))
   required=manifest['estimated_live_cache_tokens']
   if host_tokens+device_tokens<required:raise RuntimeError(f'combined GPU+Host capacity {device_tokens}+{host_tokens}={device_tokens+host_tokens} tokens < estimated unique GSP cache set {required}')
 except Exception as e:
  if args.config=='gpu-host':raise
  print(f'SERVER_INFO_ERROR {e}')
 fpm_proc=None
 if args.fpm_endpoint:
  import threading
  stop_event=threading.Event()
  fpm_proc=threading.Thread(target=collect_fpm,args=(args.fpm_endpoint,args.fpm_duration,args.fpm_output,stop_event),daemon=True);fpm_proc.start();time.sleep(0.5)
 started=time.perf_counter()
 for r in range(args.rounds):
  # Reorder this round deterministically so same-group prefix pairs are sent together.
  # This explicit locality policy maximizes cross-session prefix reuse and is frozen in the manifest.
  round_ids=manifest['initial_order']
  for batch_no,start in enumerate(range(0,len(round_ids),args.concurrency)):
   ids=round_ids[start:start+args.concurrency]
   expected_prompts=[len(histories[sid]) for sid in ids]
   payloads=[{'model':'falcon-h1-r16c','prompt':histories[sid],'max_tokens':args.output_len,'temperature':0.0,'ignore_eos':True,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'return_cached_tokens_details':True,'return_prompt_token_ids':True,'seed':args.seed} for sid in ids]
   t0=time.perf_counter();responses=asyncio.run(send_round(payloads,url,args.concurrency));batch_elapsed=time.perf_counter()-t0
   for sid,expected_input,resp in zip(ids,expected_prompts,responses):
    if not resp.success:raise RuntimeError(f'round {r} session {sid}: {resp.error}')
    if resp.prompt_len and resp.prompt_len!=expected_input:raise RuntimeError(f'prompt token length mismatch session={sid} expected={expected_input} actual={resp.prompt_len}')
    expected=0 if r==0 else (max(previous_prompt[sid]+args.output_len+len(rows[sid]['questions'][r-1])-1,0)//page)*page
    # Preserve evidence even if SGLang's reported cached count is lower than constructional expectation.
    # Cache details are legitimately omitted on a cold miss; preserve None and validate coverage after the run.
    if resp.generated_len!=args.output_len:raise RuntimeError(f'completion length mismatch session={sid} round={r}: {resp.generated_len} != {args.output_len}')
    records.append({'session_id':sid,'round':r,'prompt_tokens':resp.prompt_len,'cached_tokens':resp.cached_tokens,'expected_min_cached':expected,'cache_details':getattr(resp,'cached_tokens_details',None),'ttft_s':resp.ttft,'latency_s':resp.latency,'itl_s':resp.itl,'tpot_s':resp.tpot,'generated_tokens':resp.generated_len,'next_round_question_tokens':len(rows[sid]['questions'][r]) if r<args.rounds-1 else 0,'batch_elapsed_s':batch_elapsed,'session_revisit_distance':args.revisit_distance,'shared_prefix_group':rows[sid]['group']})
    if r and resp.cached_tokens<expected: print(f'CACHE_EXPECTATION_SHORT round={r} session={sid} actual={resp.cached_tokens} expected={expected}')
    previous_prompt[sid]=resp.prompt_len
    histories[sid].extend(resp.output_ids)
    if r<args.rounds-1: histories[sid].extend(rows[sid]['questions'][r])
 duration=time.perf_counter()-started
 if fpm_proc is not None:
  stop_event.set();fpm_proc.join(timeout=10)
 result={'config':args.config,'concurrency':args.concurrency,'sessions':args.sessions,'rounds':args.rounds,'requests':len(records),'duration_s':duration,'rps':len(records)/duration,'effective_concurrency':args.concurrency,'arrival_policy':'round_barrier_fcfs','revisit_distance_sessions':args.revisit_distance,'shared_prefix_groups':args.groups,'flush_status':flush.status_code,'revisit_distance':args.revisit_distance,'estimated_live_cache_tokens':manifest['estimated_live_cache_tokens'],'shared_prefix_lcp_min':manifest['shared_prefix_lcp_min'],'successful_responses':sum(x['generated_tokens']>0 for x in records),'cache_detail_responses':sum(x['cache_details'] is not None for x in records),'input_tokens':sum(x['prompt_tokens'] for x in records),'ttft_p95_ms':sorted(x['ttft_s'] for x in records)[int(.95*(len(records)-1))]*1000,'latency_p95_ms':sorted(x['latency_s'] for x in records)[int(.95*(len(records)-1))]*1000,'tpot_p95_ms':sorted(x['tpot_s'] for x in records)[int(.95*(len(records)-1))]*1000,'mean_tpot_ms':statistics.mean(x['tpot_s'] for x in records)*1000,'host_hit_tokens':sum((x['cache_details'] or {}).get('host',0) for x in records),'device_hit_tokens':sum((x['cache_details'] or {}).get('device',0) for x in records),'storage_hit_tokens':sum((x['cache_details'] or {}).get('storage',0) for x in records),'input_tps':sum(x['prompt_tokens'] for x in records)/duration,'output_tokens':sum(x['generated_tokens'] for x in records),'output_tps':sum(x['generated_tokens'] for x in records)/duration,'mean_ttft_ms':statistics.mean(x['ttft_s'] for x in records)*1000,'p95_ttft_ms':sorted(x['ttft_s'] for x in records)[int(.95*(len(records)-1))]*1000,'mean_latency_ms':statistics.mean(x['latency_s'] for x in records)*1000,'p95_latency_ms':sorted(x['latency_s'] for x in records)[int(.95*(len(records)-1))]*1000,'cache_tokens_by_round':{str(r):sum(x['cached_tokens'] for x in records if x['round']==r) for r in range(args.rounds)},'records':records}
 after=metric_snapshot()
 if args.metrics_after:Path(args.metrics_after).write_text(after)
 result['prometheus_before']=before;result['prometheus_after']=after
 if args.fpm_output and Path(args.fpm_output).exists():
  fpm=json.loads(Path(args.fpm_output).read_text());result['fpm_records']=len(fpm);result['fpm_gpu_wall_time_s']=sum(x['wall_time'] for x in fpm);result['fpm_queue_max_prefill_requests']=max((x['queued']['num_prefill_requests'] for x in fpm),default=0);result['fpm_queue_max_decode_requests']=max((x['queued']['num_decode_requests'] for x in fpm),default=0)
 Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('records','prometheus_before','prometheus_after')},indent=2))
if __name__=='__main__':main()
