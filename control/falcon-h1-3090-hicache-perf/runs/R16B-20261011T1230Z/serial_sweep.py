#!/usr/bin/env python3
"""Locked serial GPU baseline using SGLang's existing serving benchmark."""
import fcntl, glob, json, os, signal, subprocess, sys, time, uuid
from pathlib import Path
ROOT=Path('/tmp/sglang-f1-r16b-clean')
RUN=Path('/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16B-20261011T1230Z')
MODEL='/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4'; REV='52036ae497a2c0c253e17f98cc8652f2f7082ae3'; PY='/home/ubuntu/venvs/sglang-3090/bin/python'
LOCK='/tmp/f1-r16b-gpu-exclusive.lock'; env=os.environ.copy(); env['PYTHONPATH']=f'/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python'; env['SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION']='false'
def stop_group(p):
 if p is None:return
 try:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:return
 try:p.wait(timeout=35)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL);p.wait()
def gpu_idle():
 out=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',')
 mem,util=map(int,out)
 if mem>32 or util>2:raise RuntimeError(f'GPU interference before run or after cleanup: {mem} MiB {util}%')
def port_free(port):
 x=subprocess.run(['bash','-lc',f"! ss -ltn | grep -q ':{port} '"])
 if x.returncode:raise RuntimeError(f'port {port} occupied')
def main():
 cfg=sys.argv[1]; trials=int(os.getenv('TRIALS','3')); concs=[int(x) for x in os.getenv('CONCURRENCIES','1 4 8 9').split()]
 if cfg=='gpu-only':port=30138;launch=RUN/'launch_gpu_only.sh'
 elif cfg=='gpu-host':port=30139;launch=RUN/'launch_gpu_host.sh'
 else:raise SystemExit('gpu-only|gpu-host')
 RUN.mkdir(parents=True,exist_ok=True)
 with open(LOCK,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  gpu_idle()
  for trial in range(1,trials+1):
   runid=f'{uuid.uuid4().hex[:8]}-{cfg}-t{trial}'; server=client=None
   logp=RUN/f'{runid}-server.log'; sf=open(logp,'w')
   try:
    port_free(port)
    server=subprocess.Popen([str(launch)],cwd=ROOT,env=env,stdout=sf,stderr=subprocess.STDOUT,start_new_session=True)
    for _ in range(180):
     if server.poll() is not None:raise RuntimeError(f'server exited {server.returncode}; {logp}')
     sf.flush()
     if 'The server is fired up and ready to roll!' in logp.read_text(errors='replace'):break
     time.sleep(2)
    else:raise TimeoutError(f'server startup timeout; {logp}')
    # Record actual configured runtime cap from the startup log; Falcon Mamba may cap below CLI request.
    text=logp.read_text(errors='replace');
    caps=[int(s.split('max_running_requests=')[1].split()[0]) for s in text.splitlines() if 'max_running_requests is capped to' in s and 'max_running_requests=' in s]
    effective=min(caps) if caps else 9
    workloads=[('p-heavy',1024,16,64),('d-heavy',128,64,64),('long-context',4096,8,32)]
    if os.getenv('INCLUDE_GSP') == '1':workloads.append(('gsp-multiturn',0,0,0))
    for workload,ilen,olen,nreq in workloads:
     for conc in concs:
      actual=min(conc,effective); out=RUN/runid/workload/f'c{conc}'/'result.jsonl'; out.parent.mkdir(parents=True,exist_ok=False); cl=out.parent/'client.log'
      if workload=='gsp-multiturn':
       out=out.with_name('gsp-result.jsonl')
       cmd=[PY,str(RUN/'gsp_rounds.py'),str(port),str(out)]
      else:
       cmd=[PY,'-m','sglang.benchmark.serving','--backend','sglang','--model',MODEL,'--dataset-name','random-ids','--tokenizer',MODEL,'--host','127.0.0.1','--port',str(port),'--num-prompts',str(nreq),'--random-input-len',str(ilen),'--random-output-len',str(olen),'--request-rate','inf','--max-concurrency',str(actual),'--seed','20261011','--temperature','0','--tokenize-prompt','--output-details','--cache-report','--output-file',str(out)]
      with open(cl,'w') as f:client=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
      try:rc=client.wait(timeout=480)
      except subprocess.TimeoutExpired:stop_group(client);raise TimeoutError(f'{runid}/{workload}/c{conc} timeout')
      client=None
      if rc:raise RuntimeError(f'client rc={rc}; {cl}')
      lines=out.read_text().splitlines()
      if len(lines)!=1:raise RuntimeError(f'invalid result rows {len(lines)}: {out}')
      d=json.loads(lines[0]); errors=sum(bool(x) for x in d.get('errors',[]))
      if d.get('completed')!=nreq or errors:raise RuntimeError(f'incomplete/errors {d.get("completed")}/{nreq}, {errors}: {out}')
      if d.get('max_concurrency')!=actual:raise RuntimeError(f'effective concurrency request mismatch: {out}')
      if server.poll() is not None:raise RuntimeError(f'server exited during case: {logp}')
   finally:
    stop_group(client);stop_group(server);sf.close()
    for _ in range(20):
     if subprocess.run(['bash','-lc',f"! ss -ltn | grep -q ':{port} '"]).returncode==0:break
     time.sleep(1)
    port_free(port);gpu_idle()
if __name__=='__main__':main()
