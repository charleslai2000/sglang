#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Run one bounded Falcon forward between scheduler CUDA Profiler API markers.

NCU starts this process with --profile-from-start off. The HTTP /start_profile
and /stop_profile path invokes cudaProfilerStart/Stop inside the scheduler's
actual CUDA context, after server initialization and graph warmup.
"""
import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNROOT = pathlib.Path(__file__).resolve().parent
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"
PYTHON = "/home/ubuntu/venvs/sglang-3090/bin/python"
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
REVISION = "52036ae497a2c0c253e17f98cc8652f2f7082ae3"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=("prefill", "decode"), required=True)
    p.add_argument("--concurrency", type=int, choices=(8, 16), required=True)
    p.add_argument("--trial", type=int, required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--profile-from-start", action="store_true")
    a = p.parse_args()
    out = pathlib.Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = f"http://127.0.0.1:{a.port}"
    manifest = {
        "branch": git("branch", "--show-current"),
        "HEAD": git("rev-parse", "HEAD"),
        "stage": a.stage,
        "concurrency": a.concurrency,
        "trial": a.trial,
        "model": MODEL,
        "model_revision": REVISION,
        "runner": str(pathlib.Path(__file__).resolve()),
        "runner_sha256": sha(__file__),
        "python": sys.executable,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "cap_eff_amb": pathlib.Path("/proc/self/status").read_text().splitlines(),
        "port": a.port,
        "profile_boundary": "scheduler CUDA Profiler API start/stop after server warmup; NCU profile-from-start=off",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    workload_path = RUNROOT / "provenance-20c837f1" / "workload.json"
    rows = json.loads(workload_path.read_text())["workload"]
    row = rows[0]
    prompt_ids = row["prompt_token_ids"]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:/tmp/f1-r3-kernel-overlay:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python",
        "SGLANG_T002_NVTX_STEP": "1",
        "SGLANG_AOT_KERNELS": "1",
        "SGLANG_R17_GPU_LOCK_HELD": "1",
        "SGLANG_PROFILE_V2": "0",
        "SGLANG_ENABLE_METRICS_DEVICE_TIMER": "1",
        "PROMETHEUS_MULTIPROC_DIR": str(out / "prometheus"),
    })
    (out / "prometheus").mkdir()
    ipc = f"ipc:///tmp/sglang-r17-marker-{a.stage}-c{a.concurrency}-t{a.trial}.sock"
    cmd = [PYTHON, "-u", "-m", "sglang.launch_server",
        "--model-path", MODEL, "--revision", REVISION,
        "--served-model-name", f"falcon-ncu-{a.stage}-c{a.concurrency}",
        "--host", "127.0.0.1", "--port", str(a.port), "--tp-size", "1",
        "--trust-remote-code", "--mem-fraction-static", "0.90",
        "--max-running-requests", str(a.concurrency), "--context-length", "8192",
        "--max-mamba-cache-size", "83", "--mamba-radix-cache-strategy", "extra_buffer",
        "--cuda-graph-max-bs-decode", "16", "--enable-forward-pass-metrics",
        "--forward-pass-metrics-worker-id", f"ncu-{a.stage}-c{a.concurrency}-t{a.trial}",
        "--forward-pass-metrics-ipc-name", ipc,
        "--cuda-graph-backend-prefill", "disabled", "--cuda-graph-backend-decode", "full",
        "--enable-metrics", "--log-level", "info"]
    if a.profile_from_start:
        ncu_cmd = [
            "/usr/local/cuda-12.9/bin/ncu",
            "--nvtx",
            "--nvtx-include", "sglang.step",
            "--replay-mode", "range",
            "--metrics",
            "gpu__time_duration.avg,sm__cycles_active.avg.pct_of_peak_sustained_elapsed,"
            "sm__throughput.avg.pct_of_peak_sustained_elapsed,"
            "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,"
            "dram__bytes_read.sum,dram__bytes_write.sum,"
            "gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed",
            "--launch-count", "1",
            "--target-processes", "all",
            "--export", str(out / "ncu-report"),
            "--force-overwrite",
            "--",
            PYTHON, str(pathlib.Path(__file__).resolve()),
            "--stage", a.stage,
            "--concurrency", str(a.concurrency),
            "--trial", str(a.trial),
            "--port", str(a.port),
            "--out", str(out / "captured-workload"),
        ]
        with open(out / "ncu.stdout", "w") as stdout, open(out / "ncu.stderr", "w") as stderr:
            completed = subprocess.run(ncu_cmd, cwd=ROOT, env=os.environ.copy(),
                                       stdout=stdout, stderr=stderr, timeout=1800)
        if completed.returncode:
            raise RuntimeError(f"NCU range-replay capture failed: rc={completed.returncode}")
        return

    server = None
    ncu_proc = None
    ncu_stdout = None
    ncu_stderr = None
    profile_started = False
    try:
        with open(LOCK, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if git("branch", "--show-current") != "3090-24g-hicache":
                raise RuntimeError("wrong branch")
            gpu_pids = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
            if gpu_pids:
                raise RuntimeError(f"GPU process already active: {gpu_pids}")
            try:
                if requests.get(base + "/health", timeout=2).ok:
                    raise RuntimeError(f"port {a.port} is already serving")
            except requests.ConnectionError:
                pass
            server = subprocess.Popen(cmd, cwd=ROOT, env=env,
                stdout=open(out / "server.log", "w"), stderr=subprocess.STDOUT,
                start_new_session=True)
            (out / "server.pid").write_text(str(server.pid) + "\n")
            for _ in range(600):
                if server.poll() is not None:
                    raise RuntimeError(f"server exited rc={server.returncode}")
                try:
                    if requests.get(base + "/health", timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError("server health timeout")
            # Run a complete warmup request before any CUDA profiler marker.
            warm = requests.post(base + "/generate", json={
                "input_ids": prompt_ids,
                "sampling_params": {"temperature": 0, "top_p": 1, "max_new_tokens": 2, "ignore_eos": True},
                "stream": False,
            }, timeout=300)
            warm.raise_for_status()
            warm_json = warm.json()
            if warm_json.get("error"):
                raise RuntimeError(f"warmup request error: {warm_json['error']}")
            if a.profile_from_start:
                ncu_cmd = [
                    "/usr/local/cuda-12.9/bin/ncu",
                    "--nvtx",
                    "--nvtx-include", "sglang.step",
                    "--replay-mode", "range",
                    "--graph-profiling", "graph",
                    "--metrics",
                    "gpu__time_duration.avg,sm__cycles_active.avg.pct_of_peak_sustained_elapsed,"
                    "sm__throughput.avg.pct_of_peak_sustained_elapsed,"
                    "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,"
                    "dram__bytes_read.sum,dram__bytes_write.sum,"
                    "gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed",
                    "--launch-count", "1",
                    "--target-processes", "all",
                    "--export", str(out / "ncu-report"),
                    "--force-overwrite",
                ]
                ncu_stdout = open(out / "ncu.stdout", "w")
                ncu_stderr = open(out / "ncu.stderr", "w")
                ncu_proc = subprocess.Popen(
                    ncu_cmd,
                    env=env,
                    stdout=ncu_stdout,
                    stderr=ncu_stderr,
                    start_new_session=True,
                )
                time.sleep(3)
                if ncu_proc.poll() is not None:
                    raise RuntimeError(f"ncu exited before Scheduler capture: {ncu_proc.returncode}")
            (out / "warmup.json").write_text(json.dumps({"status": warm.status_code, "meta_info": warm_json.get("meta_info", {})}, indent=2) + "\n")
            if a.stage == "prefill":
                requests.post(base + "/flush_cache", timeout=90).raise_for_status()
                sampling = {"temperature": 0, "top_p": 1, "max_new_tokens": 1, "ignore_eos": True}
            else:
                sampling = {"temperature": 0, "top_p": 1, "max_new_tokens": 24, "ignore_eos": True}
            start_body = {"activities": ["CUDA_PROFILER"], "profile_id": f"ncu-{a.stage}-c{a.concurrency}-t{a.trial}", "num_steps": 1}
            start = requests.post(base + "/start_profile", json=start_body, timeout=30)
            start.raise_for_status()
            profile_started = True
            (out / "cuda-profiler-start.txt").write_text(start.text)
            request = requests.post(base + "/generate", json={
                "input_ids": prompt_ids,
                "sampling_params": sampling,
                "stream": False,
                "return_cached_tokens_details": True,
            }, timeout=600)
            request.raise_for_status()
            result = request.json()
            if result.get("error"):
                raise RuntimeError(f"profile request error: {result['error']}")
            (out / "profiled-request.json").write_text(json.dumps({
                "status": request.status_code,
                "meta_info": result.get("meta_info", {}),
                "output_ids": result.get("output_ids", []),
            }, indent=2) + "\n")
            stop = requests.post(base + "/stop_profile", timeout=60)
            stop.raise_for_status()
            profile_started = False
            if a.profile_from_start and ncu_proc is not None:
                ncu_proc.wait(timeout=600)
                if ncu_proc.returncode:
                    raise RuntimeError(f"ncu failed rc={ncu_proc.returncode}")
                ncu_proc = None
            (out / "cuda-profiler-stop.txt").write_text(stop.text)
            status = {
                "server_pid": server.pid,
                "server_uid": os.stat(f"/proc/{server.pid}").st_uid,
                "scheduler_processes": subprocess.check_output(
                    ["ps", "-eo", "pid,ppid,uid,comm,args"], text=True
                ).splitlines(),
                "gpu_compute_pids_after_profile": subprocess.check_output(
                    ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"], text=True
                ).strip(),
                "captured_stage": a.stage,
                "warmup_completed_before_cudaProfilerStart": True,
                "request_completed_before_cudaProfilerStop": True,
                "returncode": 0,
            }
            (out / "capture-driver-status.json").write_text(json.dumps(status, indent=2) + "\n")
            print(json.dumps({"out": str(out), "profiled_status": request.status_code,
                "meta_info": result.get("meta_info", {})}, indent=2), flush=True)
    finally:
        if profile_started:
            try:
                requests.post(base + "/stop_profile", timeout=15)
            except requests.RequestException:
                pass
        if ncu_proc is not None and ncu_proc.poll() is None:
            try:
                os.killpg(ncu_proc.pid, signal.SIGINT)
                ncu_proc.wait(timeout=30)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
        if ncu_stdout is not None:
            ncu_stdout.close()
        if ncu_stderr is not None:
            ncu_stderr.close()
        if server is not None:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(server.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                server.wait()


if __name__ == "__main__":
    main()
