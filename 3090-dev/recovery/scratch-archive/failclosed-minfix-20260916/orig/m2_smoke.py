#!/usr/bin/env python3
"""M2 (OmniCoder-9B GPTQ-INT4) real-hardware bring-up smoke on LOCAL-PROD-v1.1.

Task: m2-bringup-smoke-20260916 (test-runner / execution only).

Executes the six task-prescribed validation steps against the frozen
LOCAL-PROD-v1.1 source tree via explicit PYTHONPATH + `-m sglang.launch_server`
(NOT launcher/launch.sh, which is pinned to M1).  Launch arguments mirror M1's
proven fp8 arm from m1-v11-fp8-anchor-20260916/anchor-summary.json, with the
model path swapped to the M2 GPTQ artifact.  MTP is not enabled.

It acquires and holds the canonical GPU flock (/tmp/opencode/gpu-3090.lock)
for the whole server lifetime.  No product source is modified; only normal
server logs, the public HTTP API and nvidia-smi are used.
"""
from __future__ import annotations

import base64
import fcntl
import io
import json
import math
import os
import re
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone

PY = "/opt/sglang/local-prod-v1/env/bin/python"
SRC = "/opt/sglang/local-prod-v1.1-candidate/src"
PYTHONPATH = SRC + "/python"
GPU = "GPU-2e3ed202-3655-d919-0a64-259209bc6587"
HOST = "127.0.0.1"
PORT = 30164
RUN_DIR = "/var/log/sglang/local-prod-v1/phase8/m2-bringup-smoke-20260916"
MODEL_DIR = "/data/models/omnicoder-9b-gptq-int4"
MODEL_FILE = MODEL_DIR + "/model.safetensors"
EXPECTED_SHA = "06d1bcfce288de3088aa0637c0b63e041d83f7079e89f373396d139d6b00e6da"
LOCK = "/tmp/opencode/gpu-3090.lock"
OWNER = "m2-bringup-smoke-20260916"
LOCK_WAIT_S = 45 * 60
POLL_S = 60

# M1's proven launch arg set (m1-v11-fp8-anchor-20260916/anchor-summary.json),
# model path replaced with the M2 artifact.  MTP/speculative args absent.
LAUNCH_ARGS = [
    PY, "-u", "-m", "sglang.launch_server",
    "--model-path", MODEL_DIR,
    "--host", HOST, "--port", str(PORT),
    "--tp-size", "1",
    "--mem-fraction-static", "0.92",
    "--max-total-tokens", "65536",
    "--kv-cache-dtype", "fp8_e4m3",
    "--attention-backend", "flashinfer",
    "--linear-attn-prefill-backend", "triton",
    "--linear-attn-decode-backend", "triton",
    "--mamba-radix-cache-strategy", "extra_buffer",
    "--mamba-ssm-dtype", "float32",
    "--cuda-graph-backend-decode", "full",
    "--disable-prefill-cuda-graph",
    "--max-running-requests", "21",
    "--reasoning-parser", "qwen3",
    "--tool-call-parser", "qwen3_coder",
    "--enable-metrics",
    "--export-metrics-to-file",
    "--export-metrics-to-file-dir", RUN_DIR + "/metrics",
]

REPORT = os.path.join(RUN_DIR, "report.json")
DRIVER_LOG = os.path.join(RUN_DIR, "driver.log")
_logf = None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    global _logf
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    if _logf is not None:
        _logf.write(line + "\n")
        _logf.flush()
        os.fsync(_logf.fileno())


def write_report(art: dict) -> None:
    art["updated_utc"] = now()
    tmp = REPORT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(art, f, indent=2)
    os.replace(tmp, REPORT)


def http_json(method, path, payload=None, timeout=600):
    url = f"http://{HOST}:{PORT}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def http_stream(path, payload, timeout=600):
    """Streaming POST; returns (status, ttft_s, t_last_s, n_chunks, text, meta, raw_last)."""
    url = f"http://{HOST}:{PORT}{path}"
    payload = dict(payload)
    payload["stream"] = True
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    ttft = None
    t_last = None
    n = 0
    parts = []
    meta = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                txt = obj.get("text", "")
                if txt:
                    n += 1
                    parts.append(txt)
                    if ttft is None:
                        ttft = time.time() - t0
                    t_last = time.time() - t0
                if obj.get("meta_info"):
                    meta = obj["meta_info"]
        return 200, ttft, t_last, n, "".join(parts), meta, None
    except urllib.error.HTTPError as e:
        return e.code, ttft, t_last, n, "".join(parts), meta, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return None, ttft, t_last, n, "".join(parts), meta, f"{type(e).__name__}: {e}"


def port_free() -> bool:
    s = socket.socket()
    try:
        s.bind((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def nvsmi():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"], text=True, timeout=20).strip()
        used, total, util = [x.strip() for x in out.split(",")[:3]]
        return int(used), int(total), int(util)
    except Exception:  # noqa: BLE001
        return None, None, None


def finite_values(x):
    out = []
    if isinstance(x, bool):
        return out
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, list):
        for v in x:
            out += finite_values(v)
    elif isinstance(x, dict):
        for v in x.values():
            out += finite_values(v)
    return out


def acquire_lock(art):
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o664)
    deadline = time.time() + LOCK_WAIT_S
    attempt = 0
    while True:
        attempt += 1
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            art["lock"] = {"acquired_utc": now(), "attempts": attempt,
                           "path": LOCK, "waited_s": round(time.time() - (deadline - LOCK_WAIT_S), 1)}
            try:
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, json.dumps({
                    "owner": OWNER, "pid": os.getpid(),
                    "acquired": now()}).encode())
            except Exception as e:  # noqa: BLE001
                log(f"WARN could not write canonical lock owner record: {e}")
            log(f"canonical lock acquired on attempt {attempt}")
            write_report(art)
            return fd
        except OSError:
            if time.time() >= deadline:
                art["lock"] = {"acquired_utc": None, "attempts": attempt,
                               "path": LOCK, "blocked": "lock busy or invalid"}
                log(f"BLOCKED: canonical lock not acquired after {LOCK_WAIT_S}s")
                write_report(art)
                return None
            log(f"canonical lock busy (attempt {attempt}); sleeping {POLL_S}s")
            time.sleep(POLL_S)


def wait_health(proc, timeout_s=1200):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if proc.poll() is not None:
            return False, f"server process exited rc={proc.returncode}"
        try:
            code, _ = http_json("GET", "/health", timeout=5)
            if code == 200:
                return True, None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
    return False, f"health timeout after {timeout_s}s"


def terminate(proc, grace=60):
    if proc.poll() is not None:
        return proc.returncode
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return proc.poll()
    t0 = time.time()
    while time.time() - t0 < grace:
        if proc.poll() is not None:
            return proc.returncode
        time.sleep(1)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=30)
    return proc.returncode


def readlog(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def kv_gate(logtext):
    m = re.search(r"KV Cache is allocated\. dtype: ([^,]+), #tokens: (\d+)", logtext)
    if not m:
        return {"ok": False, "reason": "KV Cache allocation line not found"}
    dtype = m.group(1).strip()
    return {"ok": dtype == "torch.float8_e4m3fn", "dtype": dtype,
            "tokens": int(m.group(2)), "line": m.group(0)}


def step1_kv_gate(art, logtext):
    g = kv_gate(logtext)
    # fail-closed gate uses the tuple comparison requested by the task
    g["requested"] = "fp8_e4m3"
    g["requested_torch_dtype"] = "torch.float8_e4m3fn"
    art["step1_kv_gate"] = g
    return g


def step2_finite_logits(art):
    res = {}
    for tag, prompt in (("p1", "The capital of France is"),
                        ("p2", "Question: What is 17 times 3?\nAnswer:")):
        payload = {"text": prompt,
                   "sampling_params": {"temperature": 0.0, "max_new_tokens": 8},
                   "return_logprob": True, "logprob_start_len": 0,
                   "top_logprobs_num": 5}
        code, body = http_json("POST", "/generate", payload)
        if code != 200 or not isinstance(body, dict):
            res[tag] = {"http": code, "body": body}
            continue
        mi = body.get("meta_info", {})
        vals = finite_values([mi.get("input_token_logprobs"),
                              mi.get("output_token_logprobs"),
                              mi.get("input_top_logprobs"),
                              mi.get("output_top_logprobs")])
        bad = [v for v in vals if not math.isfinite(v)]
        res[tag] = {"http": code, "text": body.get("text"),
                    "n_values_checked": len(vals),
                    "n_nonfinite": len(bad), "first_nonfinite": bad[:5],
                    "min": min(vals) if vals else None,
                    "max": max(vals) if vals else None}
    res["note"] = ("HTTP API does not expose raw logits; returned token logprobs are "
                   "log_softmax over the logit vector, so non-finite logits would "
                   "manifest as non-finite logprobs.")
    art["step2_finite_logits"] = res
    return res


def step3_semantic(art):
    res = {}
    for tag, prompt, expected in (
            ("arithmetic", "Question: What is 17 times 3? Answer with only the number.\nAnswer:", ["51"]),
            ("capital", "The capital of France is", ["Paris", "paris"])):
        code, body = http_json("POST", "/generate",
                               {"text": prompt,
                                "sampling_params": {"temperature": 0.0, "max_new_tokens": 32}})
        text = body.get("text") if isinstance(body, dict) else body
        res[tag] = {"http": code, "prompt": prompt, "expected": expected,
                    "generated": text,
                    "contains_expected": bool(text and any(e in text for e in expected))}
    art["step3_semantic"] = res
    return res


def step3b_vision(art):
    res = {"model_multimodal": True,
           "evidence": "config.json has vision_config + image_token_id=248056; "
                       "architectures=[Qwen3_5ForConditionalGeneration] "
                       "(subclass of Qwen3VLForConditionalGeneration)"}
    try:
        from PIL import Image, ImageDraw
    except Exception as e:  # noqa: BLE001
        res["error"] = f"PIL unavailable: {e}"
        art["step3b_vision"] = res
        return res

    def uri(img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    green = Image.new("RGB", (96, 96), (0, 200, 0))
    shape = Image.new("RGB", (96, 96), (255, 255, 255))
    ImageDraw.Draw(shape).ellipse((16, 16, 80, 80), fill=(0, 0, 0))

    for tag, img, q, expected in (
            ("color", green, "What is the dominant colour of this image? Answer with one word.", ["green"]),
            ("shape", shape, "What shape is shown in this image? Answer with one word.", ["circle"])):
        code, body = http_json("POST", "/v1/chat/completions",
                               {"model": "default",
                                "messages": [{"role": "user", "content": [
                                    {"type": "text", "text": q},
                                    {"type": "image_url", "image_url": {"url": uri(img)}}]}],
                                "max_tokens": 24, "temperature": 0.0})
        content = None
        if isinstance(body, dict):
            try:
                content = body["choices"][0]["message"].get("content")
            except Exception:  # noqa: BLE001
                content = None
        res[tag] = {"http": code, "expected": expected, "answer": content,
                    "raw": body if code != 200 else None,
                    "contains_expected": bool(content and any(
                        e.lower() in content.lower() for e in expected))}
    art["step3b_vision"] = res
    return res


def step4_quant_dispatch(art, logtext):
    lines = logtext.splitlines()
    pats = {
        "using_kernel": r"Using .* kernel\.",
        "gptq_marlin": r"gptq_marlin",
        "marlin": r"(?i)marlin",
        "gptq_convert": r"(?i)convertible to .* during runtime",
        "unquantized_fallback": r"UnquantizedLinearMethod",
        "fallback_generic": r"(?i)falling back|fall back",
        "not_supported": r"(?i)not support|unsupported|NotImplementedError",
        "gptq_gemm": r"gptq_gemm|gptq_marlin_gemm|marlin_gemm",
    }
    out = {}
    for k, p in pats.items():
        hits = [ln for ln in lines if re.search(p, ln)]
        out[k] = {"count": len(hits), "lines": hits[:12]}
    art["step4_quant_dispatch"] = out
    return out


def step5_cuda_graph(art, logtext):
    lines = logtext.splitlines()
    begin = [ln for ln in lines if "Capture target decode CUDA graph begin" in ln]
    end = [ln for ln in lines if "Capture target decode CUDA graph end" in ln]
    prefill_disabled = [ln for ln in lines if "Disable prefill CUDA graph" in ln]
    grapherr = [ln for ln in lines if re.search(r"(?i)cuda graph", ln)
                and re.search(r"(?i)error|fail|exception|traceback|abort", ln)]
    dec_true = sum(1 for ln in lines if "cuda graph: True" in ln)
    dec_false = sum(1 for ln in lines if "cuda graph: False" in ln)
    art["step5_cuda_graph"] = {
        "capture_begin_lines": begin,
        "capture_end_lines": end,
        "prefill_graph_disabled_lines": prefill_disabled,
        "graph_error_lines": grapherr,
        "decode_log_lines_cuda_graph_true": dec_true,
        "decode_log_lines_cuda_graph_false": dec_false,
    }
    return art["step5_cuda_graph"]


def build_prefix(n_chars=10500):
    base = ("The quick brown fox jumps over the lazy dog while the diligent "
            "engineer reviews the scheduler logs and checks the cache state. ")
    return (base * (n_chars // len(base) + 1))[:n_chars] + "\nSummarize the above in one short sentence:"


def step6_short_gen(art):
    before = nvsmi()
    prompt = build_prefix()
    code, ttft, t_last, n, text, meta, err = http_stream(
        "/generate",
        {"text": prompt,
         "sampling_params": {"temperature": 0.0, "max_new_tokens": 256}})
    after = nvsmi()
    prompt_tokens = None
    completion_tokens = None
    if isinstance(meta, dict):
        prompt_tokens = meta.get("prompt_tokens")
        completion_tokens = meta.get("completion_tokens")
    decode_tps = None
    if ttft is not None and t_last is not None and n > 1 and t_last > ttft:
        decode_tps = (n - 1) / (t_last - ttft)
    art["step6_short_gen"] = {
        "http": code, "error": err,
        "prompt_tokens_reported": prompt_tokens,
        "completion_tokens_reported": completion_tokens,
        "stream_chunks": n,
        "ttft_s": ttft, "t_last_s": t_last,
        "achieved_decode_tps": decode_tps,
        "vram_used_mib_before": before[0], "vram_total_mib": before[1],
        "vram_used_mib_after": after[0],
        "generated_head": (text or "")[:200],
    }
    return art["step6_short_gen"]


def main() -> int:
    global _logf
    os.makedirs(RUN_DIR, exist_ok=True)
    _logf = open(DRIVER_LOG, "a")
    art = {
        "owner": OWNER, "task": "m2-bringup-smoke-20260916",
        "model_dir": MODEL_DIR, "model_file": MODEL_FILE,
        "expected_sha256": EXPECTED_SHA,
        "source": SRC, "pythonpath": PYTHONPATH,
        "python": PY, "gpu_uuid": GPU, "port": PORT,
        "launcher_used": False,
        "launch_mode": "explicit PYTHONPATH + python -m sglang.launch_server",
        "mtp": "off", "started_utc": now(),
    }

    # preflight: exactly one safetensors in the model root before launching
    sts = sorted(f for f in os.listdir(MODEL_DIR) if f.endswith(".safetensors"))
    art["preflight_safetensors"] = sts
    art["preflight_safetensors_count"] = len(sts)
    if len(sts) != 1 or sts[0] != "model.safetensors":
        art["status"] = "blocked_safetensors_preflight"
        log(f"BLOCKED: expected exactly one model.safetensors, found {sts}")
        write_report(art)
        return 2
    sz = os.path.getsize(MODEL_FILE)
    art["model_size_bytes"] = sz
    if sz != 11668993760:
        art["status"] = "blocked_model_size"
        log(f"BLOCKED: unexpected model size {sz}")
        write_report(art)
        return 2
    log(f"preflight OK: one safetensors, size={sz}")

    # acquire canonical GPU lock (bounded backoff)
    lock_fd = acquire_lock(art)
    if lock_fd is None:
        art["status"] = "blocked_gpu_lock"
        return 3

    try:
        # wait for port to free after lock acquisition
        t0 = time.time()
        while not port_free() and time.time() - t0 < 120:
            log("port 30164 not free yet; waiting 10s")
            time.sleep(10)
        art["port_free_before_launch"] = port_free()
        if not art["port_free_before_launch"]:
            art["status"] = "blocked_port_busy"
            log("BLOCKED: port 30164 busy after lock acquired")
            write_report(art)
            return 4

        env = dict(os.environ)
        env["PYTHONPATH"] = PYTHONPATH
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = GPU
        env["CUDA_HOME"] = "/usr/local/cuda-12.9"
        env["PATH"] = "/usr/local/cuda-12.9/bin:" + env.get("PATH", "")
        env.pop("SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR", None)

        art["launch_argv"] = LAUNCH_ARGS
        with open(os.path.join(RUN_DIR, "launch_argv.txt"), "w") as f:
            f.write(" ".join(LAUNCH_ARGS) + "\n")
        with open(os.path.join(RUN_DIR, "launch_env.txt"), "w") as f:
            for k in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
                      "CUDA_VISIBLE_DEVICES", "CUDA_HOME"):
                f.write(f"{k}={env.get(k)}\n")

        server_log = os.path.join(RUN_DIR, "server.log")
        logf = open(server_log, "wb")
        t_launch = time.time()
        proc = subprocess.Popen(LAUNCH_ARGS, env=env, cwd="/tmp", stdout=logf,
                                stderr=subprocess.STDOUT, start_new_session=True)
        art["server_pid"] = proc.pid
        log(f"server launched pid={proc.pid}; waiting for health")
        write_report(art)

        ok, why = wait_health(proc)
        art["startup_s"] = round(time.time() - t_launch, 2)
        used0 = nvsmi()[0]
        art["vram_after_load_mib"] = used0
        if not ok:
            logf.flush()
            lt = readlog(server_log)
            art["status"] = "server_failed"
            art["health_error"] = why
            art["server_tail"] = lt[-6000:]
            terminate(proc)
            logf.close()
            art["server_returncode"] = proc.returncode
            write_report(art)
            log(f"SERVER FAILED: {why}")
            return 5
        log(f"healthy in {art['startup_s']}s; vram={used0} MiB")

        # confirm the server actually imported the frozen v1.1 source
        try:
            with open(f"/proc/{proc.pid}/environ", "rb") as f:
                envblob = f.read().decode(errors="replace")
            pp = [x for x in envblob.split("\0") if x.startswith("PYTHONPATH=")]
            art["proc_environ_pythonpath"] = pp
        except Exception as e:  # noqa: BLE001
            art["proc_environ_pythonpath"] = f"unreadable: {e}"

        time.sleep(3)
        logf.flush()
        lt = readlog(server_log)
        gate = step1_kv_gate(art, lt)
        write_report(art)
        if not gate.get("ok"):
            art["status"] = "kv_gate_failed"
            log(f"KV GATE FAILED: {gate}")
            terminate(proc)
            logf.close()
            art["server_returncode"] = proc.returncode
            write_report(art)
            return 6
        log(f"KV gate OK: {gate['dtype']} tokens={gate['tokens']}")

        code, info = http_json("GET", "/get_server_info", timeout=30)
        art["server_info_http"] = code
        if code == 200 and isinstance(info, dict):
            keep = {k: info.get(k) for k in (
                "model_path", "served_model_name", "quantization", "model_type",
                "kv_cache_dtype", "enable_multimodal", "is_multimodal",
                "context_length", "max_total_tokens") if k in info}
            art["server_info_subset"] = keep

        try:
            step2_finite_logits(art)
            write_report(art)
            step3_semantic(art)
            write_report(art)
            step3b_vision(art)
            write_report(art)
            step6_short_gen(art)
            write_report(art)
        except Exception:  # noqa: BLE001
            art["step_exception"] = traceback.format_exc()
            write_report(art)

        time.sleep(2)
        logf.flush()
        lt = readlog(server_log)
        step4_quant_dispatch(art, lt)
        step5_cuda_graph(art, lt)
        art["vram_after_steps_mib"] = nvsmi()[0]

        art["status"] = "completed"
        write_report(art)
        terminate(proc)
        logf.close()
        art["server_returncode"] = proc.returncode
        write_report(art)
        log("smoke completed")
        return 0
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            log("canonical lock released")
        except Exception:  # noqa: BLE001
            pass
        if _logf:
            _logf.close()


if __name__ == "__main__":
    sys.exit(main())
