#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Use Nsight Compute Python API to profile a launched mainline clean run."""
import argparse, contextlib, fcntl, importlib.util, json, os, pathlib, signal, subprocess, sys, time
from ncu_report import NcuReport

ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNROOT = pathlib.Path(__file__).resolve().parent
PYTHON = "/home/ubuntu/venvs/sglang-3090/bin/python"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=("prefill", "decode"), required=True)
    p.add_argument("--concurrency", type=int, choices=(8, 16), required=True)
    p.add_argument("--trial", type=int, required=True)
    a = p.parse_args()
    tag = f"mainline-ncu-{a.stage}-c{a.concurrency}-t{a.trial}"
    out = RUNROOT / tag
    out.mkdir()
    pattern = (r".*(Marlin<__nv_bfloat16,.*|ampere_bf16_s16816gemm_bf16_128x128.*)"
               if a.stage == "prefill" else
               r".*(Marlin<__nv_bfloat16,.*|causal_conv1d_update_kernel.*|_selective_scan_update_kernel|ampere_bf16_s16816gemm_bf16_64x64.*)")
    user = importlib.util.find_spec("ncu_report")
    if user is None:
        raise RuntimeError("ncu_report Python binding unavailable")
    # configure() and all NCU API work run under the caller's user identity;
    # sudo is used only for the exact counter-profiled launch beneath it.
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip():
            raise SystemExit("GPU compute process active before NCU trial")
        cfg = {
            "rules": [{"match": {"regex": pattern}, "metrics": [
                "sm__throughput.avg.pct_of_peak_sustained_elapsed",
                "smsp__warps_active.avg.pct_of_peak_sustained_active",
                "dram__throughput.avg.pct_of_peak_sustained_elapsed",
                "lts__t_sector_hit_rate.pct",
            ], "launch_count": 8}],
            "output": str(out / "ncu-report"),
        }
        ncu = NcuReport()
        ncu.configure(cfg)
        env = os.environ.copy()
        env.update({"PYTHONPATH": f"/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python", "SGLANG_AOT_KERNELS": "1"})
        cmd = ["sudo", "-n", "/home/ubuntu/venvs/sglang-3090/bin/python", str(RUNROOT/"run_mainline_measurement.py"), "--concurrency", str(a.concurrency), "--trial", str(a.trial)]
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(out/"trial.stdout","w"), stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None:
                time.sleep(1)
            ncu.stop()
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try: proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        (out/"capture-status.json").write_text(json.dumps({"stage":a.stage,"concurrency":a.concurrency,"trial":a.trial,"returncode":proc.returncode,"tree_head":subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),"kernel_regex":pattern,"ncu_config":cfg},indent=2)+"\n")
        if proc.returncode: raise SystemExit(proc.returncode)

if __name__ == "__main__": main()
