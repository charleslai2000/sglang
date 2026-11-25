#!/usr/bin/env python3
"""Serial GPU cache baseline; owns server/client process groups and validates every result."""
import json, os, signal, subprocess, sys, time, urllib.request, uuid
from pathlib import Path
ROOT=Path('/home/ubuntu/workspaces/3rdparty/sglang-hicache'); RUN=ROOT/'control/falcon-h1-3090-hicache-perf/runs/R16-20261011T0800Z'
MODEL='/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4'; PY='/home/ubuntu/venvs/sglang-3090/bin/python'
env=os.environ.copy(); env['PYTHONPATH']=f"/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python"; env['SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION']='false'
def terminate(p):
 if p is None or p.poll() is not None:return
 os.killpg(p.pid,signal.SIGTERM)
 try:p.wait(timeout=30)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def check_idle():
 s=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader'],text=True).strip()
 if s!='1 MiB':raise RuntimeError(f'GPU not idle after cleanup: {s}')
def main():
 cfg=sys.argv[1]; trials=int(os.getenv('TRIALS','3')); concs=[int(x) for x in os.getenv('CONCURRENCIES','1 4 8 16 32 64').split()]
 if cfg=='gpu-only': port=30128; launch=RUN/'launch_gpu_only.sh'
 elif cfg=='gpu-host':port=30129;launch=RUN/'launch_gpu_host.sh'
 else:raise SystemExit('gpu-only|gpu-host')
 for trial in range(1,trials+1):
  server=None
  try:
   server=subprocess.Popen([str(launch)],cwd=ROOT,env=env,stdout=open(RUN/f'{cfg}-server-trial{trial}.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
   ready=RUN/f'{cfg}-server-ready.json'
   ready.unlink(missing_ok=True)
   for _ in range(180):
    if server.poll() is not None:raise RuntimeError(f'server exited {server.returncode}')
    with open(RUN/f'{cfg}-server-trial{trial}.log') as sf:
     if 'The server is fired up and ready to roll!' in sf.read():break
    time.sleep(2)
   else:raise TimeoutError('server readiness timeout')
   for workload,ilen,olen,nreq in [('p-heavy',1024,16,32),('d-heavy',128,64,32),('long-context',4096,8,16)]:
    for conc in concs:
     runid=os.getenv('RUN_ID',uuid.uuid4().hex[:8])
     out=RUN/f'{runid}-{cfg}-{workload}-c{conc}-trial{trial}.jsonl'; log=RUN/f'{runid}-{cfg}-{workload}-c{conc}-trial{trial}.log'
     cmd=[PY,'-m','sglang.benchmark.serving','--backend','sglang','--model',MODEL,'--dataset-name','random-ids','--tokenizer',MODEL,'--host','127.0.0.1','--port',str(port),'--num-prompts',str(nreq),'--random-input-len',str(ilen),'--random-output-len',str(olen),'--request-rate','inf','--max-concurrency',str(min(conc,9)),'--seed','20261011','--temperature','0','--tokenize-prompt','--output-details','--cache-report','--output-file',str(out)]
     with open(log,'w') as f:p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
     try:rc=p.wait(timeout=480)
     except subprocess.TimeoutExpired:terminate(p);raise TimeoutError(f'{cfg}/{workload}/c{conc} timeout')
     if rc:raise RuntimeError(f'{cfg}/{workload}/c{conc} client rc={rc}; see {log}')
     rows=out.read_text().splitlines();
     if len(rows)!=1:raise RuntimeError(f'{out} expected exactly one summary row, got {len(rows)}')
     data=json.loads(rows[0]);errors=sum(bool(x) for x in data.get('errors',[]))
     if data.get('completed')!=nreq or errors:raise RuntimeError(f'incomplete/errors: completed={data.get("completed")} errors={errors}')
     if server.poll() is not None:raise RuntimeError(f'server exited during benchmark: {server.returncode}')
  finally:
   terminate(server)
   check_idle()
if __name__=='__main__':main()
