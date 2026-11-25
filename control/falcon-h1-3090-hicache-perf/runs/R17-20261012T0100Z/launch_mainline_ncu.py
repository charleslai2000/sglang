#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Profile selected kernels from one clean mainline workload via NCU attach.

The unprivileged owner launches SGLang and owns the shared GPU lock. Root NCU
attaches only to that process tree, avoiding privilege/lock-file conflicts.
"""
import argparse, fcntl, json, os, pathlib, signal, subprocess, sys, time
import requests
ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNROOT = pathlib.Path(__file__).resolve().parent
PY = "/home/ubuntu/venvs/sglang-3090/bin/python"
NCU = "/usr/local/cuda-12.9/bin/ncu"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=("prefill", "decode"), required=True)
    p.add_argument("--concurrency", choices=("8", "16"), required=True)
    p.add_argument("--trial", type=int, default=1)
    a = p.parse_args()
    tag = f"mainline-ncu-{a.stage}-c{a.concurrency}-t{a.trial}-direct"
    out = RUNROOT / tag
    out.mkdir()
    pattern = ("regex:.*(Marlin<__nv_bfloat16,.*|ampere_bf16_s16816gemm_bf16_128x128.*)"
               if a.stage == "prefill" else
               "regex:.*(Marlin<__nv_bfloat16,.*|causal_conv1d_update_kernel.*|_selective_scan_update_kernel|ampere_bf16_s16816gemm_bf16_64x64.*)")
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
            raise SystemExit("GPU compute process active before NCU trial")
        try:
            if requests.get("http://127.0.0.1:30160/health", timeout=2).ok:
                raise SystemExit("port 30160 already active")
        except requests.RequestException:
            pass
        env = os.environ.copy()
        env.update({"PYTHONPATH": f"/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python", "SGLANG_AOT_KERNELS": "1", "SGLANG_R17_GPU_LOCK_HELD": "1"})
        ncu_cmd = ["sudo", "-n", NCU, "--set", "full", "--kernel-name-base", "demangled", "--kernel-name", pattern, "--launch-count", "8", "--target-processes", "all", "--csv", "--page", "raw", "--print-metric-attribution", "--force-overwrite", "-o", str(out / "ncu-report"), PY]
        trial_args = [str(RUNROOT/"run_mainline_measurement.py"), "--concurrency", a.concurrency, "--trial", str(a.trial)]
        with open(out/"ncu.stdout","w") as ncu_out, open(out/"ncu.stderr","w") as ncu_err:
            ncu = subprocess.Popen(ncu_cmd + trial_args, cwd=ROOT, env=env, stdout=ncu_out, stderr=ncu_err, start_new_session=True)
            rc = ncu.wait()
        result_dir = RUNROOT/f"mainline-gpu-only-c{a.concurrency}-t{a.trial}"
        trial_summary = result_dir/"summary.json"
        status = {"stage":a.stage,"concurrency":int(a.concurrency),"trial":a.trial,"ncu_returncode":rc,"trial_summary_exists":trial_summary.is_file(),"tree_head":subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),"kernel_regex":pattern}
        (out/"capture-status.json").write_text(json.dumps(status,indent=2)+"\n")
        if rc != 0 or not trial_summary.is_file(): raise SystemExit(f"NCU rc={rc}, trial summary exists={trial_summary.is_file()}")

if __name__ == "__main__": main()
