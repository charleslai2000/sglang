#!/home/ubuntu/venvs/sglang-3090/bin/python
import argparse,asyncio,json,os,signal,subprocess,time
from pathlib import Path
import aiohttp,requests
R=Path('/tmp/sglang-r17/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z');P='/home/ubuntu/venvs/sglang-3090/bin/python';URL='http://127.0.0.1:30160'
p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prefill','decode'],required=True);p.add_argument('--concurrency',type=int,choices=[8,16],required=True);p.add_argument('--trial',type=int,default=1);p.add_argument('--outdir',required=True);a=p.parse_args();tag=a.outdir;D=R/tag
D.mkdir(parents=True,exist_ok=True)
if (D/'.run-started').exists():raise RuntimeError(f'run output directory was already used: {D}')
(D/'.run-started').write_text(str(time.time_ns()))
rows=json.loads((R/'workload.json').read_text())['workload'][:max(40,a.concurrency*5)]
env=os.environ.copy();env['SGLANG_R17_PROFILE_TAG']=tag;env['SGLANG_ENABLE_METRICS_DEVICE_TIMER']='1';env['SGLANG_PROFILE_V2']='1';env['SGLANG_ENABLE_NVTX_SCHEDULER']='1';srv=subprocess.Popen(['bash',str(R/'launch_server.sh')],cwd='/tmp/sglang-r17',env=env,stdout=open(D/'server.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
async def go(n):
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2400),connector=aiohttp.TCPConnector(limit=a.concurrency)) as s:
  sem=asyncio.Semaphore(a.concurrency)
  async def one(x):
   async with sem:
    async with s.post(URL+'/generate',json={'input_ids':x['prompt_token_ids'],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':128,'ignore_eos':True},'stream':False,'return_cached_tokens_details':True}) as r:
     d=await r.json();return {'status':r.status,'output':d.get('meta_info',{}).get('completion_tokens'),'e2e_s':d.get('meta_info',{}).get('e2e_latency')}
  return await asyncio.gather(*(one(x) for x in rows[:n]))
try:
 for _ in range(540):
  if srv.poll() is not None:raise RuntimeError(f'server exited {srv.returncode}')
  try:
   if requests.get(URL+'/health',timeout=2).ok:break
  except requests.RequestException:pass
  time.sleep(2)
 else:raise TimeoutError('health timeout')
 time.sleep(5);requests.post(URL+'/flush_cache',timeout=60).raise_for_status()
 if a.stage=='prefill':
  # Short output makes the launch window dominated by the prompt extend stage.
  rows2=rows
  async def pf():
   async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1200),connector=aiohttp.TCPConnector(limit=a.concurrency)) as s:
    async def one(x):
     async with s.post(URL+'/generate',json={'input_ids':x['prompt_token_ids'],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':1,'ignore_eos':True},'stream':False}) as r:return {'status':r.status,'body':await r.json()}
    return await asyncio.gather(*(one(x) for x in rows2[:max(40,a.concurrency*5)]))
  result=asyncio.run(pf())
 else:result=asyncio.run(go(max(40,a.concurrency*5)))
 (D/'requests.json').write_text(json.dumps({'stage':a.stage,'concurrency':a.concurrency,'requests':len(result),'results':result},indent=2));print(json.dumps({'dir':str(D),'requests':len(result)}),flush=True)
finally:
 try:requests.post(URL+'/shutdown',timeout=5)
 except Exception:pass
 try:os.killpg(srv.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 try:srv.wait(timeout=90)
 except subprocess.TimeoutExpired:os.killpg(srv.pid,signal.SIGKILL);srv.wait()
