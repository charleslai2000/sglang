#!/usr/bin/env python3
"""Hold the project GPU flock and profile a T004 direct-I/O high-pressure run."""
from __future__ import annotations
import fcntl, hashlib, json, os, signal, shutil, subprocess, sys, time
import zmq
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
RUN=Path(__file__).resolve().parent
PY='/home/ubuntu/venvs/sglang-3090/bin/python'
NSYS=os.environ.get('T004_NSYS','/usr/local/bin/nsys')
if not Path(NSYS).is_file() or not os.access(NSYS,os.X_OK):
  raise RuntimeError(f'Nsight Systems CLI is unavailable: {NSYS}')
LOCK='/tmp/f1-r16b-gpu-exclusive.lock'

def main():
    run_id=os.environ.get('T38C_RUN_ID') or f"falcon-t004-nsys-{time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())}"
    cupti_probe=RUN/f'{run_id}-cupti.json'
    if cupti_probe.exists(): raise RuntimeError(f'refusing to overwrite CUPTI calibration output {cupti_probe}')
    out=RUN/f'{run_id}-nsys'
    out.mkdir(parents=True,exist_ok=False)
    lock_inherited=os.environ.get('SGLANG_R17_GPU_LOCK_HELD')=='1'
    lf=None
    if not lock_inherited:
      lf=open(LOCK,'a'); fcntl.flock(lf,fcntl.LOCK_EX)
    nsys=None
    collector=None
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    pysha=hashlib.sha256(Path(PY).read_bytes()).hexdigest()
    # Scheduler appends `.<dp_rank>` to this base name. Connect the collector
    # and readiness PUB to the actual DP0 endpoint, not the base path.
    endpoint_base=f'ipc:///tmp/t004-fpm-{run_id}.sock'
    endpoint=endpoint_base+'.0'
    kernel_overlay=os.environ.get('SGLANG_R17_AOT_OVERLAY','/home/ubuntu/workspaces/3rdparty/sglang/python/sglang/kernels/aot/python')
    if not Path(kernel_overlay).is_dir():
      raise RuntimeError(f'required registered kernel source missing: {kernel_overlay!r}')
    cache_home=Path(os.environ.get('T004_CACHE_HOME',f'/data/sglang-hicache/nsys-2026.5.1/cache/{run_id}'))
    cache_home.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy(); env.update({
      # NVTX availability is captured when nvtx_utils is first imported, so
      # enabling it only in the Nsight child is too late for the runner's
      # parent-side readiness and collector setup imports.
      'SGLANG_T002_NVTX_STEP':'1','SGLANG_ENABLE_NVTX_SCHEDULER':'1',
      'PYTHONPATH':f"{os.environ.get('T004_BOOTSTRAP','/data/sglang-hicache/nsys-2026.5.1/bootstrap')}:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:/home/ubuntu/workspaces/3rdparty/sglang/python/sglang/kernels/aot/python:{kernel_overlay}:{ROOT}/python:{ROOT}",
      'PYTHONUSERBASE':'/data/sglang-hicache/nsys-2026.5.1/userbase',
      'HOME':'/home/ubuntu','XDG_CACHE_HOME':'/home/ubuntu/.cache',
      'SGLANG_CACHE_DIR':'/home/ubuntu/.cache/sglang','TORCHINDUCTOR_CACHE_DIR':'/home/ubuntu/.cache/sglang/inductor',
      'TRITON_CACHE_DIR':'/home/ubuntu/.cache/sglang/triton','CUDA_CACHE_PATH':'/home/ubuntu/.cache/sglang/nv',
      'FLASHINFER_WORKSPACE_BASE':'/home/ubuntu/.cache/sglang',
      'SGLANG_JIT_CACHE_DIR':'/home/ubuntu/.cache/sglang/jit',
      'SGLANG_JIT_DEEPGEMM_PRECOMPILE':'0','SGLANG_JIT_DEEPGEMM_COMPILE_WORKERS':'1',
      'LD_LIBRARY_PATH':'/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/targets/x86_64-linux/lib',
      'SKBUILD_EDITABLE_SKIP':'1',
      'SGLANG_AOT_KERNELS':'1','SGLANG_R17_AOT_OVERLAY':kernel_overlay,'SGLANG_T002_NVTX_STEP':'1','SGLANG_ENABLE_NVTX_SCHEDULER':'1',
      'T004_TIMELINE_REQUIRED':'1','T004_TIMELINE_MARKER':str(out/'timeline-on'),'T004_TIMELINE_LOG':str(out/'timeline.jsonl'),
      'T004_FPM_ENDPOINT':endpoint_base,'T004_FPM_STOP':str(out/'fpm-stop'),'T004_FPM_LOG':str(out/'fpm.jsonl'),
      'T004_FPM_SOURCE_HEAD':head,'T004_FPM_BINARY_SHA256':pysha,'SGLANG_DISABLE_HICACHE_QUEUE_PREFETCH':'false',
      'SGLANG_HICACHE_L3_DIRECT_IO_MEASURE':'1','T004_DIRECT_IO_MEASURE':'1','T004_EXPECT_DIRECT_IO':'1',
      'T004_AB_MODE':os.environ.get('T004_AB_MODE','on'),'T004_MODE':'ab_measured','T004_MAX_RUNNING_REQUESTS':'8','T004_MAX_QUEUED_REQUESTS':'8','T004_MAX_TOTAL_TOKENS':'32768','T004_BCD_MAX_NEW':os.environ.get('T004_BCD_MAX_NEW','128'),'T004_OCCUPANT_A_MAX_NEW':os.environ.get('T004_OCCUPANT_A_MAX_NEW','1024'),'T004_OCCUPANT_SECONDARY_MAX_NEW':os.environ.get('T004_OCCUPANT_SECONDARY_MAX_NEW','128'),
      'T004_EXPECT_QUEUE_PREFETCH_DISABLED':'1' if os.environ.get('T004_AB_MODE','on')=='off' else '0','SGLANG_DISABLE_HICACHE_QUEUE_PREFETCH':'true' if os.environ.get('T004_AB_MODE','on')=='off' else 'false',
      'T004_EXTENT_DIR':f'/tmp/t004-extent-{run_id}',
      'T004_EXTENT_SIZE':'150994944','T004_EXTENT_FILE_SIZE':'34359738368','T004_EXTENT_MAX_SIZE':'34359738368','T004_EXTENT_MIN_FREE_SPACE':'10737418240','T004_EXTENT_EVICTION_RATIO':'0.9',
      'T38C_RUN_ID':run_id,'T004_SOURCE_HEAD':head,'T004_BINARY_SHA256':pysha,'T004_REQUEST_LOG':str(out/'requests.jsonl'),'T38C_PROBE_PATH':str(out/'probe.jsonl'),'T38C_PROBE_LOG':str(out/'probe.jsonl'),
      'T38C_DURABLE_TRACE_LOG':str(out/'durable.jsonl'),'T004_SERVER_LOG':str(out/'nsys.stderr'),'T004_TIMELINE_LOG':str(out/'timeline.jsonl'),'T004_TIMELINE_MARKER':str(out/'timeline-on'),'T004_REQUEST_LOG':str(out/'requests.jsonl'),'T004_AB_ARM_PATH':str(RUN/f'ab-{run_id}.json'),'SGLANG_R17_AOT_OVERLAY':kernel_overlay,'PROMETHEUS_MULTIPROC_DIR':str(out/'prometheus'),
      'T38C_BUILD_COMPLETE_DEBUG':'1','SGLANG_P2A_TIMING_PROBE':'1','SGLANG_R17_GPU_LOCK_HELD':'1','SGLANG_R17_AOT_OVERLAY':kernel_overlay})
    out.joinpath('prometheus').mkdir()
    Path(env['T004_EXTENT_DIR']).mkdir(parents=True,exist_ok=False)
    for fn in ('timeline.jsonl','fpm.jsonl','probe.jsonl','durable.jsonl','server.log'): (out/fn).touch()
    env['T38C_PROBE_MARKER']=str(out/'probe-on'); env['T38C_DURABLE_TRACE_MARKER']=str(out/'durable-on')
    global_probe_marker=Path('/tmp/t38c-on'); global_durable_marker=Path('/tmp/t38c-durable-trace')
    Path(env['T38C_PROBE_MARKER']).touch(); Path(env['T38C_DURABLE_TRACE_MARKER']).touch()
    Path(env['T004_TIMELINE_MARKER']).touch()
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,memory.total','--format=csv,noheader'],text=True).strip()
    active=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    if active: raise RuntimeError(f'GPU was occupied while holding flock: {active}')
    if subprocess.run(['bash','-lc',"ss -H -ltn 'sport = :30133'"],capture_output=True,text=True).stdout.strip(): raise RuntimeError('port 30133 occupied')
    if shutil.disk_usage(out).free < 3 * 1024**3: raise RuntimeError('less than 3 GiB free for bounded Nsight report/export')
    if not Path('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4').is_dir(): raise RuntimeError('frozen Falcon model path missing')
    metrics_devices=os.environ.get('T004_NSYS_GPU_METRICS_DEVICES','none')
    if metrics_devices != 'none' and os.environ.get('T004_NSYS_GPU_METRICS_SET','ga10x') != 'ga10x':
      raise RuntimeError('T004 GA102 collection requires the ga10x metric set')
    if os.environ.get('T004_AB_MODE','on') not in ('on','off'):
      raise RuntimeError(f"invalid T004_AB_MODE={os.environ.get('T004_AB_MODE')}")
    metrics_options=[]
    if metrics_devices != 'none':
      metrics_options=['--gpu-metrics-devices='+metrics_devices,
        '--gpu-metrics-set='+os.environ.get('T004_NSYS_GPU_METRICS_SET','ga10x'),
        '--gpu-metrics-frequency='+os.environ.get('T004_NSYS_GPU_METRICS_FREQUENCY','1000')]
    manifest={'schema':'t004_nsys_run.v1','run_id':run_id,'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'head':head,'python_sha256':pysha,'python':PY,'gpu':gpu,'model':'/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4','model_revision':'52036ae497a2c0c253e17f98cc8652f2f7082ae3','queue_prefetch':'on' if env['T004_AB_MODE']=='on' else 'off','queue_prefetch_disabled':env['SGLANG_DISABLE_HICACHE_QUEUE_PREFETCH'],'direct_io':True,'cupti_probe_output':str(cupti_probe),'workload':{'max_running':8,'max_queued':8,'max_total_tokens':32768,'bcd_max_new':int(env['T004_BCD_MAX_NEW']),'occupant_a_max_new':int(env['T004_OCCUPANT_A_MAX_NEW']),'occupant_secondary_max_new':int(env['T004_OCCUPANT_SECONDARY_MAX_NEW'])},'extent_dir':env['T004_EXTENT_DIR'],'fpm_endpoint_base':endpoint_base,'fpm_endpoint_dp0':endpoint,'nsys_options':['--trace=cuda,nvtx','--cuda-graph-trace=node:host-only','--gpu-metrics-devices='+metrics_devices,*metrics_options[1:],'--sample=none','--cpuctxsw=none','--capture-range=none','--wait=all']}
    (out/'run-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # sudo env does not preserve caller variables; explicitly pass all run-scoped instrumentation inputs.
    keys=['PYTHONPATH','LD_LIBRARY_PATH','HOME','XDG_CACHE_HOME','TORCHINDUCTOR_CACHE_DIR','SGLANG_CACHE_DIR','TRITON_CACHE_DIR','CUDA_CACHE_PATH','FLASHINFER_WORKSPACE_BASE','SGLANG_JIT_CACHE_DIR']+[k for k in env if k.startswith(('T004_','T38C_','SGLANG_','PROMETHEUS_'))]
    nenv=sorted(set(f'{k}={env[k]}' for k in keys))
    command=['sudo','-n','env',*nenv,'SGLANG_AOT_KERNELS=1','SGLANG_R17_GPU_LOCK_HELD=1','SGLANG_R17_AOT_OVERLAY='+kernel_overlay,NSYS,'profile','--force-overwrite=true',*metrics_options,'--trace=cuda,nvtx','--cuda-graph-trace=node:host-only','--sample=none','--cpuctxsw=none','--capture-range=none','--wait=all','--output',str(out/'falcon'),PY,'-u','-m','sglang.launch_server','--model-path',manifest['model'],'--revision',manifest['model_revision'],'--served-model-name','falcon-h1-t004','--host','127.0.0.1','--port','30133','--tp-size','1','--trust-remote-code','--mem-fraction-static','0.90','--max-running-requests','8','--max-queued-requests','8','--max-total-tokens','32768','--context-length','8192','--mamba-radix-cache-strategy','extra_buffer','--enable-hierarchical-cache','--enable-session-radix-cache','--enable-ready-horizon','--hicache-ratio','2','--hicache-write-policy','write_through','--hicache-io-backend','kernel','--hicache-mem-layout','page_first','--hicache-storage-backend','extent','--hicache-storage-backend-extra-config',json.dumps({'storage_dir':env['T004_EXTENT_DIR'],'extent_size':150994944,'file_size':34359738368,'max_size':34359738368,'min_free_space':10737418240,'eviction_ratio':0.9,'prefetch_threshold':64,'direct_io_measure':True}),'--cuda-graph-backend-prefill','disabled','--cuda-graph-backend-decode','full','--disable-overlap-schedule','--enable-metrics','--enable-forward-pass-metrics','--forward-pass-metrics-worker-id','falcon-t004','--forward-pass-metrics-ipc-name',endpoint_base,'--cuda-graph-max-bs-decode','16','--log-level','info','--device','cuda:0']
    (out/'launch-command.json').write_text(json.dumps(command,indent=2)+'\n')
    try:
      collector=subprocess.Popen([PY,'-u',str(RUN/'collect_fpm_timeline.py'),'--endpoint',endpoint,'--output',env['T004_FPM_LOG'],'--stop',env['T004_FPM_STOP']],cwd=ROOT,env=env,stdout=(out/'fpm-collector.stdout').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
      sys.path.insert(0,str(ROOT/'python'))
      from sglang.srt.observability.forward_pass_metrics import ForwardPassMetrics, ScheduledRequestMetrics, encode as encode_fpm
      deadline=time.monotonic()+20
      while time.monotonic()<deadline and not Path(env['T004_FPM_LOG']).stat().st_size:
        if collector.poll() is not None: raise RuntimeError(f'FPM collector exited rc={collector.returncode}')
        time.sleep(.1)
      if not Path(env['T004_FPM_LOG']).stat().st_size: raise TimeoutError('FPM collector failed to write identity record')
      identity_lines=[json.loads(line) for line in Path(env['T004_FPM_LOG']).read_text().splitlines() if line.strip() and json.loads(line).get('schema')=='t004_fpm_identity.v1']
      if len(identity_lines) != 1:
        raise RuntimeError(f'expected one FPM collector identity row, got {len(identity_lines)}')
      ident=identity_lines[0]
      if ident.get('identity',{}).get('endpoint') != endpoint:
        raise RuntimeError(f"FPM collector endpoint mismatch: expected {endpoint}, got {ident.get('identity',{}).get('endpoint')}")
      pub_probe_ctx=zmq.Context(); pub_probe=pub_probe_ctx.socket(zmq.PUB); pub_probe.bind(endpoint)
      ready_deadline=time.monotonic()+10
      # Publish bounded real ZMQ multipart heartbeats until the SUB collector
      # demonstrably receives one; then hand the IPC endpoint to the scheduler.
      probe_seq=0
      while time.monotonic()<ready_deadline:
        probe_payload=encode_fpm(ForwardPassMetrics(worker_id='collector-readiness-probe',scheduled_requests=ScheduledRequestMetrics(num_prefill_requests=1)))
        pub_probe.send_multipart((b'',probe_seq.to_bytes(8,'big'),probe_payload),flags=zmq.NOBLOCK); probe_seq+=1
        time.sleep(.1)
        rows=[json.loads(line) for line in Path(env['T004_FPM_LOG']).read_text().splitlines() if line.strip()]
        if any(row.get('schema')=='t004_fpm_ready_ack.v1' for row in rows): break
      else:
        pub_probe.close(linger=0); pub_probe_ctx.term()
        raise TimeoutError('FPM SUB collector did not receive PUB readiness heartbeat')
      pub_probe.close(linger=0); pub_probe_ctx.term()
      ready_deadline=time.monotonic()+20
      while time.monotonic()<ready_deadline:
        if collector.poll() is not None: raise RuntimeError(f'FPM collector exited rc={collector.returncode}')
        rows=[json.loads(line) for line in Path(env['T004_FPM_LOG']).read_text().splitlines() if line.strip()]
        if any(row.get('schema')=='t004_fpm_ready_ack.v1' for row in rows): break
        time.sleep(.1)
      else: raise TimeoutError('FPM collector readiness ACK was not recorded')
      with (out/'nsys.stdout').open('w') as so,(out/'nsys.stderr').open('w') as se:
        nsys=subprocess.Popen(command,cwd=ROOT,env=env,stdout=so,stderr=se,start_new_session=True)
        (out/'nsys.pid').write_text(str(nsys.pid)+'\n')
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
          if nsys.poll() is not None: raise RuntimeError(f'Nsight service exited early rc={nsys.returncode}')
          if subprocess.run(['bash','-lc',"ss -H -ltn 'sport = :30133'"],capture_output=True,text=True).stdout.strip(): break
          time.sleep(1)
        else: raise TimeoutError('Nsight service startup timed out')
      import requests
      deadline=time.monotonic()+240
      while time.monotonic()<deadline:
        if nsys.poll() is not None: raise RuntimeError(f'server exited during health wait rc={nsys.returncode}')
        try:
          if requests.get('http://127.0.0.1:30133/health_generate',timeout=2).ok: break
        except requests.RequestException: pass
        time.sleep(1)
      else: raise TimeoutError('Falcon health_generate timeout')
      # Keep the scheduler timeline marker present across fixture checks and
      # the measured arm so RID/step rows cover actual request work.
      drv=subprocess.Popen([PY,'-u','-c',"import sys,os; sys.path.insert(0, '"+str(RUN)+"'); import driver; driver.run_ab_measured()"],cwd=ROOT,env=env,stdout=(out/'driver.stdout').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
      (out/'driver.pid').write_text(str(drv.pid)+'\n')
      try: rc=drv.wait(timeout=600)
      except subprocess.TimeoutExpired:
        os.killpg(drv.pid,signal.SIGTERM)
        try: drv.wait(timeout=20)
        except subprocess.TimeoutExpired: os.killpg(drv.pid,signal.SIGKILL); drv.wait()
        raise TimeoutError(f'T004 A/B/C/D workload exceeded 600 s; preserved artifacts in {out}')
      if rc: raise RuntimeError(f'T004 driver rc={rc}; see {out}/driver.stdout')
      arm=Path(env['T004_AB_ARM_PATH'])
      if not arm.is_file(): raise RuntimeError(f'measured-arm manifest absent: {arm}')
      arm_data=json.loads(arm.read_text())
      l3_rows=arm_data.get('same_run_l3_queries',[])
      measured_rids={record.get('rid') for record in arm_data.get('measured',{}).values()}
      qualified={row.get('rid') for row in l3_rows if row.get('rid') in measured_rids and int(row.get('kv_hit_pages',0)) >= 1786 and int((row.get('sidecar_hits') or {}).get('mamba',0)) >= 1}
      if qualified != measured_rids or len(measured_rids) != 4:
        raise RuntimeError(f'measured arm did not preserve four qualified same-run FULL+MAMBA fixtures: measured={sorted(measured_rids)} qualified={sorted(qualified)}')
      measured=arm_data.get('measured',{})
      if not all(label in measured for label in ('A','B','C','D')):
        raise RuntimeError(f'measured arm lacks complete A/B/C/D request records: {sorted(measured)}')
      # Stop the profiled service only after the complete measured driver has
      # returned and validated A/B/C/D. This closes CUDA trace cleanly instead
      # of leaving Nsight attached to an idle long-lived HTTP service.
      if nsys and nsys.poll() is None:
        server_pids=subprocess.check_output(['bash','-lc',"pgrep -f '^/home/ubuntu/venvs/sglang-3090/bin/python -u -m sglang.launch_server .*--port 30133'"],text=True).split()
        if not server_pids: raise RuntimeError('profiled Falcon server PID not found for graceful post-workload shutdown')
        os.kill(int(server_pids[0]),signal.SIGTERM)
      Path(env['T004_FPM_STOP']).touch()
      if collector and collector.poll() is None:
        try: collector.wait(timeout=15)
        except subprocess.TimeoutExpired: collector.terminate(); collector.wait(timeout=10)
      # Markers bracket the measured interval and provide same-process wall/mono anchors.
      anchors=[{'wall_ns':int(x['ts_wall_ns']),'mono_ns':int(x['ts_mono_ns']),'event':x.get('evt')} for x in (json.loads(line) for line in Path(env['T004_TIMELINE_LOG']).read_text().splitlines() if line.strip()) if x.get('evt') in ('request_enqueue','scheduler_step_start')]
      (out/'clock-anchors.json').write_text(json.dumps(anchors,indent=2)+'\n')
      try: nsys.wait(timeout=180)
      except subprocess.TimeoutExpired:
        os.killpg(nsys.pid,signal.SIGTERM)
        try: nsys.wait(timeout=30)
        except subprocess.TimeoutExpired: os.killpg(nsys.pid,signal.SIGKILL); nsys.wait()
        raise TimeoutError(f'Nsight report drain exceeded 180 s; preserved raw capture in {out}')
      if nsys.returncode: raise RuntimeError(f'Nsight rc={nsys.returncode}; see {out}')
      rep=out/'falcon.nsys-rep'
      if not rep.is_file() or not rep.stat().st_size: raise RuntimeError('missing Nsight report')
      subprocess.run(['sudo','-n',NSYS,'export','--type','sqlite','--output',str(out/'falcon.sqlite'),'--force-overwrite=true',str(rep)],cwd=ROOT,check=True)
      (out/'capture-status.json').write_text(json.dumps({'nsys_rc':nsys.returncode,'driver_rc':rc,'report_bytes':rep.stat().st_size,'head':head,'finished_wall_ns':time.time_ns()},indent=2)+'\n')
    finally:
      if nsys and nsys.poll() is None:
        try: os.killpg(nsys.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: nsys.wait(timeout=40)
        except subprocess.TimeoutExpired:
          try: os.killpg(nsys.pid,signal.SIGKILL)
          except ProcessLookupError: pass
      Path(env['T004_FPM_STOP']).touch()
      if collector and collector.poll() is None:
        try: collector.wait(timeout=10)
        except subprocess.TimeoutExpired: collector.terminate(); collector.wait(timeout=10)
      Path(env['T004_TIMELINE_MARKER']).unlink(missing_ok=True); Path(env['T38C_PROBE_MARKER']).unlink(missing_ok=True); Path(env['T38C_DURABLE_TRACE_MARKER']).unlink(missing_ok=True)
      (out/'gpu-after-cleanup.csv').write_text(subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_memory --format=csv,noheader'],capture_output=True,text=True).stdout)
      try:
        sudo=subprocess.run(['sudo','-n','rm','-f',endpoint.removeprefix('ipc://'),endpoint_base.removeprefix('ipc://')],capture_output=True,text=True)
        if sudo.returncode:
          (out/'ipc-cleanup-warning.txt').write_text(sudo.stderr)
      except Exception as exc:
        (out/'ipc-cleanup-warning.txt').write_text(repr(exc))
      if lf is not None: lf.close()
if __name__=='__main__': main()
