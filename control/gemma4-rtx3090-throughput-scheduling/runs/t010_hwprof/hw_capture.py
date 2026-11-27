#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Bounded Gemma4 forward capture between scheduler CUDA Profiler API markers.

Adapted from control/falcon-h1-3090-hicache-perf/runs/R17-.../ncu_marker_capture.py:
NCU starts this process with --profile-from-start off; /start_profile and
/stop_profile invoke cudaProfilerStart/Stop inside the real scheduler CUDA
context, after server init and graph warmup, so no capture-phase kernel is ever
profiled. Each phase is one start/stop session.
"""
import argparse, json, os, pathlib, random, signal, subprocess, sys, threading, time
import requests

ROOT = pathlib.Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
PYTHON = "/home/ubuntu/venvs/sglang-3090/bin/python"
DATA = "/data/sglang-hicache/gemma4"
VENV_SITE = "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages"
AOT = "/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package"
OVERLAY = f"{ROOT}/control/gemma4-w4a16-3090-performance-capacity/runs/overlay"
RUNS = f"{ROOT}/control/gemma4-w4a16-3090-performance-capacity/runs"

def git(*a): return subprocess.check_output(["git", "-C", str(ROOT), *a], text=True).strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phases", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = pathlib.Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    (out / "phases").mkdir(exist_ok=True)
    base = f"http://127.0.0.1:{a.port}"
    (out / "manifest.json").write_text(json.dumps({
        "HEAD": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "phases": a.phases, "port": a.port, "runner_sha256": __import__("hashlib").sha256(open(__file__,'rb').read()).hexdigest(),
        "boundary": "scheduler CUDA_PROFILER start/stop after warmup; NCU --profile-from-start off",
        "ncu": subprocess.run(["/usr/local/cuda-12.9/bin/ncu","--version"],capture_output=True,text=True).stdout.splitlines()[1].strip(),
    }, indent=2) + "\n")
    l3 = out / "l3-extent"; l3.mkdir(exist_ok=True)
    args = [PYTHON, "-u", "-m", "sglang.launch_server",
        "--model-path", f"{DATA}/model", "--trust-remote-code", "--host", "127.0.0.1", "--port", str(a.port),
        "--context-length", "131072", "--max-running-requests", "32", "--mem-fraction-static", os.environ.get("HWPROF_MEM_FRACTION", ".94"),
        "--kv-cache-dtype", "fp8_e5m2", "--attention-backend", "triton",
        "--cuda-graph-backend-decode", "full", "--cuda-graph-max-bs-decode", "32",
        "--log-level", "warning", "--enable-metrics", "--skip-server-warmup",
        "--enable-hierarchical-cache", "--hicache-size", "8", "--hicache-write-policy", "write_back",
        "--hicache-io-backend", "kernel", "--hicache-mem-layout", "page_first",
        "--hicache-host-memory-mode", "cache", "--hicache-storage-backend", "extent",
        "--hicache-storage-backend-extra-config",
        json.dumps({"storage_dir": str(l3), "extent_size": 67108864, "file_size": 34359738368,
                    "max_size": 34359738368, "min_free_space": 1073741824}),
        "--hicache-storage-prefetch-policy", "wait_complete", "--chunked-prefill-size", "4096"]
    (out / "launch-argv.txt").write_text(" ".join(args) + "\n")
    env = os.environ.copy()
    env.update({"PYTHONNOUSERSITE": "1", "SGLANG_GEMMA4_SWA_POOL_TOKENS": "65536",
        "PYTHONPATH": f"{RUNS}:{AOT}:{ROOT}/python:{VENV_SITE}:{ROOT}/python/sglang/kernels/aot/python:{OVERLAY}",
        "LD_LIBRARY_PATH": f"{VENV_SITE}/torch/lib:/usr/local/cuda-12.9/lib64",
        "SGLANG_CACHE_DIR": f"{DATA}/cache", "HF_HOME": f"{DATA}/cache/hf-home",
        "HF_DATASETS_CACHE": f"{DATA}/cache/datasets",
        "SGLANG_ENABLE_METRICS_DEVICE_TIMER": "1"})
    server = subprocess.Popen(args, cwd=ROOT, env=env, stdout=open(out/"server.log","w"),
                              stderr=subprocess.STDOUT, start_new_session=True)
    (out/"server.pid").write_text(str(server.pid)+"\n")
    try:
        for _ in range(900):
            if server.poll() is not None: raise RuntimeError(f"server rc={server.returncode}")
            try:
                if requests.get(base+"/health_generate", timeout=3).ok: break
            except requests.RequestException: pass
            time.sleep(2)
        else: raise TimeoutError("health timeout")
        rng = random.Random(20261127)
        def toks(n): return [rng.randrange(1000, 100000) for _ in range(n)]
        # full warmup: real extend+decode so graph capture and allocator warm state exist
        w = requests.post(base+"/generate", json={"input_ids": toks(1024),
            "sampling_params": {"temperature": 0, "max_new_tokens": 8}}, timeout=600)
        w.raise_for_status(); (out/"warmup.json").write_text(json.dumps(w.json().get("meta_info",{}), indent=2))
        for ph in a.phases.split(","):
            pd = out/"phases"/ph; pd.mkdir(exist_ok=True)
            if ph.startswith("ext") or ph == "long":
                n = 32768 if ph == "long" else int(ph[3:]); nout = 4 if ph == "long" else 1
            elif ph.startswith("dec"):
                n = 1024; nout = 16
            def one(tag, ids, nout, store):
                t0 = time.time()
                r = requests.post(base+"/generate", json={"input_ids": ids,
                    "sampling_params": {"temperature": 0, "max_new_tokens": nout}}, timeout=3600)
                r.raise_for_status(); j = r.json()
                store[tag] = {"wall_s": time.time()-t0, "meta": j["meta_info"], "n_out": len(j.get("output_ids", []))}
            store = {}
            if ph.startswith("dec"):
                batch = int(ph[3:]); ths = [threading.Thread(target=one, args=(f"c{i}", toks(n), nout, store)) for i in range(batch)]
                rs = requests.post(base+"/start_profile", json={"activities": ["CUDA_PROFILER"], "num_steps": 1}, timeout=60)
                (pd/"start.txt").write_text(f"{rs.status_code} {rs.text}")
                [t.start() for t in ths]; [t.join() for t in ths]
            else:
                rs = requests.post(base+"/start_profile", json={"activities": ["CUDA_PROFILER"], "num_steps": 1}, timeout=60)
                (pd/"start.txt").write_text(f"{rs.status_code} {rs.text}")
                one("single", toks(n), nout, store)
            up = requests.post(base+"/stop_profile", timeout=120)
            # The stage trigger auto-stops after num_steps, so a 500 "not in progress"
            # here is expected and must not abort the phase sequence.
            (pd/"stop.txt").write_text(f"{up.status_code} {up.text}")
            (pd/"result.json").write_text(json.dumps(store, indent=2))
            print(json.dumps({"phase": ph, **{k: {"wall_s": round(v["wall_s"],3),
                "prompt": v["meta"].get("prompt_tokens"), "completion": v["meta"].get("completion_tokens")} for k,v in store.items()}}), flush=True)
    finally:
        try: requests.post(base+"/stop_profile", timeout=10)
        except Exception: pass
        try: os.killpg(server.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: server.wait(timeout=90)
        except subprocess.TimeoutExpired: os.killpg(server.pid, signal.SIGKILL)

if __name__ == "__main__":
    main()
