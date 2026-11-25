#!/usr/bin/env python3
"""Run the SGLang scheduler process itself under Nsight Systems; benchmark it separately."""
import fcntl,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path('/tmp/sglang-f1-r16b-clean'); RUN=Path(__file__).resolve().parent; LOCK='/tmp/f1-r16b-gpu-exclusive.lock'; port=30148
launch=RUN/'launch_profile_gpu_only.sh'
with open(LOCK,'w') as lf:
 fcntl.flock(lf,fcntl.LOCK_EX)
 used=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())
 if used>32:raise SystemExit(f'GPU not idle: {used} MiB')
 env=os.environ.copy();env['PYTHONPATH']=f'/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python';env['SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION']='false';env['PROMETHEUS_MULTIPROC_DIR']=str(RUN/'prometheus-profile');Path(env['PROMETHEUS_MULTIPROC_DIR']).mkdir(exist_ok=True)
 cmd=['nsys','profile','--trace=cuda,nvtx,osrt','--sample=none','--cuda-graph-trace=graph','--force-overwrite=true','--output',str(RUN/'nsys-server-process'),'/bin/bash',str(launch)]
 p=subprocess.Popen(cmd,cwd=ROOT,env=env,start_new_session=True,stdout=open(RUN/'nsys-server-driver.log','w'),stderr=subprocess.STDOUT)
 try:
  ready=False
  for _ in range(240):
   log=RUN/'nsys-server-driver.log'
   if log.exists() and ('The server is fired up and ready to roll!' in log.read_text(errors='replace') or 'Uvicorn running on http://127.0.0.1:30148' in log.read_text(errors='replace')):ready=True;break
   if p.poll() is not None:raise RuntimeError('Nsight-launched server exited before ready')
   time.sleep(2)
  if not ready:raise TimeoutError('server startup timeout')
  Path(RUN/'nsys-server.pid').write_text(str(p.pid))
  server_pid=None
  for _ in range(20):
   rows=[line.split(None,2) for line in subprocess.check_output(['ps','-eo','pid,ppid,args'],text=True).splitlines()[1:]]
   proc={int(pid):(int(ppid),args) for pid,ppid,args in rows}
   # nsys may insert helper processes whose parent is not the CLI PID, and
   # launch_server may be shown as ``-m sglang.launch_server`` rather than a
   # script path. Identify the actual serving process by argv and membership
   # anywhere below the nsys process, not by an assumed nsys-launcher parent.
   descendants={p.pid}
   changed=True
   while changed:
    changed=False
    for pid,(ppid,args) in proc.items():
     if ppid in descendants and pid not in descendants:
      descendants.add(pid);changed=True
   candidates=[]
   for pid in descendants:
    if pid not in proc:continue
    ppid,args=proc[pid]
    if 'sglang.launch_server' in args and f'--port {port}' in args:
     candidates.append(pid)
   if candidates:server_pid=max(candidates);break
   time.sleep(1)
  if server_pid is None:raise RuntimeError('cannot identify SGLang launcher PID inside profiled tree')
  Path(RUN/'nsys-server.pid').write_text(f'nsys_root={p.pid}\\nserver_launcher={server_pid}\\n')
  print(f'profiled process tree root={p.pid}, server launcher={server_pid} port={port}; waiting for explicit stop',flush=True)
  # Keep collection alive until an explicit stop request after the separate client finishes.
  stopfile=RUN/'stop-nsys-server'
  stopfile.unlink(missing_ok=True)
  while not stopfile.exists():
   if p.poll() is not None:raise RuntimeError(f'Nsight/server exited unexpectedly: {p.returncode}')
   time.sleep(1)
  stopfile.unlink()
  try:os.killpg(p.pid,signal.SIGINT)
  except ProcessLookupError:pass
  try:rc=p.wait(timeout=90)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
  print('nsys server rc',rc)
 finally:
  if p.poll() is None:
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:p.wait(timeout=40)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
PY