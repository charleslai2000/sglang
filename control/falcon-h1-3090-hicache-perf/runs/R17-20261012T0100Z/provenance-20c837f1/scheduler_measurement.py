#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Reuse SGLang ForwardPassMetrics + NVML sampling for clean c8/c16 scheduler timing."""
import argparse,asyncio,fcntl,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
import aiohttp,requests,zmq,msgspec
ROOT=Path('/tmp/sglang-r17');sys.path[:0]=['/tmp/f1-r3-kernel-overlay',str(ROOT/'python'),str(ROOT/'python/sglang/kernels/aot/python')]
from sglang.srt.observability.forward_pass_metrics import ForwardPassMetrics
R=ROOT/'control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z';PY='/home/ubuntu/venvs/sglang-3090/bin/python';BASE='http://127.0.0.1:30160';LOCK='/tmp/f1-r16b-gpu-exclusive.lock'
p=argparse.ArgumentParser();p.add_argument('--concurrency',type=int,choices=[8,16],required=True);p.add_argument('--trial',type=int,required=True);p.add_argument('--mode',choices=['gpu-only','host'],required=True);p.add_argument('--requests',type=int,default=40);a=p.parse_args()
D=R/f'scheduler-{a.mode}-c{a.concurrency}-t{a.trial}';D.mkdir(parents=True,exist_ok=True)
if any(D.iterdir()):raise RuntimeError(f'run output directory is not empty: {D}')
if subprocess.run(['git','-C',str(ROOT),'diff','--quiet','HEAD','--',str(R.relative_to(ROOT))],check=False).returncode not in (0,1):raise RuntimeError('unable to verify frozen R17 worktree');
if subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()!='20c837f1a3daaec47508feaecf5514dd586c636c':raise RuntimeError('R17 frozen HEAD changed')
rows=json.loads((R/'workload.json').read_text())['workload'][:a.requests];manifest=hashlib.sha256(json.dumps([x['prompt_token_ids'] for x in rows],separators=(',',':')).encode()).hexdigest();tag=f'r17-{a.mode}-c{a.concurrency}-t{a.trial}';endpoint=f'ipc:///tmp/sglang-r17-{tag}.sock.0';sockpath=endpoint.removeprefix('ipc://')
ctx=zmq.Context();sub=ctx.socket(zmq.SUB);sub.setsockopt(zmq.SUBSCRIBE,b'');sub.setsockopt(zmq.RCVHWM,100000);sub.connect(endpoint);dec=msgspec.msgpack.Decoder(ForwardPassMetrics);poll=zmq.Poller();poll.register(sub,zmq.POLLIN);events=[];collector_error=[];srv=None;sampler=None
async def request_batch():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800),connector=aiohttp.TCPConnector(limit=a.concurrency)) as s:
  sem=asyncio.Semaphore(a.concurrency)
  async def one(row):
   async with sem:
    start=time.perf_counter()
    async with s.post(BASE+'/generate',json={'input_ids':row['prompt_token_ids'],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':128,'ignore_eos':True},'stream':False,'return_cached_tokens_details':True}) as resp:
     payload=await resp.json();status=resp.status
    m=payload.get('meta_info',{})
    return {'request_id':row['request_id'],'status':status,'prompt_tokens':row['input_tokens'],'completion_tokens':m.get('completion_tokens'),'e2e_latency_s':m.get('e2e_latency'),'ttft_s':m.get('ttft'),'queue_time_s':m.get('queue_time'),'forward_entry_time':m.get('forward_entry_time'),'prefill_finished_time':m.get('prefill_finished_time'),'request_received_ts':m.get('request_received_ts'),'request_finished_ts':m.get('request_finished_ts'),'cached_tokens':m.get('cached_tokens'),'cached_tokens_details':m.get('cached_tokens_details'),'client_latency_s':time.perf_counter()-start,'error':payload.get('error')}
  return await asyncio.gather(*(one(x) for x in rows))
def collect_available():
 while True:
  ev=dict(poll.poll(0))
  if sub not in ev:break
  parts=sub.recv_multipart()
  if len(parts)!=3:continue
  try:
   q=dec.decode(parts[2]);events.append({'recv_monotonic_ns':time.monotonic_ns(),'seq':int.from_bytes(parts[1],'big'),'counter_id':q.counter_id,'worker_id':q.worker_id,'dp_rank':q.dp_rank,'gpu_forward_s':q.wall_time,'prefill':{'requests':q.scheduled_requests.num_prefill_requests,'compute_tokens':q.scheduled_requests.sum_prefill_tokens,'prefix_kv_tokens':q.scheduled_requests.sum_prefill_kv_tokens},'decode':{'requests':q.scheduled_requests.num_decode_requests,'kv_tokens':q.scheduled_requests.sum_decode_kv_tokens},'queued':{'prefill_requests':q.queued_requests.num_prefill_requests,'prefill_tokens':q.queued_requests.sum_prefill_tokens,'decode_requests':q.queued_requests.num_decode_requests,'decode_kv_tokens':q.queued_requests.sum_decode_kv_tokens}})
  except Exception as ex:collector_error.append(str(ex))
def main():
 global srv,sampler
 with open(LOCK,'w') as lf:
  fcntl.flock(lf,fcntl.LOCK_EX)
  try:
   if requests.get(BASE+'/health',timeout=2).ok:raise RuntimeError('port 30160 unexpectedly active')
  except requests.RequestException:pass
  if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise RuntimeError('GPU compute process already active')
  if Path(sockpath).exists():raise RuntimeError('FPM socket collision')
  env=os.environ.copy();env['SGLANG_R17_PROFILE_TAG']=tag;env['SGLANG_ENABLE_METRICS_DEVICE_TIMER']='1';env['SGLANG_HICACHE_METRICS_ENABLED']='1'
  launcher=R/'launch_server.sh'
  if a.mode=='gpu-only':
   sh=launcher.read_text().replace('--enable-hierarchical-cache --hicache-ratio 2.0','');custom=D/'launch_gpu_only.sh';custom.write_text(sh);custom.chmod(0o755);launcher=custom
  else:
   sh=launcher.read_text();custom=D/'launch_host_cache.sh';custom.write_text(sh);custom.chmod(0o755);launcher=custom
  srv=subprocess.Popen(['bash',str(launcher)],cwd=ROOT,env=env,stdout=open(D/'server.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
  sampler=subprocess.Popen([PY,str(R/'gpu_window_sample.py'),'--out',str(D/'gpu-nvml.csv'),'--tag',tag],stdout=open(D/'nvml.stdout','w'),stderr=open(D/'nvml.stderr','w'),start_new_session=True)
  try:
   (D/'manifest.json').write_text(json.dumps({'tag':tag,'mode':a.mode,'concurrency':a.concurrency,'trial':a.trial,'requests':len(rows),'output_tokens_per_request':128,'manifest_sha256':manifest,'source_manifest_sha256':json.loads((R/'workload.json').read_text())['sha256'],'base_commit':'20c837f1a3daaec47508feaecf5514dd586c636c','model_revision':'52036ae497a2c0c253e17f98cc8652f2f7082ae3','device_timer_env':'1','fpm_endpoint':endpoint},indent=2))
   ready=False
   for _ in range(600):
    if srv.poll() is not None:raise RuntimeError(f'server exited rc={srv.returncode}')
    try:
     if requests.get(BASE+'/health',timeout=2).ok:ready=True;break
    except requests.RequestException:pass
    time.sleep(2)
   if not ready:raise TimeoutError('service health timed out after 1200 s')
   requests.post(BASE+'/flush_cache',timeout=60).raise_for_status();(D/'processes.txt').write_text(subprocess.check_output(['ps','-eo','pid,ppid,stat,args'],text=True))
   ready_gpu=[]
   for _ in range(120):
    try:
     x=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],text=True);ready_gpu.append((time.monotonic(),int(x.strip())))
    except Exception:pass
    time.sleep(1)
   baseline={'gpu_util_pct_min':min(x[1] for x in ready_gpu),'gpu_util_pct_max':max(x[1] for x in ready_gpu),'samples':len(ready_gpu)};(D/'preload-baseline.json').write_text(json.dumps(baseline,indent=2))
   wall0=time.time_ns();mono0=time.monotonic_ns();t0=time.perf_counter();loop=asyncio.new_event_loop();asyncio.set_event_loop(loop);task=loop.create_task(request_batch())
   while not task.done():
    loop.run_until_complete(asyncio.sleep(0))
    ev=dict(poll.poll(50))
    if sub in ev:collect_available()
   results=task.result();loop.close();elapsed=time.perf_counter()-t0;wall1=time.time_ns();mono1=time.monotonic_ns()
   deadline=time.monotonic()+2
   while time.monotonic()<deadline:
    ev=dict(poll.poll(50))
    if sub in ev:collect_available()
   metrics=requests.get(BASE+'/metrics',timeout=30).text;(D/'metrics-final.prom').write_text(metrics)
   import re
   hitnames=['effective_prefill_tokens','hicache','load_back_bytes_total','load_back_tokens_total','backup_bytes_total']
   (D/'metrics-cache-window.prom').write_text('\n'.join(line for line in metrics.splitlines() if any(n in line.lower() for n in hitnames) and not line.startswith('#'))+'\n')
   meta={'tag':tag,'mode':a.mode,'concurrency':a.concurrency,'trial':a.trial,'requests':len(results),'successful':sum(r['completion_tokens']==128 and r['error'] is None for r in results),'manifest_sha256':manifest,'wall_s':elapsed,'wall_start_epoch_ns':wall0,'wall_end_epoch_ns':wall1,'monotonic_start_ns':mono0,'monotonic_end_ns':mono1,'actual_scheduler_forward_pass_messages':len(events),'sum_forward_pass_gpu_s':sum(x['gpu_forward_s'] for x in events),'prefill_compute_tokens_reported':sum(x['prefill']['compute_tokens'] for x in events),'decode_active_forwards':sum(x['decode']['requests']>0 for x in events),'decode_kv_context_tokens_sum':sum(x['decode']['kv_tokens'] for x in events),'gpu_idle_gap_est_s':max(0,elapsed-sum(x['gpu_forward_s'] for x in events)),'collector_errors':collector_error,'gpu_window_csv':str(D/'gpu-nvml.csv'),'gpu_event_semantics':'CUDA event intervals bracket model_runner.forward/cuda_graph.replay; their sum can exceed union wall time if async streams overlap'}
   (D/'summary.json').write_text(json.dumps(meta,indent=2));(D/'scheduler-forward-pass.json').write_text(json.dumps({'endpoint':endpoint,'messages':len(events),'records':events},indent=2));(D/'request-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(meta),flush=True)
  finally:
   try:requests.post(BASE+'/shutdown',timeout=5)
   except Exception:pass
   if srv is not None:
    try:os.killpg(srv.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:srv.wait(timeout=120)
    except subprocess.TimeoutExpired:os.killpg(srv.pid,signal.SIGKILL);srv.wait()
   if sampler is not None:
    try:os.killpg(sampler.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:sampler.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(sampler.pid,signal.SIGKILL);sampler.wait()
   sub.close(0);ctx.term()
   try:Path(sockpath).unlink()
   except FileNotFoundError:pass
if __name__=='__main__':main()
