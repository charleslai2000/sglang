#!/usr/bin/env python3
"""Capture short in-scheduler CUDA profiles at c8 for prefill and decode."""
import argparse,asyncio,json,os,signal,subprocess,time,fcntl
from pathlib import Path
import aiohttp,requests
R=Path(__file__).resolve().parent
P='/home/ubuntu/venvs/sglang-3090/bin/python';URL='http://127.0.0.1:30160';LOCK='/tmp/f1-r16b-gpu-exclusive.lock';m=json.loads((R/'workload.json').read_text());rows=m['workload'][:8];z=argparse.ArgumentParser();z.add_argument('--stage',choices=['prefill','decode'],required=True);a=z.parse_args()
async def reqs():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
  async def one(row):
   async with s.post(URL+'/generate',json={'input_ids':row['prompt_token_ids'],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':128,'ignore_eos':True},'stream':False}) as r:
    x=await r.json();return int(x.get('meta_info',{}).get('completion_tokens',0))
  return await asyncio.gather(*(one(x) for x in rows))
with open(LOCK,'w') as f:
 fcntl.flock(f,fcntl.LOCK_EX)
 p=R/f'profile-{a.stage}';p.mkdir(exist_ok=True)
 # Start isolated service with the stage-filtered profiler implementation.
 env=os.environ.copy();env['SGLANG_PROFILE_V2']='1'
 srv=subprocess.Popen([str(R/'launch_server.sh')],cwd='/tmp/sglang-r17',env=env,stdout=open(p/'server.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
 try:
  for _ in range(180):
   if srv.poll() is not None:
    (p/'server.stdout.txt').write_text((p/'server.log').read_text(errors='replace'))
    raise RuntimeError(f'server exited rc={srv.returncode}; '+(p/'server.log').read_text(errors='replace')[-4000:])
   try:
    if requests.get(URL+'/health',timeout=2).ok:break
   except requests.RequestException:pass
   time.sleep(2)
  else:raise TimeoutError('service not ready')
  requests.post(URL+'/flush_cache',timeout=60).raise_for_status();asyncio.run(reqs());requests.post(URL+'/flush_cache',timeout=60).raise_for_status()
  prof={'output_dir':str(p),'profile_id':f'r17-{a.stage}','activities':['CPU','GPU'],'with_stack':False,'record_shapes':False,'num_steps':6,'profile_by_stage':True,'profile_stages':['prefill' if a.stage=='prefill' else 'decode']}
  requests.post(URL+'/start_profile',json=prof,timeout=30).raise_for_status();t=time.perf_counter();lens=asyncio.run(reqs());elapsed=time.perf_counter()-t
  time.sleep(2);traces=list(p.glob('*.trace.json.gz'))+list(p.glob('*.json'));(p/'profile_info.json').write_text(json.dumps({'stage':a.stage,'concurrency':8,'requests':8,'output_lengths':lens,'wall_seconds':elapsed,'trace_files':[str(x) for x in traces]},indent=2));print('profile',a.stage,'outputs',lens,'traces',traces)
 finally:
  try:os.killpg(srv.pid,signal.SIGTERM);srv.wait(timeout=30)
  except:os.killpg(srv.pid,signal.SIGKILL)
