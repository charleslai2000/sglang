#!/usr/bin/env python3
"""Per-model real-hardware smoke harness for the qwen35 GGUF loader path.

Owner: m3-m4-gpu-smoke-20260916 (test-runner role).  This file lives in the
run directory only; it never writes to the frozen source tree.

It launches the frozen LOCAL-PROD-v1.1 server via the explicit PYTHONPATH
module invocation (NOT launcher/launch.sh), waits for health, applies a
fail-closed KV dtype gate, and executes the four ordered steps.

Run under the canonical GPU lock:
  python server_harness.py m3
"""
from __future__ import annotations

import base64
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
SRC = "/opt/sglang/local-prod-v1.1-candidate/src/python"
GPU = "GPU-2e3ed202-3655-d919-0a64-259209bc6587"
HOST = "127.0.0.1"
PORT = 30164
RUNROOT = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916"

MODELS = {
    "m3": {
        "name": "M3",
        "gguf": "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
        "sha256": "64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810",
        "max_total_tokens": 16384,
        "mem_fraction_static": 0.85,
        "cuda_graph_max_bs_decode": 8,
        "vision": False,
    },
    "m4": {
        "name": "M4",
        "gguf": "/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf",
        "sha256": "5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e",
        "mmproj": "/data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf",
        "max_total_tokens": 8192,
        "mem_fraction_static": 0.85,
        "cuda_graph_max_bs_decode": 8,
        "vision": True,
    },
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)


def http_json(method: str, path: str, payload=None, timeout=600):
    url = f"http://{HOST}:{PORT}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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


def port_free() -> bool:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def nvidia_mem_used_mib():
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=20,
        ).strip()
        used, util = [x.strip() for x in out.split(",")[:2]]
        return int(used), int(util)
    except Exception:  # noqa: BLE001
        return None, None


def build_launch_args(spec):
    return [
        PY,
        "-u",
        "-m",
        "sglang.launch_server",
        "--model-path",
        spec["gguf"],
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--tp-size",
        "1",
        "--mem-fraction-static",
        str(spec["mem_fraction_static"]),
        "--max-total-tokens",
        str(spec["max_total_tokens"]),
        "--kv-cache-dtype",
        "fp8_e4m3",
        "--attention-backend",
        "flashinfer",
        "--linear-attn-prefill-backend",
        "triton",
        "--linear-attn-decode-backend",
        "triton",
        "--mamba-radix-cache-strategy",
        "extra_buffer",
        "--mamba-ssm-dtype",
        "float32",
        "--cuda-graph-backend-decode",
        "full",
        "--cuda-graph-max-bs-decode",
        str(spec["cuda_graph_max_bs_decode"]),
        "--disable-prefill-cuda-graph",
        "--max-running-requests",
        "8",
        "--reasoning-parser",
        "qwen3",
        "--tool-call-parser",
        "qwen3_coder",
        "--enable-metrics",
        "--export-metrics-to-file",
        "--export-metrics-to-file-dir",
        os.path.join(RUNROOT, spec["key"], "metrics"),
    ]


def wait_health(proc, logpath, timeout_s=1200):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if proc.poll() is not None:
            return False, "server process exited rc=%s" % proc.returncode
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


def logprob_values(seq):
    """Extract only the logprob number (entry[0]) from a logprob sequence."""
    out = []
    for e in seq or []:
        if isinstance(e, (list, tuple)) and e and isinstance(e[0], (int, float)):
            out.append(float(e[0]))
        elif isinstance(e, dict) and "logprob" in e:
            out.append(float(e["logprob"]))
    return out


def top_logprob_values(seq):
    """``input_top_logprobs`` is one list-of-entries per position."""
    out = []
    for pos in seq or []:
        out += logprob_values(pos)
    return out


def nonfinite(values):
    return [v for v in values if not math.isfinite(v)]


def step_finite_logits(art):
    """Step 1: finite-logit evidence via full-sequence logprobs.

    The HTTP API does not expose raw logits.  SGLang computes the returned
    token logprobs with log_softmax over the model's logit vector; NaN/Inf in
    logits manifests as non-finite logprobs.  We check only logprob numbers
    (not token ids), for every prompt and decode position of two requests.
    """
    res = {}
    for tag, prompt in (
        ("p1", "The capital of France is"),
        ("p2", "Question: What is 17 times 3?\nAnswer:"),
    ):
        payload = {
            "text": prompt,
            "sampling_params": {"temperature": 0.0, "max_new_tokens": 8},
            "return_logprob": True,
            "logprob_start_len": 0,
            "top_logprobs_num": 5,
        }
        code, body = http_json("POST", "/generate", payload)
        if code != 200:
            res[tag] = {"http": code, "body": body}
            continue
        mi = body.get("meta_info", {})
        in_lp = logprob_values(mi.get("input_token_logprobs"))
        out_lp = logprob_values(mi.get("output_token_logprobs"))
        in_top = top_logprob_values(mi.get("input_top_logprobs"))
        out_top = top_logprob_values(mi.get("output_top_logprobs"))
        vals = in_lp + out_lp + in_top + out_top
        bad = nonfinite(vals)
        res[tag] = {
            "http": code,
            "text": body.get("text"),
            "output_ids": mi.get("output_ids"),
            "output_token_logprobs": mi.get("output_token_logprobs"),
            "meta_info_keys": sorted(mi.keys()),
            "n_input_positions": len(in_lp),
            "n_output_positions": len(out_lp),
            "n_input_top": len(in_top),
            "n_output_top": len(out_top),
            "n_logprob_values_checked": len(vals),
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "n_nonfinite": len(bad),
            "first_nonfinite": bad[:5],
        }
    art["step1_finite_logits"] = res
    return res


def step_semantic(art):
    res = {}
    cases = [
        ("arithmetic", "Question: What is 17 times 3? Answer with only the number.\nAnswer:", ["51"]),
        ("capital", "The capital of France is", ["Paris", "paris"]),
        ("echo", "Repeat this exact phrase: hello world\nPhrase:", ["hello world"]),
    ]
    for tag, prompt, expected in cases:
        payload = {
            "text": prompt,
            "sampling_params": {"temperature": 0.0, "max_new_tokens": 32},
            "return_logprob": True,
        }
        code, body = http_json("POST", "/generate", payload)
        text = body.get("text") if isinstance(body, dict) else body
        mi = body.get("meta_info", {}) if isinstance(body, dict) else {}
        hit = any(e in (text or "") for e in expected)
        res[tag] = {
            "http": code,
            "prompt": prompt,
            "expected": expected,
            "generated": text,
            "output_ids": mi.get("output_ids"),
            "output_token_logprobs": mi.get("output_token_logprobs"),
            "contains_expected": bool(hit),
        }

    # Chat path with the model's own chat template (thinking disabled when the
    # template exposes the toggle).
    chat_cases = [
        ("chat_arithmetic", "What is 17 times 3? Answer with only the number.", ["51"]),
    ]
    for tag, q, expected in chat_cases:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": q}],
            "temperature": 0.0,
            "max_tokens": 64,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        code, body = http_json("POST", "/v1/chat/completions", payload)
        content = None
        reasoning = None
        if isinstance(body, dict):
            try:
                msg = body["choices"][0]["message"]
                content = msg.get("content")
                reasoning = msg.get("reasoning_content")
            except Exception:  # noqa: BLE001
                pass
        res[tag] = {
            "http": code,
            "prompt": q,
            "expected": expected,
            "content": content,
            "reasoning_content": reasoning,
            "raw": body if code != 200 else None,
            "contains_expected": bool(
                content and any(e in content for e in expected)
            ),
        }
    art["step2_semantic"] = res
    return res


def step_tokenizer_crosscheck(art):
    """Decode the server's raw generated token ids with the frozen tokenizer.

    Separates "model emitted incoherent ids" from "server detokenisation
    mismatch": if local decode of the same ids yields coherent text while the
    server text did not, the defect is in detokenisation; if local decode also
    yields the same garbage, the token ids themselves are incoherent.
    """
    out = {}
    try:
        from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_tokenizer

        tok = build_gguf_tokenizer(MODELS[art["model_key"]]["gguf"])
        out["tokenizer_vocab_size"] = getattr(tok, "vocab_size", None)
    except Exception as e:  # noqa: BLE001
        art["step2b_tokenizer_crosscheck"] = {"error": f"{type(e).__name__}: {e}"}
        return art["step2b_tokenizer_crosscheck"]

    samples = {}
    for tag, rec in art.get("step1_finite_logits", {}).items():
        otl = rec.get("output_token_logprobs")
        if not otl:
            continue
        ids = [int(e[1]) for e in otl if isinstance(e, (list, tuple)) and len(e) > 1]
        samples[tag] = {
            "ids": ids,
            "server_text": rec.get("text"),
            "local_decode": tok.decode(ids, skip_special_tokens=False),
            "local_decode_skip_special": tok.decode(ids, skip_special_tokens=True),
            "ids_max": max(ids) if ids else None,
            "n_ids_ge_vocab": sum(1 for i in ids if i >= (tok.vocab_size or 0)),
        }
    for tag, rec in art.get("step2_semantic", {}).items():
        otl = rec.get("output_token_logprobs")
        if not otl:
            continue
        ids = [int(e[1]) for e in otl if isinstance(e, (list, tuple)) and len(e) > 1]
        samples[tag] = {
            "ids": ids,
            "server_text": rec.get("generated") or rec.get("content"),
            "local_decode": tok.decode(ids, skip_special_tokens=False),
            "local_decode_skip_special": tok.decode(ids, skip_special_tokens=True),
            "ids_max": max(ids) if ids else None,
            "n_ids_ge_vocab": sum(1 for i in ids if i >= (tok.vocab_size or 0)),
        }
    out["samples"] = samples
    art["step2b_tokenizer_crosscheck"] = out
    return out


def _png_data_uri(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def step_vision(art):
    """Step 2 (M4): vision E2E with known-answer images."""
    res = {"mmproj_present": os.path.exists(MODELS["m4"]["mmproj"])}
    try:
        from PIL import Image, ImageDraw
    except Exception as e:  # noqa: BLE001
        res["error"] = f"PIL unavailable: {e}"
        art["step2_vision"] = res
        return res

    green = Image.new("RGB", (96, 96), (0, 200, 0))
    shape = Image.new("RGB", (96, 96), (255, 255, 255))
    d = ImageDraw.Draw(shape)
    d.ellipse((16, 16, 80, 80), fill=(0, 0, 0))

    cases = [
        ("color", green, "What is the dominant colour of this image? Answer with one word.", ["green"]),
        ("shape", shape, "What shape is shown in this image? Answer with one word.", ["circle"]),
    ]
    for tag, img, q, expected in cases:
        uri = _png_data_uri(img)
        payload = {
            "model": "default",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": q},
                        {"type": "image_url", "image_url": {"url": uri}},
                    ],
                }
            ],
            "max_tokens": 24,
            "temperature": 0.0,
        }
        code, body = http_json("POST", "/v1/chat/completions", payload)
        content = None
        if isinstance(body, dict):
            try:
                content = body["choices"][0]["message"].get("content")
            except Exception:  # noqa: BLE001
                content = None
        res[tag] = {
            "http": code,
            "expected": expected,
            "answer": content,
            "raw": body if code != 200 else None,
            "contains_expected": bool(
                content and any(e.lower() in content.lower() for e in expected)
            ),
        }
    art["step2_vision"] = res
    return res


def step_kernel_server_signals(art, logtext):
    """Step 3 server-side signals: quant method, warnings, absence of fallback."""
    pats = {
        "gguf_mentions": r"(?i)gguf",
        "quant_mentions": r"(?i)quant(ization)?[=: _-]",
        "dequant_mentions": r"(?i)dequant",
        "kernel_mentions": r"(?i)ggml|mul_mat|sgl_kernel",
        "fallback_warnings": r"(?i)falling back|fallback|not support",
        "not_implemented": r"(?i)NotImplementedError|unsupported GGUF quantization",
    }
    out = {}
    for k, p in pats.items():
        hits = [ln for ln in logtext.splitlines() if re.search(p, ln)]
        out[k] = {"count": len(hits), "sample": hits[:10]}
    art["step3_server_signals"] = out
    return out


def step_graph_and_device(art, logtext):
    lines = logtext.splitlines()
    graph_lines = [ln for ln in lines if re.search(r"(?i)cuda graph|graph capture|capture cuda", ln)]
    graph_err = [
        ln
        for ln in lines
        if re.search(r"(?i)cuda graph|graph capture|capture cuda", ln)
        and re.search(r"(?i)error|fail|exception|traceback|abort", ln)
    ]
    kv = [ln for ln in lines if "KV Cache is allocated" in ln]
    mempool = [ln for ln in lines if re.search(r"(?i)memory pool|load weight end|model runner mem", ln)]
    used, util = nvidia_mem_used_mib()
    art["step4_graph_device"] = {
        "graph_log_lines": graph_lines[:60],
        "graph_log_line_count": len(graph_lines),
        "graph_error_lines": graph_err,
        "kv_alloc_lines": kv,
        "device_mem_lines": mempool[:20],
        "nvidia_smi_used_mib": used,
        "nvidia_smi_util_pct": util,
    }
    return art["step4_graph_device"]


def kv_gate(logtext):
    m = re.search(r"KV Cache is allocated\. dtype: ([^,]+), #tokens: (\d+)", logtext)
    if not m:
        return {"ok": False, "reason": "KV Cache allocation line not found"}
    dtype, tokens = m.group(1), int(m.group(2))
    ok = dtype.strip() == "torch.float8_e4m3fn"
    return {"ok": ok, "dtype": dtype.strip(), "tokens": tokens}


def main():
    key = sys.argv[1]
    spec = MODELS[key]
    spec["key"] = key
    outdir = os.path.join(RUNROOT, key)
    logpath = os.path.join(outdir, "server.log")
    art = {
        "model_key": key,
        "model_name": spec["name"],
        "gguf": spec["gguf"],
        "expected_sha256": spec["sha256"],
        "started_utc": now(),
        "source": "/opt/sglang/local-prod-v1.1-candidate/src",
        "pythonpath": SRC,
        "launcher_used": False,
        "launch_mode": "explicit PYTHONPATH + python -m sglang.launch_server",
        "cuda_visible_devices": GPU,
        "port": PORT,
        "mtp": "off",
    }

    if not port_free():
        art["status"] = "blocked_port_busy"
        write_art(outdir, art)
        return

    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = GPU
    env["CUDA_HOME"] = "/usr/local/cuda-12.9"
    env["PATH"] = "/usr/local/cuda-12.9/bin:" + env.get("PATH", "")
    for k in ("SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR",):
        env.pop(k, None)

    args = build_launch_args(spec)
    art["launch_argv"] = args
    with open(os.path.join(outdir, "launch_argv.txt"), "w") as f:
        f.write(" ".join(args) + "\n")
    with open(os.path.join(outdir, "launch_env.txt"), "w") as f:
        for k in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "CUDA_VISIBLE_DEVICES", "CUDA_HOME"):
            f.write(f"{k}={env.get(k)}\n")

    logf = open(logpath, "wb")
    t0 = time.time()
    proc = subprocess.Popen(
        args,
        env=env,
        cwd="/tmp",
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    art["server_pid"] = proc.pid
    log(f"{key}: server launched pid={proc.pid}, waiting for health")

    ok, why = wait_health(proc, logpath)
    art["startup_s"] = round(time.time() - t0, 2)
    used0, util0 = nvidia_mem_used_mib()
    art["vram_after_load_mib"] = used0
    if not ok:
        logf.flush()
        logtext = open(logpath, errors="replace").read()
        art["status"] = "server_failed"
        art["health_error"] = why
        art["server_tail"] = logtext[-4000:]
        terminate(proc)
        logf.close()
        write_art(outdir, art)
        log(f"{key}: SERVER FAILED: {why}")
        return

    log(f"{key}: healthy in {art['startup_s']}s, vram={used0} MiB")
    time.sleep(3)
    logf.flush()
    logtext = open(logpath, errors="replace").read()
    gate = kv_gate(logtext)
    art["kv_gate"] = gate
    if not gate.get("ok"):
        art["status"] = "kv_gate_failed"
        log(f"{key}: KV GATE FAILED: {gate}")
        terminate(proc)
        logf.close()
        write_art(outdir, art)
        return
    log(f"{key}: KV gate OK ({gate['dtype']}, tokens={gate['tokens']})")

    try:
        code, info = http_json("GET", "/get_server_info", timeout=30)
        art["server_info"] = info if code == 200 else {"http": code}
    except Exception as e:  # noqa: BLE001
        art["server_info"] = {"error": str(e)}

    try:
        step_finite_logits(art)
        step_semantic(art)
        step_tokenizer_crosscheck(art)
        if spec["vision"]:
            step_vision(art)
        # exercise decode at more than one graph batch size
        for bs in (2, 4):
            import threading

            results = []

            def one(i):
                results.append(
                    http_json(
                        "POST",
                        "/generate",
                        {
                            "text": f"Count: {i}. Say OK.",
                            "sampling_params": {"temperature": 0.0, "max_new_tokens": 4},
                        },
                    )[0]
                )

            ths = [threading.Thread(target=one, args=(i,)) for i in range(bs)]
            [t.start() for t in ths]
            [t.join() for t in ths]
            art.setdefault("decode_batch_probe", {})[f"bs{bs}"] = results
    except Exception as e:  # noqa: BLE001
        art["step_exception"] = traceback.format_exc()

    time.sleep(3)
    used1, util1 = nvidia_mem_used_mib()
    art["vram_after_steps_mib"] = used1
    logf.flush()
    logtext = open(logpath, errors="replace").read()
    step_kernel_server_signals(art, logtext)
    step_graph_and_device(art, logtext)

    art["status"] = "completed"
    art["finished_utc"] = now()
    terminate(proc)
    logf.close()
    write_art(outdir, art)
    log(f"{key}: harness completed, vram={used1} MiB")


def write_art(outdir, art):
    with open(os.path.join(outdir, "report.json"), "w") as f:
        json.dump(art, f, indent=2)
    log(f"wrote {os.path.join(outdir, 'report.json')}")


if __name__ == "__main__":
    main()
