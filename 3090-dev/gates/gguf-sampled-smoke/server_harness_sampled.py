#!/usr/bin/env python3
"""Per-model real-hardware smoke harness for the qwen35 GGUF loader path.

Origin: byte-identical copy of the audited prior gate harness
  /var/log/sglang/local-prod-v1/phase8/m3-m4-normfix-gate-20260916/
  server_harness_normfix.py
whose ``_ngram_analysis`` loop metric and launch-arg spec are preserved
VERBATIM so results stay numerically comparable to the prior evidence.

Delta introduced by this gate (owner re-scope 2026-09-17):
  * the >=512-token long-form GATING arm is the SAMPLED contract carried in the
    GGUF ``general.sampling.*`` metadata (temp=1.0, top_p=0.95, top_k=20,
    min_p=0.0; M4 additionally repetition_penalty=1.0), NOT greedy;
  * greedy and thinking-ON are DEMOTED to non-gating diagnostic arms;
  * the gate threshold is ``content_loop_w4 <= 0.27`` (owner COHERENT bound)
    instead of the old < 0.5, and content-empty-all-reasoning is a failure;
  * the source tree is PARAMETERIZED (no hardcoded pre-fix module hash): the
    preflight verifies identity by (a) sglang resolving into the configured
    tree, (b) the inverse-fold helpers being present in the module, and
    (c) a recorded content hash of the module for the run report.

It launches the candidate server via the explicit PYTHONPATH module invocation
(NOT launcher/launch.sh), waits for health, applies a fail-closed KV dtype gate,
and executes the ordered steps.  It never writes to the source tree.

Run under the canonical GPU lock:
  python server_harness_sampled.py m4     # owner order: M4 first
  python server_harness_sampled.py m3     # then M3

Offline (no GPU, no server) contract smoke:
  python server_harness_sampled.py --cpu-smoke
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
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
from collections import Counter
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Parameterized environment (owner rule: never hardcode a pre-fix source hash;
# the validated norm-fold fix is committed to the authoritative branch, so the
# gate verifies source IDENTITY STRUCTURALLY and RECORDS the content hash).
# ---------------------------------------------------------------------------
PY = os.environ.get("GGUF_GATE_PY", "/opt/sglang/local-prod-v1/env/bin/python")
# Source tree under test.  Default = the authoritative repo working tree
# (the fixed norm-inverse-fold commit is in it by the time this runs).
SRC = os.environ.get(
    "GGUF_GATE_SRC",
    "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python",
)
GPU = "GPU-2e3ed202-3655-d919-0a64-259209bc6587"
HOST = "127.0.0.1"
# 301xx are experiment ports.  30164 was the prior gate; 30165 is this gate's.
PORT = int(os.environ.get("GGUF_GATE_PORT", "30165"))
RUNROOT = os.environ.get(
    "GGUF_GATE_RUNROOT",
    "/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs",
)
LOCK_PATH = "/tmp/opencode/gpu-3090.lock"
OWNER = "gguf-sampled-smoke-gate-20260917"
LOCK_WAIT_S = 45 * 60
POLL_S = 60
PATCHED_MODULE = SRC + "/sglang/srt/models/qwen3_5_text.py"
# Optional expected module sha256.  Empty => structural identity check only
# (helpers present + module resolves inside SRC) and the observed hash is
# recorded.  Set GGUF_GATE_MODULE_SHA256 to pin an exact reviewed revision.
PATCHED_FILE_SHA256 = os.environ.get("GGUF_GATE_MODULE_SHA256", "")
# Structural marker proving the committed norm inverse-fold is what we run.
FOLD_HELPERS = ("_gguf_fold_absolute_norms", "_gemma_norm_param_names")

MODELS = {
    "m3": {
        "name": "M3",
        "gguf": "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
        "sha256": "64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810",
        "max_total_tokens": 16384,
        "mem_fraction_static": 0.85,
        "cuda_graph_max_bs_decode": 8,
        "vision": False,
        # GGUF-native sampling contract (metadata general.sampling.*), used by
        # the GATING sampled arm.  repetition_penalty is the sglang name for
        # GGUF's penalty_repeat.
        "sampling_contract": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": None,
        },
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
        "sampling_contract": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
        },
    },
}

# Binding owner ruling 2026-09-16: this bake-off is text-only.  No mmproj /
# LOCAL-PROD-v1.1 vision support is added, M4 vision is NOT scored, and vision
# must never contribute to the verdict nor be recorded as a pass.
VISION_SCOPE = "text_only_unscored"
VISION_RULING = "GGUF candidates evaluated as text-only; multimodal capability unscored."

# Required probe tags: a result lacking any of these is "not executed".
FINITE_LOGIT_TAGS = ("p1", "p2")
# Required probe tags: a result lacking any of these is "not executed".
# The chat_* tags are the owner-valid path; the raw /generate tags are the
# known prompt-format-misuse control (recorded, execution-only).
SEMANTIC_TAGS = (
    "arithmetic",
    "capital",
    "echo",
    "chat_arithmetic",
    "chat_capital",
    "chat_code",
    "chat_tool",
)

# The chat-path probes that actually gate short-form correctness.  The raw
# /generate tags above are recorded diagnostics only (owner ruling: raw text
# completion on an instruction-tuned chat model is prompt-format misuse).
GATING_SEMANTIC_TAGS = (
    "chat_arithmetic",
    "chat_capital",
    "chat_code",
    "chat_tool",
)

# Deterministic short-form contract for the semantic/code/tool probes.
SEMANTIC_CONTRACT = {
    "temperature": 0.0,
    "top_p": 1.0,
    "top_k": -1,
    "min_p": 0.0,
    "seed": 20260916,
    "chat_template_kwargs": {"enable_thinking": False},
}

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"],
            },
        },
    }
]


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


def acquire_lock(art):
    """Canonical GPU lock: 60 s poll x 45 min backoff; never race an incumbent."""
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o664)
    deadline = time.time() + LOCK_WAIT_S
    attempt = 0
    while True:
        attempt += 1
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            art["lock"] = {"acquired_utc": now(), "attempts": attempt, "path": LOCK_PATH}
            try:
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(
                    fd,
                    json.dumps(
                        {"owner": OWNER, "pid": os.getpid(), "acquired": now()}
                    ).encode(),
                )
            except Exception as e:  # noqa: BLE001
                log(f"WARN could not write lock owner record: {e}")
            log(f"canonical GPU lock acquired (attempt {attempt})")
            return fd
        except OSError:
            if time.time() >= deadline:
                art["lock"] = {
                    "acquired_utc": None,
                    "attempts": attempt,
                    "blocked": "lock busy",
                }
                log(f"BLOCKED: canonical GPU lock not acquired after {LOCK_WAIT_S}s")
                return None
            log(f"canonical GPU lock busy (attempt {attempt}); sleeping {POLL_S}s")
            time.sleep(POLL_S)


def release_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:  # noqa: BLE001
        pass
    try:
        os.close(fd)
    except Exception:  # noqa: BLE001
        pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_identity_preflight():
    """Owner-mandated check: sglang must resolve into the configured tree AND
    the module must carry the committed norm inverse-fold.

    The source revision is PARAMETERIZED (the fix is committed on the
    authoritative branch, so no pre-fix hash may be hardcoded).  Identity is
    established structurally -- sglang resolves inside SRC, the module is the
    expected file, and both fold helpers exist with the fold call wired into
    ``load_weights``.  The observed content hash is RECORDED for provenance;
    if GGUF_GATE_MODULE_SHA256 is set, it is also enforced exactly.
    """
    rec = {
        "expected_src": SRC,
        "expected_module": PATCHED_MODULE,
        "expected_module_sha256": PATCHED_FILE_SHA256,
        "required_fold_helpers": list(FOLD_HELPERS),
    }
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = (
        "import inspect, sglang, sglang.srt.models.qwen3_5_text as m;"
        "print('SGLANG=' + sglang.__file__);"
        "print('MODULE=' + m.__file__);"
        "print('HELPERS=' + ','.join("
        "h for h in %r if hasattr(m, h)));"
        "src = inspect.getsource(m.Qwen3_5ForCausalLM.load_weights);"
        "print('FOLD_WIRED=' + str('_gguf_fold_absolute_norms' in src))"
        % (FOLD_HELPERS,)
    )
    try:
        out = subprocess.check_output(
            [PY, "-c", probe],
            env=env,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
    except subprocess.CalledProcessError as e:
        rec["error"] = f"import probe rc={e.returncode}: {e.output[-2000:]}"
        rec["ok"] = False
        return False, rec
    sglang_file = module_file = None
    helpers = []
    fold_wired = None
    for line in out.splitlines():
        if line.startswith("SGLANG="):
            sglang_file = line[len("SGLANG=") :].strip()
        elif line.startswith("MODULE="):
            module_file = line[len("MODULE=") :].strip()
        elif line.startswith("HELPERS="):
            helpers = [h for h in line[len("HELPERS=") :].strip().split(",") if h]
        elif line.startswith("FOLD_WIRED="):
            fold_wired = line[len("FOLD_WIRED=") :].strip() == "True"
    rec["resolved_sglang_file"] = sglang_file
    rec["resolved_module_file"] = module_file
    rec["fold_helpers_present"] = helpers
    rec["fold_call_wired_in_load_weights"] = fold_wired
    rec["sglang_in_patched_copy"] = bool(sglang_file) and sglang_file.startswith(SRC)
    rec["module_is_patched_file"] = module_file == PATCHED_MODULE
    try:
        rec["actual_module_sha256"] = sha256_file(PATCHED_MODULE)
    except Exception as e:  # noqa: BLE001
        rec["actual_module_sha256"] = f"error: {e}"
    rec["module_sha256_matches_pinned"] = (
        rec["actual_module_sha256"] == PATCHED_FILE_SHA256
        if PATCHED_FILE_SHA256
        else None
    )
    rec["structural_identity_ok"] = bool(
        rec["sglang_in_patched_copy"]
        and rec["module_is_patched_file"]
        and set(FOLD_HELPERS).issubset(set(helpers))
        and fold_wired
    )
    if PATCHED_FILE_SHA256:
        rec["ok"] = bool(
            rec["structural_identity_ok"] and rec["module_sha256_matches_pinned"]
        )
    else:
        rec["ok"] = rec["structural_identity_ok"]
    rec["identity_mode"] = (
        "structural+exact_sha256" if PATCHED_FILE_SHA256 else "structural+recorded_sha256"
    )
    return rec["ok"], rec


def read_proc_environ_pythonpath(pid):
    """Post-launch re-confirmation of the server's own PYTHONPATH."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read()
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    rec = {}
    wanted = ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "CUDA_VISIBLE_DEVICES")
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        k, _, v = item.partition(b"=")
        k = k.decode(errors="replace")
        if k in wanted:
            rec[k] = v.decode(errors="replace")
    rec["pythonpath_is_patched_copy"] = rec.get("PYTHONPATH") == SRC
    return rec


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
        ("chat_capital", "What is the capital of France? Answer with one word.", ["Paris", "paris"]),
    ]
    for tag, q, expected in chat_cases:
        payload = {
            "model": "default",
            "messages": [{"role": "user", "content": q}],
            **SEMANTIC_CONTRACT,
            "max_tokens": 64,
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
            "request_payload": payload,
            "contains_expected": bool(
                content and any(e in content for e in expected)
            ),
        }

    # Code-format probe: the response must be syntactically valid Python.
    # Graded structurally (compile), not by substring, because surface wording
    # legitimately varies across sampling.
    code_prompt = (
        "Write a Python function `def add(a, b):` that returns a+b. "
        "Output only the code, no explanation."
    )
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": code_prompt}],
        **SEMANTIC_CONTRACT,
        "max_tokens": 256,
    }
    code, body = http_json("POST", "/v1/chat/completions", payload)
    content = None
    if isinstance(body, dict):
        try:
            content = body["choices"][0]["message"].get("content")
        except Exception:  # noqa: BLE001
            content = None
    extracted = content or ""
    if "```" in extracted:
        parts = extracted.split("```")
        chunk = max(parts, key=len).strip()
        if chunk.lower().startswith("python"):
            chunk = chunk[len("python"):].strip()
        extracted = chunk
    compile_ok, compile_err = False, None
    try:
        compile(extracted, "<model_output>", "exec")
        compile_ok = True
    except SyntaxError as e:
        compile_err = repr(e)
    res["chat_code"] = {
        "http": code,
        "prompt": code_prompt,
        "content": content,
        "extracted_code": extracted,
        "compile_ok": compile_ok,
        "compile_error": compile_err,
        "raw": body if code != 200 else None,
        "request_payload": payload,
        "contains_expected": bool(compile_ok),
    }

    # Tool-format probe: the qwen3_coder parser must yield a get_weather call
    # with city=Paris from the tool_calls field (not from free text).
    tool_prompt = "What is the current weather in Paris? Use the get_weather tool."
    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": tool_prompt}],
        "tools": TOOL_SCHEMA,
        **SEMANTIC_CONTRACT,
        "max_tokens": 256,
    }
    code, body = http_json("POST", "/v1/chat/completions", payload)
    tool_calls = None
    tool_detail = None
    tool_ok = False
    if isinstance(body, dict):
        try:
            msg = body["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")
        except Exception:  # noqa: BLE001
            tool_calls = None
    if tool_calls:
        try:
            fn = tool_calls[0]["function"]["name"]
            args = json.loads(tool_calls[0]["function"]["arguments"])
            tool_ok = fn == "get_weather" and str(args.get("city", "")).lower().startswith(
                "paris"
            )
            tool_detail = {"name": fn, "arguments": args}
        except Exception as e:  # noqa: BLE001
            tool_detail = {"parse_error": repr(e), "raw": tool_calls}
    res["chat_tool"] = {
        "http": code,
        "prompt": tool_prompt,
        "tool_calls": tool_calls,
        "tool_detail": tool_detail,
        "raw": body if code != 200 else None,
        "request_payload": payload,
        "contains_expected": bool(tool_ok),
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


# ---- >=512-token coherence gate (owner rule 6) -----------------------------
# Objective loop metric reused verbatim from the accepted M1/M2 validity run
# (`m2-m1-generation-validity-20260916/genvalid.py::_ngram_analysis`) so the
# numbers are directly comparable: owner-classified "COHERENT" arms scored
# loop_w4 <= 0.27 and "DEGENERATE" arms >= 0.51.
# ---------------------------------------------------------------------------
# Long-form correctness arms (owner re-scope 2026-09-17)
#
# GATING arm = the model-native SAMPLED contract carried in GGUF metadata
#   M3: general.sampling.temp=1.0 top_p=0.949999988 top_k=20 min_p=0.0
#   M4: same + general.sampling.penalty_repeat=1.0
# The earlier "sampled decoding does NOT fix M3/M4" result used
# T=0.7/top_p=0.8/top_k=20 -- WRONG explicit values, not this contract.
#
# Every request pins ALL fields explicitly (no implicit generation_config
# inheritance): temperature, top_p, top_k, min_p, seed, max_tokens and
# chat_template_kwargs.enable_thinking.
# ---------------------------------------------------------------------------
COHERENCE_SEED = 20260916
COHERENCE_MAX_TOKENS = 640

GREEDY_DIAGNOSTIC_CONTRACT = {
    "temperature": 0.0,
    "top_p": 1.0,
    "top_k": -1,
    "min_p": 0.0,
    "seed": COHERENCE_SEED,
    "max_tokens": COHERENCE_MAX_TOKENS,
    "chat_template_kwargs": {"enable_thinking": False},
}


def sampled_contract(model_key: str) -> dict:
    """The GATING sampled contract, pinned per model from GGUF metadata."""
    sc = dict(MODELS[model_key]["sampling_contract"])
    contract = {
        "temperature": sc["temperature"],
        "top_p": sc["top_p"],
        "top_k": sc["top_k"],
        "min_p": sc["min_p"],
        "seed": COHERENCE_SEED,
        # GGUF names the knob penalty_repeat; sglang's request field is
        # repetition_penalty.  Always pinned explicitly, even when neutral.
        "repetition_penalty": (
            1.0 if sc["repetition_penalty"] is None else sc["repetition_penalty"]
        ),
        "max_tokens": COHERENCE_MAX_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return contract

COHERENCE_PROMPTS = (
    (
        "function_csv",
        "Write a Python function that parses a CSV file and returns a dict of "
        "column sums, where each value is the sum of the numeric values in that "
        "column. Include a docstring and handle missing values by skipping them.",
    ),
    (
        "longform_water",
        "Write a detailed, well-structured essay of at least 900 words explaining "
        "the water cycle, covering evaporation, condensation, precipitation, "
        "collection, and transpiration. Use clear paragraphs.",
    ),
    (
        "explain_tcp",
        "Explain how TCP congestion control works, covering slow start, congestion "
        "avoidance, and the role of acknowledgements. Write several paragraphs.",
    ),
)

# Owner thresholds on the word-level 4-gram loop fraction of the CONTENT
# channel (metric preserved verbatim from the prior harness / genvalid.py):
#   COHERENT <= 0.27 ; DEGENERATE >= 0.51 ; (0.27, 0.51) = BORDERLINE
COHERENCE_GATE = {
    "min_completion_tokens": 512,
    "max_content_loop_w4_inclusive": 0.27,
    "reject_replacement_char": True,
    "min_alpha_words": 30,
    "reject_all_reasoning_empty_content": True,
}


def _ngram_analysis(ids, n):
    n_tok = len(ids)
    if n_tok < n:
        return {"max_rep": 0, "repeat_token_frac": 0.0, "max_contiguous_run": 0}
    grams = [tuple(ids[i : i + n]) for i in range(n_tok - n + 1)]
    counts = Counter(grams)
    max_rep = max(counts.values())
    covered = [False] * n_tok
    for g, cnt in counts.items():
        if cnt > 1:
            for i, gg in enumerate(grams):
                if gg == g:
                    for j in range(i, i + n):
                        covered[j] = True
    best_run = 0
    i = 0
    while i < len(grams):
        j = i + 1
        while j < len(grams) and grams[j] == grams[i]:
            j += 1
        best_run = max(best_run, j - i)
        i = j
    return {
        "max_rep": max_rep,
        "repeat_token_frac": round(sum(covered) / n_tok, 4),
        "max_contiguous_run": best_run,
    }


def _coherence_request(tag, prompt, contract):
    payload = {"model": "default", "messages": [{"role": "user", "content": prompt}]}
    payload.update(contract)
    code, body = http_json("POST", "/v1/chat/completions", payload)
    content = reasoning = finish = usage = None
    if isinstance(body, dict):
        try:
            ch = body["choices"][0]
            msg = ch.get("message", {}) or {}
            content = msg.get("content")
            reasoning = msg.get("reasoning_content")
            finish = ch.get("finish_reason")
        except Exception:  # noqa: BLE001
            pass
        usage = body.get("usage")
    # The model's generation is content + reasoning; measuring only `content`
    # would score an all-reasoning response as zero-length (a metric artifact).
    full = (content or "") + (reasoning or "")
    full_words = re.findall(r"\S+", full)
    content_words = re.findall(r"\S+", content or "")
    m_full = _ngram_analysis(full_words, 4)
    m_content = _ngram_analysis(content_words, 4)
    return {
        "tag": tag,
        "http": code,
        "prompt": prompt,
        "contract": contract,
        # exact wire body actually sent (evidence for the pinned contract)
        "request_payload": payload,
        "finish_reason": finish,
        "usage": usage,
        "n_completion_tokens": (usage or {}).get("completion_tokens"),
        "content_n_chars": len(content or ""),
        "reasoning_n_chars": len(reasoning or ""),
        "full_n_chars": len(full),
        "content_empty": not bool((content or "").strip()),
        "reasoning_only": bool((reasoning or "").strip())
        and not bool((content or "").strip()),
        "content_sha256": hashlib.sha256((content or "").encode()).hexdigest(),
        "full_sha256": hashlib.sha256(full.encode()).hexdigest(),
        "first_300_chars": full[:300],
        "first_300_content": (content or "")[:300],
        "first_300_reasoning": (reasoning or "")[:300],
        "contains_replacement_char": chr(0xFFFD) in full,
        "n_alpha_words": sum(1 for w in re.findall(r"[A-Za-z]{2,}", full)),
        "loop_w4": m_full["repeat_token_frac"],
        "w4_max_contiguous_run": m_full["max_contiguous_run"],
        "w4_max_rep": m_full["max_rep"],
        "content_loop_w4": m_content["repeat_token_frac"],
        "content_w4_max_contiguous_run": m_content["max_contiguous_run"],
        "content_w4_max_rep": m_content["max_rep"],
        "reasoning_content_len": len(reasoning or ""),
        "raw_body": body if code != 200 else None,
    }


def classify_coherence(rec):
    """Owner threshold classification on the CONTENT channel only."""
    if rec.get("http") != 200:
        return "HTTP_ERROR"
    if rec.get("n_completion_tokens") is None:
        return "NO_USAGE"
    if rec.get("content_empty"):
        return "EMPTY_CONTENT"
    if rec.get("n_alpha_words", 0) < COHERENCE_GATE["min_alpha_words"]:
        return "TOO_SHORT"
    w = rec.get("content_loop_w4", 0.0)
    if w <= 0.27:
        return "COHERENT"
    if w >= 0.51:
        return "DEGENERATE"
    return "BORDERLINE"


def _passes_coherence(rec):
    """GATING predicate: >=512 tokens AND coherent CONTENT under sampling.

    Fail-closed: an all-reasoning / empty-content response fails even when the
    (full-channel) loop metric would look benign, because the deliverable is
    user-visible content.
    """
    if COHERENCE_GATE["reject_all_reasoning_empty_content"] and rec.get(
        "content_empty"
    ):
        return False
    return (
        rec["http"] == 200
        and isinstance(rec["n_completion_tokens"], int)
        and rec["n_completion_tokens"] >= COHERENCE_GATE["min_completion_tokens"]
        and rec.get("content_loop_w4", 1.0)
        <= COHERENCE_GATE["max_content_loop_w4_inclusive"]
        and not rec["contains_replacement_char"]
        and rec["n_alpha_words"] >= COHERENCE_GATE["min_alpha_words"]
    )


def step_coherence(art):
    """Long-form correctness, split into one GATING arm + two diagnostics.

    GATING  : ``step5_coherence`` -- >=512-token chat generation under the
              frozen explicit SAMPLED contract (GGUF general.sampling.*) with
              enable_thinking=false.  Gate = content_loop_w4 <= 0.27.
    DIAG-A  : ``step5a_greedy_diagnostic`` -- the demoted greedy arm, recorded
              for comparability with the prior evidence only.
    DIAG-B  : ``step5b_thinking_probe`` -- thinking ON, non-gating.

    Raw /generate text completion is prompt-format misuse on a chat model and
    streaming-concat is a known artifact, so neither is used (owner rule).
    """
    key = art["model_key"]
    sampled = sampled_contract(key)

    gating = {}
    for tag, prompt in COHERENCE_PROMPTS:
        rec = _coherence_request(tag, prompt, sampled)
        rec["classification"] = classify_coherence(rec)
        rec["passes_gate"] = _passes_coherence(rec)
        gating[tag] = rec
    passing = [tag for tag, rec in gating.items() if rec["passes_gate"]]
    art["step5_coherence"] = {
        "arm": "GATING_sampled",
        "contract": sampled,
        "contract_source": "GGUF metadata general.sampling.* for " + key,
        "gate": COHERENCE_GATE,
        "probes": gating,
        "passing_probes": passing,
        "coherence_pass": bool(passing),
    }

    # Diagnostic A: greedy (demoted; recorded for comparability with prior run)
    greedy = {}
    for tag, prompt in COHERENCE_PROMPTS:
        rec = _coherence_request(tag, prompt, GREEDY_DIAGNOSTIC_CONTRACT)
        rec["classification"] = classify_coherence(rec)
        rec["passes_gate"] = _passes_coherence(rec)
        greedy[tag] = rec
    art["step5a_greedy_diagnostic"] = {
        "arm": "DIAGNOSTIC_greedy",
        "gating": False,
        "note": (
            "DEMOTED to diagnostic evidence per owner re-scope 2026-09-17; "
            "not part of the verdict. Comparable to the prior gate's criterion 3."
        ),
        "contract": GREEDY_DIAGNOSTIC_CONTRACT,
        "gate": COHERENCE_GATE,
        "probes": greedy,
        "passing_probes": [t for t, r in greedy.items() if r["passes_gate"]],
    }

    # Diagnostic B: thinking ON
    on_contract = dict(sampled)
    on_contract["chat_template_kwargs"] = {"enable_thinking": True}
    on_tag, on_prompt = COHERENCE_PROMPTS[1]
    on_rec = _coherence_request(f"{on_tag}_thinkingON", on_prompt, on_contract)
    on_rec["classification"] = classify_coherence(on_rec)
    on_rec["passes_gate"] = _passes_coherence(on_rec)
    art["step5b_thinking_probe"] = {
        "arm": "DIAGNOSTIC_thinking_on",
        "gating": False,
        "note": "NON-GATING diagnostic: same long-form prompt with thinking ON",
        "probe": on_rec,
    }
    return art["step5_coherence"]


def kv_gate(logtext):
    m = re.search(r"KV Cache is allocated\. dtype: ([^,]+), #tokens: (\d+)", logtext)
    if not m:
        return {"ok": False, "reason": "KV Cache allocation line not found"}
    dtype, tokens = m.group(1), int(m.group(2))
    ok = dtype.strip() == "torch.float8_e4m3fn"
    return {"ok": ok, "dtype": dtype.strip(), "tokens": tokens}


def _vision_tag_outcome(rec):
    """Classify one vision probe result under the text-only ruling."""
    if not isinstance(rec, dict):
        return "missing"
    http = rec.get("http")
    if http == 400:
        return "expected_out_of_scope_http400"
    if http == 200:
        return "http200_still_unscored"
    return f"unexpected_http{http}"


def vision_record(art, vision_applicable):
    """Record vision as deliberately unscored (never a pass, never gating).

    A reader must be unable to confuse "vision was not evaluated by policy"
    with "vision verified".  ``outcome`` names exactly what happened.
    """
    vis = art.get("step2_vision") if isinstance(art.get("step2_vision"), dict) else None
    attempted = bool(vis) and any(
        isinstance(vis.get(t), dict) for t in ("color", "shape"))
    rec = {
        "scope": VISION_SCOPE,
        "scored": False,
        "ruling": VISION_RULING,
        "attempted": attempted,
        "expected_out_of_scope": True,
    }
    if not vision_applicable:
        rec["outcome"] = "not_applicable"
    elif not attempted:
        rec["outcome"] = "skipped_by_policy"
    else:
        rec["outcome"] = {
            tag: _vision_tag_outcome(vis.get(tag)) for tag in ("color", "shape")}
    return rec


def evaluate_verdict(art):
    """Fail-closed per-model verdict, derived from the per-criterion report.

    PASS only when every required criterion actually executed and passed.
    Missing evidence is a failure, never the absence of a failure.
    Vision is OUT OF SCOPE (text-only owner ruling) and is never part of this
    verdict; it is recorded separately by ``vision_record``.
    """
    rep = criterion_report(art)
    return ("PASS" if rep["all_pass"] else "FAIL"), rep["failures"]


def criterion_report(art):
    """Per-criterion breakdown so a PARTIAL result stays legible.

    Criteria (owner list 2026-09-17):
      1 finite logits, 0 non-finite
      2 short deterministic semantic correctness (51 / Paris / code / tool)
      3 CUDA graph capture+replay, 0 errors
      4 fp8 KV confirmed
      5 no quant-or-kernel fallback
      6 coherent >=512-token generation under the SAMPLED contract
        (content loop_w4 <= 0.27; content-empty-all-reasoning fails)
    """
    crit = {}

    # 1 -- finite logits
    fl = art.get("step1_finite_logits")
    f1 = {"name": "finite_logits_no_nonfinite", "pass": False, "detail": {}}
    if isinstance(fl, dict):
        ok = True
        for tag in FINITE_LOGIT_TAGS:
            rec = fl.get(tag) if isinstance(fl.get(tag), dict) else {}
            n_checked = rec.get("n_logprob_values_checked", 0)
            n_bad = rec.get("n_nonfinite")
            good = rec.get("http") == 200 and n_checked > 0 and n_bad == 0
            ok = ok and good
            f1["detail"][tag] = {
                "http": rec.get("http"),
                "n_logprob_values_checked": n_checked,
                "n_nonfinite": n_bad,
                "pass": good,
            }
        f1["pass"] = ok
    crit["1_finite_logits"] = f1

    # 2 -- deterministic short-form semantic correctness (chat path)
    sem = art.get("step2_semantic") if isinstance(art.get("step2_semantic"), dict) else {}
    f2 = {"name": "short_deterministic_semantics", "pass": False, "detail": {}}
    # Every GATING semantic probe must have executed on the chat path; a probe
    # missing entirely is a failure, not the absence of a failure.  The raw
    # /generate tags (arithmetic/capital/echo) stay recorded-only diagnostics:
    # the owner ruling states raw text completion on a chat model is
    # prompt-format misuse, so it must not gate.
    for tag in GATING_SEMANTIC_TAGS:
        rec = sem.get(tag) if isinstance(sem.get(tag), dict) else None
        if rec is None or rec.get("http") != 200:
            f2["detail"][f"{tag}__executed"] = {
                "http": (rec or {}).get("http"),
                "pass": False,
                "note": "required gating probe did not execute",
            }
    checks = (
        ("chat_arithmetic", "contains_expected", "51"),
        ("chat_capital", "contains_expected", "Paris"),
        ("chat_code", "compile_ok", "code compiles"),
        ("chat_tool", "contains_expected", "get_weather(city=Paris)"),
    )
    ok2 = True
    for tag, field, label in checks:
        rec = sem.get(tag) if isinstance(sem.get(tag), dict) else {}
        good = rec.get("http") == 200 and bool(rec.get(field))
        ok2 = ok2 and good
        f2["detail"][tag] = {
            "expects": label,
            "http": rec.get("http"),
            "observed": rec.get(field),
            "pass": good,
        }
    ok2 = ok2 and not any(
        v.get("pass") is False and k.endswith("__executed")
        for k, v in f2["detail"].items()
    )
    f2["pass"] = ok2
    crit["2_semantics"] = f2

    # 3 -- CUDA graph capture + replay, 0 errors
    gd = art.get("step4_graph_device") if isinstance(art.get("step4_graph_device"), dict) else {}
    capture_lines = gd.get("graph_log_line_count", 0) or 0
    graph_errs = gd.get("graph_error_lines") or []
    batch = art.get("decode_batch_probe") or {}
    replay_ok = bool(batch) and all(
        isinstance(v, list) and all(c == 200 for c in v) for v in batch.values()
    )
    crit["3_cuda_graph"] = {
        "name": "cuda_graph_capture_and_replay",
        "pass": bool(capture_lines > 0 and not graph_errs and replay_ok),
        "detail": {
            "capture_log_lines": capture_lines,
            "graph_error_lines": graph_errs[:10],
            "decode_batch_replay_http": batch,
        },
    }

    # 4 -- fp8 KV confirmed
    kv = art.get("kv_gate") if isinstance(art.get("kv_gate"), dict) else {}
    crit["4_fp8_kv"] = {
        "name": "fp8_e4m3_kv_confirmed",
        "pass": bool(kv.get("ok")),
        "detail": {
            "dtype": kv.get("dtype"),
            "tokens": kv.get("tokens"),
            "reason": kv.get("reason"),
        },
    }

    # 5 -- no quant-or-kernel fallback
    sig = art.get("step3_server_signals") if isinstance(art.get("step3_server_signals"), dict) else {}
    fb = sig.get("fallback_warnings") or {}
    ni = sig.get("not_implemented") or {}
    bad_lines = (fb.get("count") or 0) + (ni.get("count") or 0)
    crit["5_no_fallback"] = {
        "name": "no_quant_or_kernel_fallback",
        "pass": bad_lines == 0,
        "detail": {
            "fallback_count": fb.get("count"),
            "not_implemented_count": ni.get("count"),
            "fallback_samples": (fb.get("sample") or [])[:5],
            "not_implemented_samples": (ni.get("sample") or [])[:5],
        },
    }

    # 6 -- GATING sampled >=512-token coherence on the content channel
    coh = art.get("step5_coherence") if isinstance(art.get("step5_coherence"), dict) else {}
    probes = coh.get("probes") or {}
    f6 = {
        "name": "sampled_ge512_coherent_content",
        "pass": bool(coh.get("coherence_pass")),
        "contract": coh.get("contract"),
        "detail": {
            tag: {
                "http": rec.get("http"),
                "classification": rec.get("classification"),
                "n_completion_tokens": rec.get("n_completion_tokens"),
                "finish_reason": rec.get("finish_reason"),
                "content_loop_w4": rec.get("content_loop_w4"),
                "full_loop_w4": rec.get("loop_w4"),
                "content_n_chars": rec.get("content_n_chars"),
                "reasoning_n_chars": rec.get("reasoning_n_chars"),
                "content_empty": rec.get("content_empty"),
                "contains_replacement_char": rec.get("contains_replacement_char"),
                "n_alpha_words": rec.get("n_alpha_words"),
                "pass": rec.get("passes_gate"),
            }
            for tag, rec in probes.items()
        },
        "passing_probes": coh.get("passing_probes"),
    }
    crit["6_sampled_coherence"] = f6

    # diagnostics (never part of all_pass)
    diag = {}
    g = art.get("step5a_greedy_diagnostic")
    if isinstance(g, dict):
        diag["greedy_ge512"] = {
            "contract": g.get("contract"),
            "per_probe": {
                tag: {
                    "classification": rec.get("classification"),
                    "content_loop_w4": rec.get("content_loop_w4"),
                    "full_loop_w4": rec.get("loop_w4"),
                    "n_completion_tokens": rec.get("n_completion_tokens"),
                    "passes_gate": rec.get("passes_gate"),
                }
                for tag, rec in (g.get("probes") or {}).items()
            },
        }
    t = art.get("step5b_thinking_probe")
    if isinstance(t, dict):
        rec = t.get("probe") or {}
        diag["thinking_on"] = {
            "classification": rec.get("classification"),
            "content_loop_w4": rec.get("content_loop_w4"),
            "full_loop_w4": rec.get("loop_w4"),
            "n_completion_tokens": rec.get("n_completion_tokens"),
        }

    failures = [k for k, v in crit.items() if not v["pass"]]
    if art.get("status") != "completed":
        failures.append(f"status={art.get('status')!r}")
    if art.get("step_exception"):
        failures.append("step_exception")
    return {
        "criteria": crit,
        "diagnostics": diag,
        "failures": failures,
        "all_pass": not failures,
    }


def verdict_exit_code(verdict):
    return 0 if verdict == "PASS" else 5


def finish(outdir, art, rc, require_vision):
    """Attach the verdict, write the artifact, and return the process exit code."""
    verdict, failures = evaluate_verdict(art)
    art["verdict"] = verdict
    art["verdict_failures"] = failures
    art["criterion_report"] = criterion_report(art)
    art["vision_scope"] = VISION_SCOPE
    art["vision_scored"] = False
    art["vision_record"] = vision_record(art, require_vision)
    art.setdefault("finished_utc", now())
    write_art(outdir, art)
    if verdict != "PASS":
        return rc if rc else verdict_exit_code(verdict)
    return 0


def _serve_and_probe(art, outdir, logpath, key, spec):
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
    art["proc_environ"] = read_proc_environ_pythonpath(proc.pid)
    log(
        f"{key}: /proc/{proc.pid}/environ PYTHONPATH is patched copy: "
        f"{art['proc_environ'].get('pythonpath_is_patched_copy')}"
    )

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
        log(f"{key}: SERVER FAILED: {why}")
        return finish(outdir, art, 3, spec["vision"])

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
        return finish(outdir, art, 4, spec["vision"])
    log(f"{key}: KV gate OK ({gate['dtype']}, tokens={gate['tokens']})")

    try:
        code, info = http_json("GET", "/get_server_info", timeout=30)
        art["server_info"] = info if code == 200 else {"http": code}
    except Exception as e:  # noqa: BLE001
        art["server_info"] = {"error": str(e)}

    try:
        step_finite_logits(art)
        step_semantic(art)
        step_coherence(art)
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
    terminate(proc)
    logf.close()
    log(f"{key}: harness completed, vram={used1} MiB")
    return finish(outdir, art, 0, spec["vision"])


def main():
    key = sys.argv[1]
    spec = MODELS[key]
    spec["key"] = key
    outdir = os.path.join(RUNROOT, key)
    os.makedirs(outdir, exist_ok=True)
    logpath = os.path.join(outdir, "server.log")
    art = {
        "model_key": key,
        "model_name": spec["name"],
        "gguf": spec["gguf"],
        "expected_sha256": spec["sha256"],
        "started_utc": now(),
        "source": SRC,
        "pythonpath": SRC,
        "patched_module": PATCHED_MODULE,
        "expected_patched_file_sha256": PATCHED_FILE_SHA256,
        "launcher_used": False,
        "launch_mode": "explicit PYTHONPATH + python -m sglang.launch_server",
        "cuda_visible_devices": GPU,
        "port": PORT,
        "mtp": "off",
    }

    lock_fd = acquire_lock(art)
    if lock_fd is None:
        art["status"] = "blocked_gpu_lock_busy"
        log(f"{key}: BLOCKED: canonical GPU lock busy; server not started")
        return finish(outdir, art, 2, spec["vision"])
    try:
        waited = 0
        while not port_free() and waited < 180:
            log(f"{key}: port {PORT} still busy; waiting 5s ({waited}s)")
            time.sleep(5)
            waited += 5
        if not port_free():
            art["status"] = "blocked_port_busy"
            log(f"{key}: BLOCKED: port {PORT} busy; server not started")
            return finish(outdir, art, 2, spec["vision"])

        ok, preflight = source_identity_preflight()
        art["source_preflight"] = preflight
        if not ok:
            art["status"] = "source_identity_preflight_failed"
            log(f"{key}: SOURCE-IDENTITY PREFLIGHT FAILED: {preflight}")
            return finish(outdir, art, 6, spec["vision"])
        log(f"{key}: source-identity preflight OK (sglang -> patched copy)")

        return _serve_and_probe(art, outdir, logpath, key, spec)
    finally:
        release_lock(lock_fd)


def write_art(outdir, art):
    with open(os.path.join(outdir, "report.json"), "w") as f:
        json.dump(art, f, indent=2)
    log(f"wrote {os.path.join(outdir, 'report.json')}")


# ---------------------------------------------------------------------------
# CPU smoke: prove what the gate SENDS and that the loop metric is unchanged.
# Touches no GPU, opens no socket, needs no server.
# ---------------------------------------------------------------------------
def cpu_smoke():
    """Deterministic offline check of the request-building + scoring logic.

    1. Build (never send) the exact JSON body of the gating sampled request for
       both models and assert every required contract field is present/pinned.
    2. Prove ``_ngram_analysis`` is bit-identical in behavior to the prior
       authenticated implementation by running both on fixed inputs.
    3. Prove the gate threshold is the re-scoped one (<=0.27 on content).
    """
    out = {"python": sys.executable, "ok": True, "checks": {}}

    # --- 1. exact request bodies -------------------------------------------------
    bodies = {}
    required = (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "seed",
        "max_tokens",
        "chat_template_kwargs",
    )
    for key in ("m4", "m3"):
        contract = sampled_contract(key)
        payload = {
            "model": "default",
            "messages": [
                {"role": "user", "content": COHERENCE_PROMPTS[0][1]}
            ],
        }
        payload.update(contract)
        missing = [f for f in required if f not in payload]
        ok = not missing
        checks = {
            "missing_required_fields": missing,
            "temperature_is_1.0": payload["temperature"] == 1.0,
            "top_p_is_0.95": payload["top_p"] == 0.95,
            "top_k_is_20": payload["top_k"] == 20,
            "min_p_is_0.0": payload["min_p"] == 0.0,
            "seed_is_20260916": payload["seed"] == 20260916,
            "max_tokens_is_640": payload["max_tokens"] == 640,
            "thinking_disabled": payload["chat_template_kwargs"]
            == {"enable_thinking": False},
            "endpoint": "/v1/chat/completions",
            "not_raw_generate": "text" not in payload
            and "sampling_params" not in payload,
            "not_streaming": payload.get("stream") is None,
        }
        if key == "m4":
            checks["m4_repetition_penalty_pinned_1.0"] = (
                payload["repetition_penalty"] == 1.0
            )
        else:
            # M3 has no penalty_repeat in metadata; the field is still pinned
            # explicitly (neutral 1.0) so no implicit default can leak in.
            checks["m3_repetition_penalty_pinned_neutral"] = (
                payload["repetition_penalty"] == 1.0
            )
        ok = ok and all(v for k, v in checks.items() if isinstance(v, bool))
        out["checks"][f"request_body_{key}"] = {"pass": ok, **checks}
        bodies[key] = payload
        out["ok"] = out["ok"] and ok
    out["request_bodies"] = bodies

    # --- 2. ngram metric equivalence --------------------------------------------
    # Reference: byte-copy of genvalid.py::_ngram_analysis (prior authenticated
    # implementation), written out here literally for the comparison.
    def ref_ngram_analysis(ids, n):
        from collections import Counter as _C

        n_tok = len(ids)
        if n_tok < n:
            return {"max_rep": 0, "repeat_token_frac": 0.0, "max_contiguous_run": 0}
        grams = [tuple(ids[i : i + n]) for i in range(n_tok - n + 1)]
        c = _C(grams)
        max_rep = max(c.values())
        covered = [False] * n_tok
        for g, cnt in c.items():
            if cnt > 1:
                for i, gg in enumerate(grams):
                    if gg == g:
                        for j in range(i, i + n):
                            covered[j] = True
        best_run = 0
        i = 0
        while i < len(grams):
            j = i + 1
            while j < len(grams) and grams[j] == grams[i]:
                j += 1
            best_run = max(best_run, j - i)
            i = j
        return {
            "max_rep": max_rep,
            "repeat_token_frac": round(sum(covered) / n_tok, 4),
            "max_contiguous_run": best_run,
        }

    cases = {
        "empty": [],
        "shorter_than_n": ["a", "b"],
        "no_repeat": ["the", "water", "cycle", "moves", "water", "vapour", "rises"],
        "pure_loop": ["loop"] * 40,
        "period4_loop": ["one", "two", "three", "four"] * 12,
        "mixed": ["alpha", "beta", "gamma", "delta", "alpha", "beta", "gamma",
                  "delta", "alpha", "beta", "gamma", "x", "y", "z", "w", "x",
                  "y", "z", "w", "q"],
        "single_word_heavy": ["ok"] * 3 + ["then", "more", "words", "here"] * 2,
    }
    eq_ok = True
    detail = {}
    for name, toks in cases.items():
        got = _ngram_analysis(toks, 4)
        want = ref_ngram_analysis(toks, 4)
        same = (
            got["max_rep"] == want["max_rep"]
            and got["repeat_token_frac"] == want["repeat_token_frac"]
            and got["max_contiguous_run"] == want["max_contiguous_run"]
        )
        eq_ok = eq_ok and same
        detail[name] = {"ours": got, "reference": want, "identical": same}
    out["checks"]["ngram_metric_identical_to_prior"] = {
        "pass": eq_ok,
        "n_cases": len(cases),
        "cases": detail,
    }
    out["ok"] = out["ok"] and eq_ok

    # --- 3. threshold wiring ------------------------------------------------------
    thr = COHERENCE_GATE["max_content_loop_w4_inclusive"]
    thr_ok = thr == 0.27
    out["checks"]["gate_threshold_is_content_w4_0.27"] = {
        "pass": thr_ok,
        "gate": COHERENCE_GATE,
    }
    out["ok"] = out["ok"] and thr_ok

    # A synthetic all-reasoning response must FAIL the gating predicate.
    synthetic = {
        "http": 200,
        "n_completion_tokens": 640,
        "content_loop_w4": 0.0,
        "loop_w4": 0.0,
        "contains_replacement_char": False,
        "n_alpha_words": 200,
        "content_empty": True,
    }
    reason_fail = _passes_coherence(synthetic) is False
    synth2 = dict(synthetic, content_empty=False, content_loop_w4=0.27)
    at_bound_passes = _passes_coherence(synth2) is True
    synth3 = dict(synthetic, content_empty=False, content_loop_w4=0.271)
    above_bound_fails = _passes_coherence(synth3) is False
    gate_ok = reason_fail and at_bound_passes and above_bound_fails
    out["checks"]["gating_predicate_semantics"] = {
        "pass": gate_ok,
        "empty_content_fails": reason_fail,
        "w4_exactly_0.27_passes": at_bound_passes,
        "w4_0.271_fails": above_bound_fails,
    }
    out["ok"] = out["ok"] and gate_ok

    # --- 4. drive the REAL send path with a stubbed transport ---------------------
    # Monkeypatch http_json so the actual ``_coherence_request`` /
    # ``step_coherence`` code builds the payload and scores the response,
    # without opening any socket.  This is the evidence that the gating arm's
    # wire body is what the gate will really send.
    captured = []

    def fake_http_json(method, path, payload=None, timeout=600):
        captured.append({"method": method, "path": path, "payload": payload})
        # A coherent, >=512-token-ish response with no repetition: every word
        # distinct is impossible over 600 words, so use a natural-ish corpus.
        words = []
        for i in range(140):
            words += [f"tok{i}", f"phrase{i}", "the", f"{i}x", "and", "then"]
        text = " ".join(words)
        return 200, {
            "choices": [
                {
                    "message": {"content": text, "reasoning_content": None},
                    "finish_reason": "length",
                }
            ],
            "usage": {"completion_tokens": 840},
        }

    real_http_json = globals()["http_json"]
    try:
        globals()["http_json"] = fake_http_json
        art = {
            "model_key": "m4",
            "step1_finite_logits": {
                "p1": {"http": 200, "n_logprob_values_checked": 72, "n_nonfinite": 0},
                "p2": {"http": 200, "n_logprob_values_checked": 126, "n_nonfinite": 0},
            },
            "step2_semantic": {
                "arithmetic": {"http": 200, "contains_expected": True},
                "capital": {"http": 200, "contains_expected": True},
                "echo": {"http": 200, "contains_expected": True},
                "chat_arithmetic": {"http": 200, "contains_expected": True},
                "chat_capital": {"http": 200, "contains_expected": True},
                "chat_code": {"http": 200, "compile_ok": True},
                "chat_tool": {"http": 200, "contains_expected": True},
            },
            "kv_gate": {"ok": True, "dtype": "torch.float8_e4m3fn", "tokens": 8192},
            "step3_server_signals": {
                "fallback_warnings": {"count": 0, "sample": []},
                "not_implemented": {"count": 0, "sample": []},
            },
            "step4_graph_device": {
                "graph_log_line_count": 12,
                "graph_error_lines": [],
            },
            "decode_batch_probe": {"bs2": [200, 200], "bs4": [200, 200, 200, 200]},
            "status": "completed",
        }
        step_coherence(art)
        rep = criterion_report(art)
    finally:
        globals()["http_json"] = real_http_json

    sent = [c for c in captured if c["path"] == "/v1/chat/completions"]
    gating_sent = sent[: len(COHERENCE_PROMPTS)]
    all_gating_pinned = all(
        c["payload"].get("temperature") == 1.0
        and c["payload"].get("top_p") == 0.95
        and c["payload"].get("top_k") == 20
        and c["payload"].get("min_p") == 0.0
        and c["payload"].get("seed") == 20260916
        and c["payload"].get("max_tokens") == 640
        and c["payload"].get("repetition_penalty") == 1.0
        and c["payload"].get("chat_template_kwargs") == {"enable_thinking": False}
        for c in gating_sent
    )
    diag_greedy = sent[len(COHERENCE_PROMPTS) : 2 * len(COHERENCE_PROMPTS)]
    greedy_is_greedy = all(
        c["payload"].get("temperature") == 0.0
        and c["payload"].get("top_p") == 1.0
        and c["payload"].get("top_k") == -1
        for c in diag_greedy
    )
    thinking_on = sent[-1]["payload"].get("chat_template_kwargs") == {
        "enable_thinking": True
    }
    endpoints_ok = all(c["path"] == "/v1/chat/completions" for c in captured)
    send_ok = (
        len(gating_sent) == len(COHERENCE_PROMPTS)
        and all_gating_pinned
        and greedy_is_greedy
        and thinking_on
        and endpoints_ok
    )
    out["checks"]["real_send_path_pins_sampled_contract"] = {
        "pass": send_ok,
        "n_requests": len(captured),
        "all_endpoints_chat_completions": endpoints_ok,
        "gating_requests_all_pinned": all_gating_pinned,
        "greedy_diagnostic_requests_are_greedy": greedy_is_greedy,
        "thinking_probe_is_on": thinking_on,
        "gating_payload_example": gating_sent[0]["payload"] if gating_sent else None,
    }
    out["ok"] = out["ok"] and send_ok

    # --- 5. per-criterion reporting on the stub artifact --------------------------
    crit_ok = (
        len(rep["criteria"]) == 6
        and rep["all_pass"] is True
        and set(rep["criteria"])
        == {
            "1_finite_logits",
            "2_semantics",
            "3_cuda_graph",
            "4_fp8_kv",
            "5_no_fallback",
            "6_sampled_coherence",
        }
        and rep["criteria"]["6_sampled_coherence"]["pass"] is True
        and "greedy_ge512" in rep["diagnostics"]
    )
    # ... and a single failing criterion must FAIL the whole verdict while
    # leaving the other criteria legible as passes.
    art_bad = json.loads(json.dumps(art))
    art_bad["step2_semantic"]["chat_capital"]["contains_expected"] = False
    rep_bad = criterion_report(art_bad)
    bad_ok = (
        rep_bad["all_pass"] is False
        and rep_bad["failures"] == ["2_semantics"]
        and rep_bad["criteria"]["1_finite_logits"]["pass"] is True
        and rep_bad["criteria"]["6_sampled_coherence"]["pass"] is True
    )
    out["checks"]["per_criterion_reporting"] = {
        "pass": bool(crit_ok and bad_ok),
        "all_six_present_and_pass": crit_ok,
        "single_failure_isolated": bad_ok,
        "failures": rep_bad["failures"],
    }
    out["ok"] = out["ok"] and crit_ok and bad_ok

    # --- 6. compare against the LIVE prior harness module -------------------------
    prior_path = (
        "/var/log/sglang/local-prod-v1/phase8/m3-m4-normfix-gate-20260916/"
        "server_harness_normfix.py"
    )
    prior_rec = {"path": prior_path, "available": os.path.exists(prior_path)}
    if prior_rec["available"]:
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "prior_normfix_harness", prior_path
            )
            prior = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(prior)
            prior_rec["sha256"] = sha256_file(prior_path)
            same_all = True
            cmp_detail = {}
            for name, toks in cases.items():
                a = _ngram_analysis(toks, 4)
                b = prior._ngram_analysis(toks, 4)
                same = (
                    a["max_rep"] == b["max_rep"]
                    and a["repeat_token_frac"] == b["repeat_token_frac"]
                    and a["max_contiguous_run"] == b["max_contiguous_run"]
                )
                same_all = same_all and same
                cmp_detail[name] = {"ours": a, "prior": b, "identical": same}
            # compare over a longer, pseudo-random-but-deterministic corpus too
            big = [f"w{(i * 7919) % 233}" for i in range(5000)]
            a, b = _ngram_analysis(big, 4), prior._ngram_analysis(big, 4)
            big_same = (
                a["max_rep"] == b["max_rep"]
                and a["repeat_token_frac"] == b["repeat_token_frac"]
                and a["max_contiguous_run"] == b["max_contiguous_run"]
            )
            prior_rec.update(
                {
                    "identical_on_all_cases": bool(same_all and big_same),
                    "cases": cmp_detail,
                    "large_corpus_identical": big_same,
                    "prior_module": prior.__file__,
                }
            )
        except Exception as e:  # noqa: BLE001
            prior_rec["error"] = f"{type(e).__name__}: {e}"
            prior_rec["identical_on_all_cases"] = None
    out["checks"]["ngram_identical_to_live_prior_harness"] = {
        "pass": prior_rec.get("identical_on_all_cases") is True,
        **prior_rec,
    }
    out["ok"] = out["ok"] and prior_rec.get("identical_on_all_cases") is True

    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


def _cli_main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("--cpu-smoke", "cpu-smoke"):
        return cpu_smoke()
    if not argv or argv[0] not in MODELS:
        print("usage: server_harness_sampled.py <m4|m3> | --cpu-smoke", file=sys.stderr)
        return 64
    return main()


if __name__ == "__main__":
    sys.exit(_cli_main())
