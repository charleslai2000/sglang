#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Launch a frozen 40-request R17 workload from the authorized mainline tree.

Reuses archived R17 workload, ForwardPassMetrics decoding, NVML sampler and
server configuration. Writes source/runtime identities before launch; clean
c8/c16 runs are recorded separately and never inherit R17's commit identity.
"""
import argparse, asyncio, fcntl, hashlib, importlib, json, os, pathlib, secrets, signal, subprocess, sys, time
import aiohttp, msgspec, requests, zmq
ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNROOT = pathlib.Path(__file__).resolve().parent
PROV = RUNROOT / "provenance-20c837f1"
PYTHON = "/home/ubuntu/venvs/sglang-3090/bin/python"
BASE = "http://127.0.0.1:30160"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
REV = "52036ae497a2c0c253e17f98cc8652f2f7082ae3"

def git(*args):
    if os.geteuid() == 0:
        return subprocess.check_output(
            ["/usr/bin/sudo", "-u", "ubuntu", "git", "-C", str(ROOT), *args],
            text=True,
        ).strip()
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()

def module_record(name):
    module = importlib.import_module(name)
    path = pathlib.Path(module.__file__).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}

def tracked_identity():
    paths = git("diff", "--name-only", "HEAD").splitlines()
    digest = hashlib.sha256()
    entries = []
    for rel in sorted(paths):
        data = (ROOT / rel).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        entries.append({"path": rel, "sha256": sha})
        digest.update(rel.encode() + b"\0" + data)
    return digest.hexdigest(), entries

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, choices=(8, 16), required=True)
    parser.add_argument("--trial", type=int, required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--request-count", type=int, default=40)
    parser.add_argument("--cupti-steps", type=int, default=0)
    parser.add_argument("--cupti-output", default="")
    args = parser.parse_args()
    if git("branch", "--show-current") != "3090-24g-hicache":
        raise SystemExit("refusing run outside authorized branch")
    tag = f"mainline-gpu-only-c{args.concurrency}-t{args.trial}"
    out = pathlib.Path(args.output_dir) if args.output_dir else RUNROOT / tag
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to reuse non-empty run directory {out}")
    out.mkdir(parents=True, exist_ok=True)
    aot_overlay = os.environ.get("SGLANG_R17_AOT_OVERLAY", "/tmp/f1-r3-kernel-overlay")
    sys.path[:0] = [aot_overlay, str(ROOT / "python"), str(ROOT / "python/sglang/kernels/aot/python")]
    from sglang.srt.observability.forward_pass_metrics import ForwardPassMetrics
    import torch
    import sgl_kernel.sm86.common_ops as common_ops
    workload = json.loads((PROV / "workload.json").read_text())
    if not 1 <= args.request_count <= 40:
        raise SystemExit("--request-count must be in [1, 40]")
    rows = workload["workload"][:args.request_count]
    workload_sha = hashlib.sha256(json.dumps([r["prompt_token_ids"] for r in rows], separators=(",", ":")).encode()).hexdigest()
    dirty_sha, dirty_paths = tracked_identity()
    modules = {name: module_record(name) for name in (
        "sglang", "sglang.srt.models.falcon_h1", "sglang.srt.server_args",
        "sglang.srt.managers.scheduler", "sglang.srt.mem_cache.unified_radix_cache",
        "sgl_kernel", "sgl_kernel.load_utils", "flashinfer")}
    modules["sgl_kernel.sm86.common_ops"] = {
        "path": str(pathlib.Path(common_ops.__file__).resolve()),
        "sha256": hashlib.sha256(pathlib.Path(common_ops.__file__).read_bytes()).hexdigest(),
    }
    tag_ipc = f"ipc:///tmp/sglang-mainline-{tag}.sock"
    endpoint = tag_ipc + ".0"
    sockpath = endpoint.removeprefix("ipc://")
    manifest = {
        "branch": git("branch", "--show-current"), "HEAD": git("rev-parse", "HEAD"),
        "tracked_dirty_sha256": dirty_sha, "tracked_dirty_files": dirty_paths,
        "python": sys.executable, "python_version": sys.version,
        "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
        "modules": modules, "model": MODEL, "model_revision": REV,
        "workload_sha256": workload_sha, "workload_source_sha256": workload["sha256"],
        "requests": len(rows), "prompt_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens_per_request": 128, "concurrency": args.concurrency,
        "TP": 1, "context_length": 8192, "mem_fraction_static": 0.90,
        "max_running_requests": 16, "max_mamba_cache_size": 83,
        "decode_graph": "full", "prefill_graph": "disabled", "hicache": "off",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 100000)
    sub.connect(endpoint)
    decoder = msgspec.msgpack.Decoder(ForwardPassMetrics)
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    events, errors = [], []
    srv = sampler = None

    async def request_batch():
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800), connector=aiohttp.TCPConnector(limit=args.concurrency)) as session:
            sem = asyncio.Semaphore(args.concurrency)
            async def request(row):
                async with sem:
                    t0 = time.perf_counter()
                    async with session.post(BASE + "/generate", json={
                        "input_ids": row["prompt_token_ids"],
                        "sampling_params": {"temperature": 0, "top_p": 1, "max_new_tokens": 128, "ignore_eos": True},
                        "stream": False, "return_cached_tokens_details": True,
                    }) as response:
                        payload, status = await response.json(), response.status
                    meta = payload.get("meta_info", {})
                    return {"request_id": row["request_id"], "status": status,
                        "prompt_tokens": row["input_tokens"], "completion_tokens": meta.get("completion_tokens"),
                        "e2e_latency_s": meta.get("e2e_latency"), "ttft_s": meta.get("ttft"),
                        "queue_time_s": meta.get("queue_time"), "cached_tokens": meta.get("cached_tokens"),
                        "cached_tokens_details": meta.get("cached_tokens_details"),
                        "client_latency_s": time.perf_counter() - t0, "error": payload.get("error")}
            return await asyncio.gather(*(request(row) for row in rows))

    def collect():
        while sub in dict(poller.poll(0)):
            parts = sub.recv_multipart()
            if len(parts) != 3:
                continue
            try:
                item = decoder.decode(parts[2])
                events.append({"recv_monotonic_ns": time.monotonic_ns(), "seq": int.from_bytes(parts[1], "big"),
                    "counter_id": item.counter_id, "iteration_id": item.iteration_id,
                    "worker_id": item.worker_id, "gpu_forward_s": item.wall_time,
                    "prefill": {"requests": item.scheduled_requests.num_prefill_requests,
                        "compute_tokens": item.scheduled_requests.sum_prefill_tokens,
                        "prefix_kv_tokens": item.scheduled_requests.sum_prefill_kv_tokens},
                    "decode": {"requests": item.scheduled_requests.num_decode_requests,
                        "kv_tokens": item.scheduled_requests.sum_decode_kv_tokens},
                    "queued": {"prefill_requests": item.queued_requests.num_prefill_requests,
                        "prefill_tokens": item.queued_requests.sum_prefill_tokens,
                        "decode_requests": item.queued_requests.num_decode_requests,
                        "decode_kv_tokens": item.queued_requests.sum_decode_kv_tokens}})
            except Exception as exc:
                errors.append(repr(exc))

    # The NCU launch-and-profile path holds this same exclusive lock in its
    # unprivileged wrapper before sudo execs NCU. In that case, skip acquiring
    # a second flock from the target process (which would self-deadlock).
    lock_inherited = os.environ.get("SGLANG_R17_GPU_LOCK_HELD") == "1" or os.geteuid() == 0
    lock_context = open(os.devnull, "r") if lock_inherited else open(LOCK, "w")
    with lock_context as lock:
        if not lock_inherited:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if requests.get(BASE + "/health", timeout=2).ok:
                raise SystemExit("port 30160 already active")
        except requests.RequestException:
            pass
        active = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        if active:
            raise SystemExit(f"GPU compute process active: {active}")
        if pathlib.Path(sockpath).exists():
            raise SystemExit("FPM IPC collision")
        env = os.environ.copy()
        env.update({"PYTHONPATH": f"/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:{aot_overlay}:{ROOT}/python:{ROOT}/python/sglang/kernels/aot/python",
            "SGLANG_AOT_KERNELS": "1",
            "SGLANG_R17_AOT_OVERLAY": aot_overlay, "SGLANG_ENABLE_NVTX_SCHEDULER": os.environ.get("SGLANG_ENABLE_NVTX_SCHEDULER", "0"), "SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION": "false",
            "SGLANG_PROFILE_V2": "0", "SGLANG_LOG_FORWARD_ITERS": "1",
            "SGLANG_R17_PROFILE_TAG": tag, "PROMETHEUS_MULTIPROC_DIR": str(out / "prometheus"),
            "SGLANG_ENABLE_METRICS_DEVICE_TIMER": "1"})
        if args.cupti_steps:
            if not args.cupti_output:
                raise SystemExit("--cupti-output required with --cupti-steps")
            env["SGLANG_T002_CUPTI"] = "1"
            env["SGLANG_T002_CUPTI_STEPS"] = str(args.cupti_steps)
            env["SGLANG_T002_CUPTI_OUTPUT"] = args.cupti_output
            env["SGLANG_T002_CUPTI_TOKEN"] = os.environ.get(
                "SGLANG_T002_CUPTI_TOKEN", secrets.token_hex(24)
            )

        (out / "prometheus").mkdir()
        launch = [PYTHON, "-u", "-m", "sglang.launch_server", "--model-path", MODEL, "--revision", REV,
            "--served-model-name", "falcon-h1-mainline", "--host", "127.0.0.1", "--port", "30160",
            "--tp-size", "1", "--trust-remote-code", "--mem-fraction-static", "0.90",
            "--max-running-requests", "16", "--context-length", "8192", "--max-mamba-cache-size", "83",
            "--mamba-radix-cache-strategy", "extra_buffer", "--cuda-graph-max-bs-decode", "16",
            "--enable-forward-pass-metrics", "--forward-pass-metrics-worker-id", "falcon-mainline",
            "--forward-pass-metrics-ipc-name", tag_ipc, "--cuda-graph-backend-prefill", "disabled",
            "--cuda-graph-backend-decode", "full", "--enable-metrics", "--export-metrics-to-file",
            "--export-metrics-to-file-dir", str(out / "metrics"), "--log-level", "info"]
        srv = subprocess.Popen(launch, cwd=ROOT, env=env, stdout=open(out / "server.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
        sampler = subprocess.Popen([PYTHON, str(PROV / "gpu_window_sample.py"), "--out", str(out / "gpu-nvml.csv"), "--tag", tag], stdout=open(out / "nvml.stdout", "w"), stderr=open(out / "nvml.stderr", "w"), start_new_session=True)
        try:
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                if srv.poll() is not None:
                    raise RuntimeError(f"server exited rc={srv.returncode}")
                try:
                    if requests.get(BASE + "/health", timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError("health timeout 1200s")
            # Record the actual service process tree and mapped Python/native objects.
            ps_snapshot = subprocess.check_output(["ps", "-eo", "pid,ppid,args"], text=True)
            (out / "processes.txt").write_text(ps_snapshot)
            process_rows = []
            for line in ps_snapshot.splitlines()[1:]:
                fields = line.strip().split(None, 2)
                if len(fields) < 3:
                    continue
                pid, ppid, argv = int(fields[0]), int(fields[1]), fields[2]
                if str(srv.pid) in argv or ppid == srv.pid:
                    process_rows.append((pid, ppid, argv))
            map_records = []
            for pid, ppid, argv in process_rows:
                map_path = pathlib.Path(f"/proc/{pid}/maps")
                if not map_path.exists():
                    continue
                mappings = sorted({line.split()[-1] for line in map_path.read_text(errors="replace").splitlines()
                                   if line.split() and ("sglang" in line.split()[-1] or "sgl_kernel" in line.split()[-1] or "common_ops" in line.split()[-1])
                                   and line.split()[-1].startswith("/")})
                for mapped in mappings:
                    file_path = pathlib.Path(mapped.removesuffix(" (deleted)"))
                    map_records.append({"pid": pid, "ppid": ppid, "argv": argv, "mapped_path": mapped,
                        "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest() if file_path.is_file() else None})
            (out / "service-mapped-files.json").write_text(json.dumps(map_records, indent=2) + "\\n")
            requests.post(BASE + "/flush_cache", timeout=60).raise_for_status()
            if args.cupti_steps:
                control = requests.post(
                    BASE + "/t002/cupti",
                    headers={"x-sglang-t002-token": env["SGLANG_T002_CUPTI_TOKEN"]},
                    json={"action": "start", "steps": args.cupti_steps, "output": args.cupti_output},
                    timeout=60,
                )
                control.raise_for_status()
                (out / "cupti-control-start.json").write_text(control.text + "\\n")
            ready = []
            for _ in range(120):
                ready.append(int(subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], text=True).strip()))
                time.sleep(1)
            (out / "preload-baseline.json").write_text(json.dumps({"samples": len(ready), "util_min": min(ready), "util_max": max(ready)}, indent=2))
            wall0, mono0 = time.time_ns(), time.monotonic_ns()
            start = time.perf_counter()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = loop.create_task(request_batch())
            while not task.done():
                loop.run_until_complete(asyncio.sleep(0))
                if sub in dict(poller.poll(50)):
                    collect()
                if srv.poll() is not None:
                    raise RuntimeError(f"server exited during workload rc={srv.returncode}")
            results = task.result()
            elapsed = time.perf_counter() - start
            wall1, mono1 = time.time_ns(), time.monotonic_ns()
            loop.close()
            until = time.monotonic() + 2
            while time.monotonic() < until:
                if sub in dict(poller.poll(50)):
                    collect()
            (out / "metrics-final.prom").write_text(requests.get(BASE + "/metrics", timeout=30).text)
            prefill_s = sum(e["gpu_forward_s"] for e in events if e["prefill"]["requests"])
            decode_s = sum(e["gpu_forward_s"] for e in events if e["decode"]["requests"])
            output_tokens = sum(r["completion_tokens"] or 0 for r in results)
            summary = {"tag": tag, "completed_128": sum(r["status"] == 200 and r["completion_tokens"] == 128 for r in results),
                "window_s": elapsed, "output_window_tps": output_tokens / elapsed,
                "prefill_tokens": sum(e["prefill"]["compute_tokens"] for e in events), "prefill_event_s": prefill_s,
                "prefill_event_tps": sum(e["prefill"]["compute_tokens"] for e in events) / prefill_s if prefill_s else None,
                "decode_event_s": decode_s, "decode_output_tps": output_tokens / decode_s if decode_s else None,
                "forward_event_sum_s": sum(e["gpu_forward_s"] for e in events),
                "gpu_idle_gap_est_s": max(0, elapsed - sum(e["gpu_forward_s"] for e in events)),
                "scheduler_queue_records": sum(bool(e["queued"]["prefill_requests"] or e["queued"]["decode_requests"]) for e in events),
                "e2e_ttft_available": all(r["ttft_s"] is not None for r in results),
                "mean_api_queue_s": sum(r["queue_time_s"] or 0 for r in results) / len(results),
                "cache_tokens": sum(r["cached_tokens"] or 0 for r in results),
                "wall_start_epoch_ns": wall0, "wall_end_epoch_ns": wall1,
                "monotonic_start_ns": mono0, "monotonic_end_ns": mono1, "collector_errors": errors}
            (out / "summary.json").write_text(json.dumps(summary, indent=2))
            (out / "scheduler-forward-pass.json").write_text(json.dumps({"endpoint": endpoint, "records": events}, indent=2))
            (out / "request-results.json").write_text(json.dumps(results, indent=2))
            print(json.dumps(summary, indent=2), flush=True)
        finally:
            try:
                requests.post(BASE + "/shutdown", timeout=5)
            except Exception:
                pass
            if srv:
                try: os.killpg(srv.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: srv.wait(timeout=120)
                except subprocess.TimeoutExpired: os.killpg(srv.pid, signal.SIGKILL); srv.wait()
            if sampler:
                try: os.killpg(sampler.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: sampler.wait(timeout=10)
                except subprocess.TimeoutExpired: os.killpg(sampler.pid, signal.SIGKILL); sampler.wait()
            sub.close(0)
            ctx.term()
            try: pathlib.Path(sockpath).unlink()
            except FileNotFoundError: pass

if __name__ == "__main__":
    main()
