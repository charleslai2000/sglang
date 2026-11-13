#!/usr/bin/env python3
"""T003 reuse of the archived Falcon R17 runner with full-lifetime NVTX/CUDA capture.

Unlike the earlier prefix-trigger attempt, capture-range=none observes the existing
inner dynamic scheduler step ranges; GPU metrics are filtered to the saved workload
wall interval during analysis. No profiler hooks or production instrumentation added.
"""
import fcntl, json, os, pathlib, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).resolve().parent
LOCK="/tmp/f1-r16b-gpu-exclusive.lock"
PY="/home/ubuntu/venvs/sglang-3090/bin/python"
NSYS="/usr/local/bin/nsys"
OVERLAY="/tmp/r17-ncu-overlay-NYnhWh"

def main():
    if len(sys.argv)!=4 or sys.argv[1] not in ("8","16") or not sys.argv[2].isdigit() or not sys.argv[3].isdigit():
        raise SystemExit("usage: run_nsys.py {8|16} TRIAL REQUEST_COUNT")
    c,trial,request_count=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]);tag=f"t003-nsys-c{c}-t{trial}-n{request_count}"
    out=HERE/tag
    if out.exists():raise SystemExit(f"refusing existing output {out}")
    out.mkdir(parents=True)
    with open(LOCK,"w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        active=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
        if active:raise SystemExit(f"GPU process active: {active}")
        for port in (30000,30107,30160):
            r=subprocess.run(["bash","-lc",f"ss -H -ltn 'sport = :{port}'"],capture_output=True,text=True)
            if r.stdout.strip():raise SystemExit(f"port {port} occupied: {r.stdout.strip()}")
        env=os.environ.copy();env["SGLANG_R17_GPU_LOCK_HELD"]="1"
        git_prefix=["/usr/bin/sudo","-u","ubuntu","git","-C",str(ROOT)] if os.geteuid()==0 else ["git","-C",str(ROOT)]
        env["PYTHONPATH"]=f"/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:{OVERLAY}:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python"+((":"+env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
        env["SGLANG_R17_AOT_OVERLAY"]=OVERLAY;env["SGLANG_AOT_KERNELS"]="1"
        env["SGLANG_ENABLE_NVTX_SCHEDULER"]="1";env["SGLANG_T002_NVTX_STEP"]="1"
        cmd=["sudo","-n","env",f"PYTHONPATH={env['PYTHONPATH']}","SGLANG_AOT_KERNELS=1","SGLANG_ENABLE_NVTX_SCHEDULER=1","SGLANG_T002_NVTX_STEP=1","SGLANG_R17_GPU_LOCK_HELD=1",f"SGLANG_R17_AOT_OVERLAY={OVERLAY}",NSYS,"profile","--force-overwrite=true","--gpu-metrics-devices=0","--gpu-metrics-set=ga10x","--gpu-metrics-frequency=1000","--trace=cuda,nvtx","--cuda-graph-trace=node","--cuda-event-trace=false","--sample=none","--cpuctxsw=none","--capture-range=none","--stats=false","--output",str(out/"falcon"),PY,str(ROOT/"control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/run_mainline_measurement.py"),"--concurrency",str(c),"--trial",str(trial),"--output-dir",str(out/"measurement"),"--request-count",str(request_count) ]
        start=time.time_ns()
        with open(out/"nsys.stdout","w") as stdout,open(out/"nsys.stderr","w") as stderr:
            p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True);rc=p.wait()
        (out/"capture-status.json").write_text(json.dumps({"concurrency":c,"trial":trial,"nsys_returncode":rc,"host_start_epoch_ns":start,"head":subprocess.check_output(git_prefix+["rev-parse","HEAD"],text=True).strip(),"capture_range":"none","trace":"cuda,nvtx","gpu_metric_frequency_hz":1000,"request_count":request_count},indent=2)+"\n")
        if rc:raise SystemExit(f"Nsight run failed rc={rc}; inspect {out}")
        run=out/"measurement"
        if not (run/"summary.json").is_file():raise SystemExit("measurement summary missing")
        rep=out/"falcon.nsys-rep"
        if not rep.is_file():raise SystemExit("Nsight report missing")
        export=subprocess.run(["sudo","-n",NSYS,"export","--type=sqlite","--output",str(out/"falcon.sqlite"),"--force-overwrite=true",str(rep)],cwd=ROOT)
        if export.returncode:raise SystemExit(f"SQLite export failed {export.returncode}")
        (out/"measurement-summary.json").write_text((run/"summary.json").read_text())
        (out/"decode-status.json").write_text(json.dumps({"export_rc":export.returncode,"report_bytes":rep.stat().st_size,"sqlite_bytes":(out/"falcon.sqlite").stat().st_size,"summary":json.loads((run/"summary.json").read_text())},indent=2)+"\n")
if __name__=="__main__":main()
