#!/usr/bin/env python3
"""Shared, stdlib-only helpers for the final M1 GPU gate harnesses.

Gates in this directory:
  * ``gate_a_content_integrity.py``  -- Gate A: DEVICE == L3 == RECOVERED ids.
  * ``gate_a_f1_cold_l1.py``         -- Gate A-F1: post-sweep cold-L1 head proof.
  * ``f2_restart_recovery.py``       -- F2: genuine restart + rotation + restore.

Frozen store policy enforced here:
  * Every run uses a UNIQUE L3 store namespace under ``/data/l3/<task-id>/``.
  * This module never clears, truncates, flushes, or unlinks a store file.
  * The shared production store ``/data/l3/local-prod-v1.1`` is refused.

The module imports no torch/sglang; all tree-bound work runs in subprocesses of
the tree's own interpreter (``prompt_builder.py`` / ``wal_forensics.py``).
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ------------------------------------------------------------------ constants
TASK_ID = "phase9-gates-final-20260916"
HARNESS_DIR = pathlib.Path(__file__).resolve().parent
RUN_DIR = pathlib.Path(
    os.environ.get("SGLANG_GATE_RUN_DIR",
                   f"/var/log/sglang/local-prod-v1.1/{TASK_ID}"))

DEFAULT_TREE = os.environ.get("SGLANG_GATE_TREE",
                              "/opt/sglang/local-prod-v1.1-candidate")
DEFAULT_MODEL = os.environ.get("SGLANG_GATE_MODEL",
                               "/data/models/qwen35-9b-w4a16")
DEFAULT_PORT = int(os.environ.get("SGLANG_GATE_PORT", "30165"))
DEFAULT_GPU_UUID = os.environ.get(
    "SGLANG_GATE_GPU_UUID", "GPU-2e3ed202-3655-d919-0a64-259209bc6587")
LOCK_PATH = os.environ.get("SGLANG_GATE_LOCK", "/tmp/opencode/gpu-3090.lock")

PRODUCTION_STORE = "/data/l3/local-prod-v1.1"
L3_ROOT = os.environ.get("SGLANG_GATE_L3_ROOT", "/data/l3")
CUDA_HOME = "/usr/local/cuda-12.9"

MODEL_NAME_SLUG = "-".join(DEFAULT_MODEL.split("/"))
DEFAULT_CONFIG_SUFFIX = f"_{MODEL_NAME_SLUG}_0_1"

SEED = 20260916

# ---------------------------------------------------------------- HiCache sizing
#
# LOCAL-PROD-v1.1.2 / qwen35-9b-w4a16 / --kv-cache-dtype fp8_e4m3:
#   * one KV token in the *host* pool is 16 KiB
#     (``head_dim * head_num * layer_num * itemsize * 2`` == 16384 B).
#   * ``--hicache-size`` is SI GB (10**9), NOT GiB, and it is SPLIT across the
#     device pools (kv + mamba) proportionally to their device byte sizes
#     (``hybrid_pool_assembler._split_hicache_size``).  For this hybrid model the
#     kv pool receives ~0.165 of the requested GB, i.e. ~9952 kv-host tokens per
#     ``--hicache-size`` GB.  Two measured anchors on this rig/tree:
#         --hicache-size 2  -> "kv hierarchical KV host pool:  19904 tokens, 0.33 GB"
#         --hicache-size 32 -> "kv hierarchical KV host pool: 318457 tokens, 5.22 GB"
#     (318457/32 == 19904/2 == 9952.0 tokens/GB; 16384 B/token.)
#
# HiCache write-back is device -> host -> storage: the graded prompt must first
# be RESIDENT IN THE HOST POOL to be backed up.  A host pool smaller than the
# prompt can only DROP the subtree ("dropped without backup due to host memory
# pressure") and never reaches L3.  So the host pool must be >= prompt + margin,
# yet small enough that unrelated filler prefixes still evict the target to L3.
#
HICACHE_BYTES_PER_TOKEN = 16384          # 16 KiB/token (fp8_e4m3 KV)
HICACHE_KV_TOKENS_PER_GB = 9952.0        # measured kv-host tokens per SI GB
HICACHE_DEVICE_POOL_TOKENS = 65536       # --max-total-tokens


def kv_host_tokens_for_gb(hc_size_gb: float) -> int:
    """Predicted kv host-pool tokens for a ``--hicache-size`` value (SI GB)."""
    return int(round(float(hc_size_gb) * HICACHE_KV_TOKENS_PER_GB))


def kv_host_gb_for_tokens(tokens: float) -> float:
    return float(tokens) * HICACHE_BYTES_PER_TOKEN / 1e9


def min_hc_size_gb_for_tokens(tokens: float) -> int:
    return int(math.ceil(float(tokens) / HICACHE_KV_TOKENS_PER_GB))


def sizing_arithmetic(hc_size_gb: float, prompt_tokens: int,
                      host_pool_margin: int) -> dict:
    """Justification record for the chosen host-pool size (FIX 1)."""
    predicted = kv_host_tokens_for_gb(hc_size_gb)
    need = int(prompt_tokens) + int(host_pool_margin)
    return {
        "prompt_tokens": int(prompt_tokens),
        "host_pool_margin_tokens": int(host_pool_margin),
        "required_kv_host_tokens": need,
        "chosen_hicache_size_gb_SI": float(hc_size_gb),
        "predicted_kv_host_tokens": predicted,
        "predicted_kv_host_gb": round(kv_host_gb_for_tokens(predicted), 3),
        "bytes_per_token": HICACHE_BYTES_PER_TOKEN,
        "kv_host_tokens_per_GB": HICACHE_KV_TOKENS_PER_GB,
        "min_hicache_size_gb_for_required": min_hc_size_gb_for_tokens(need),
        "device_pool_tokens": HICACHE_DEVICE_POOL_TOKENS,
        "why_forces_L3": (
            "kv host pool >= graded prompt + margin, so the prompt is staged "
            "into host memory and written back to the extent store (instead of "
            "being dropped without backup); it remains far below production "
            "(perf profile L2=32GB) and far below one graded prompt's worth of "
            "filler, so unrelated filler prefixes still evict the target out of "
            "L2 and force a storage restore."),
    }

# Exit-code table (rc=0 <=> every REQUIRED gate executed AND passed).
VERDICT_EXIT = {"PASS": 0, "FAIL": 1, "INVALID": 2, "PENDING": 3,
                "ERROR": 4, "BLOCKED": 5}


class GateBlocked(Exception):
    """External input missing (tree/model/namespace unwritable)."""


class GateInvalid(Exception):
    """A precondition that makes the requested conclusion unestablishable."""


# --------------------------------------------------------------------- logging
def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write_json(path, obj) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    os.replace(tmp, path)


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def sha256_file(path, chunk=16 << 20):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def utcstamp():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def run_id(gate: str) -> str:
    return os.environ.get("SGLANG_GATE_RUN_ID",
                          f"{gate}-{utcstamp()}-{os.getpid()}")


def resolve_python(tree: str) -> str:
    env_py = os.path.join(tree, "env", "bin", "python")
    if os.path.exists(env_py):
        return env_py
    override = os.environ.get("SGLANG_GATE_PYTHON")
    if override:
        return override
    return sys.executable


def preflight_import(tree: str, timeout: float = 600.0) -> dict:
    """Import sglang in the tree's interpreter and assert the binding.

    Guards the editable-install landmine: without PYTHONPATH the venv can
    resolve ``import sglang`` to a stale workspace copy instead of the tree
    under test.
    """
    tree = tree.rstrip("/")
    python = resolve_python(tree)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": os.path.join(tree, "src", "python"),
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    code = ("import json, sglang; "
            "print(json.dumps({'sglang_file': sglang.__file__}))")
    try:
        proc = subprocess.run([python, "-c", code], cwd="/tmp", env=env,
                              capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc), "tree": tree}
    path = ""
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        path = json.loads(lines[-1]).get("sglang_file", "")
    except Exception:  # noqa: BLE001
        path = ""
    expected = os.path.join(tree, "src") + os.sep
    return {"ok": proc.returncode == 0 and path.startswith(expected),
            "sglang_file": path, "expected_prefix": expected,
            "returncode": proc.returncode,
            "stderr": proc.stderr[-500:]}


# ------------------------------------------------------------------ gate state
class Gate:
    """Fail-closed check registry.

    ``check`` marks a required check executed.  ``skip`` marks a required check
    NOT executed -> the verdict can never be PASS.  ``invalidate`` records a
    precondition failure (storage-tier proof absent, restart not genuine, ...)
    which is reported as INVALID, distinct from a content FAIL.
    """

    def __init__(self, name: str, run_dir=None, extra=None):
        self.name = name
        self.run_dir = pathlib.Path(run_dir or RUN_DIR)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.checks: dict = {}
        self.required: set = set()
        self.invalid_reason = None
        self.fail_reason = None
        self.pending_reason = None
        self.blocked_reason = None
        self.driver_error = None
        self.report: dict = {"gate": name, "task": TASK_ID,
                             "started": time.time()}
        if extra:
            self.report.update(extra)
        self._log_path = self.run_dir / f"{name}.log"

    # -- logging ----------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(self._log_path, "a") as fh:
            fh.write(line + "\n")

    # -- checks -----------------------------------------------------------
    def require(self, *names: str):
        """Mark check names required; they must later execute AND pass."""
        self.required.update(names)
        return self

    def check(self, name: str, ok: bool, detail=None) -> bool:
        self.checks[name] = {"executed": True, "ok": bool(ok),
                             "detail": detail}
        self.required.add(name)
        self.log(f"  check {name}: {'OK' if ok else 'FAIL'}"
                 + ("" if detail is None else f" :: {detail}"))
        return bool(ok)

    def record(self, name: str, value):
        """Non-required evidence (executed, never gates the verdict)."""
        self.checks[name] = {"executed": True, "ok": True,
                             "optional": True, "detail": value}
        return value

    def skip(self, name: str, reason: str) -> None:
        self.checks[name] = {"executed": False, "ok": False,
                             "detail": reason}
        self.required.add(name)
        self.log(f"  check {name}: SKIPPED :: {reason}")

    def invalidate(self, reason: str) -> None:
        if self.invalid_reason is None:
            self.invalid_reason = reason
        self.log(f"  INVALID :: {reason}")

    def fail(self, reason: str) -> None:
        if self.fail_reason is None:
            self.fail_reason = reason
        self.log(f"  FAIL :: {reason}")

    def pending(self, reason: str) -> None:
        self.pending_reason = reason
        self.log(f"  PENDING :: {reason}")

    def blocked(self, reason: str) -> None:
        self.blocked_reason = reason
        self.log(f"  BLOCKED :: {reason}")

    def error(self, exc, tb: str) -> None:
        self.driver_error = {"error": repr(exc), "traceback": tb}
        self.log(f"  DRIVER ERROR :: {exc!r}")

    # -- verdict ----------------------------------------------------------
    def finish(self):
        missing = [n for n in sorted(self.required)
                   if not self.checks.get(n, {}).get("executed")]
        failed = [n for n in sorted(self.required)
                  if self.checks.get(n, {}).get("executed")
                  and not self.checks.get(n, {}).get("ok")]
        if self.pending_reason is not None:
            verdict = "PENDING"
        elif self.blocked_reason is not None:
            verdict = "BLOCKED"
        elif self.driver_error is not None:
            verdict = "ERROR"
        elif self.invalid_reason is not None:
            verdict = "INVALID"
        elif missing:
            verdict = "INVALID"
            self.invalid_reason = (
                f"required check(s) never executed: {missing}")
        elif self.fail_reason is not None:
            verdict = "FAIL"
        elif failed:
            verdict = "FAIL"
            if self.fail_reason is None:
                self.fail_reason = f"required check(s) failed: {failed}"
        else:
            verdict = "PASS"
        rc = VERDICT_EXIT[verdict]
        self.report.update({
            "verdict": verdict, "exit_code": rc, "checks": self.checks,
            "finished": time.time(),
            "required": sorted(self.required),
        })
        for key, val in (("invalid_reason", self.invalid_reason),
                         ("fail_reason", self.fail_reason),
                         ("pending_reason", self.pending_reason),
                         ("blocked_reason", self.blocked_reason),
                         ("driver_error", self.driver_error)):
            if val is not None:
                self.report[key] = val
        return verdict, rc

    def save(self, name: str = "result.json"):
        path = self.run_dir / name
        write_json(path, self.report)
        self.log(f"wrote {path}")
        return path


# ------------------------------------------------------------------- lock
def acquire_lock(owner: str, max_attempts: int = 240, poll_s: int = 15,
                 lock_path: str = LOCK_PATH):
    """Take the canonical GPU lock once, in THIS process.

    Returns an int fd on success, None on bounded-window timeout.  The fd is
    ``O_CLOEXEC`` so a launched server can never inherit it; callers must also
    launch children with ``close_fds=True`` (the default).
    """
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    for attempt in range(1, max_attempts + 1):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            cur = ""
            try:
                with open(lock_path, "r", errors="replace") as fh:
                    cur = fh.read().strip()
            except OSError:
                pass
            log(f"lock busy (attempt {attempt}/{max_attempts}) holder={cur!r}")
            if attempt == max_attempts:
                os.close(fd)
                return None
            time.sleep(poll_s)
            continue
        # Read the previous generation AFTER we own the lock, so a clean
        # acquire/release/acquire sequence always advances it.
        prev = ""
        try:
            with open(lock_path, "r", errors="replace") as fh:
                prev = fh.read().strip()
        except OSError:
            pass
        try:
            gen = int(json.loads(prev.splitlines()[-1]).get("generation", 0)) + 1
        except Exception:
            gen = 1
        rec = {"owner": owner, "pid": os.getpid(), "generation": gen,
               "acquired": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        os.ftruncate(fd, 0)
        os.pwrite(fd, (json.dumps(rec) + "\n").encode(), 0)
        os.fsync(fd)
        log(f"canonical GPU lock ACQUIRED generation={gen} owner={owner} pid={os.getpid()}")
        return fd
    return None


def release_lock(fd) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def lock_probe(lock_path: str = LOCK_PATH, timeout: float = 60.0) -> dict:
    """Spawn a FRESH process (no inherited fd) that tries to take the lock.

    ``locked=True`` means the lock is held by someone else.  Used to prove the
    driver -- not a server it launched -- owns the lock generation.
    """
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "lock_probe.py"), lock_path],
        capture_output=True, text=True, timeout=timeout, env=env,
        cwd="/tmp", close_fds=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        out = json.loads(lines[-1])
    except Exception:
        out = {"locked": None, "rc": proc.returncode,
               "stdout": proc.stdout[-500:], "stderr": proc.stderr[-500:]}
    out.setdefault("probe_pid", None)
    out.setdefault("rc", proc.returncode)
    return out


def proc_fd_targets(pid) -> list:
    d = f"/proc/{pid}/fd"
    out = []
    try:
        for fd in sorted(os.listdir(d), key=lambda x: (len(x), x)):
            try:
                out.append(os.readlink(os.path.join(d, fd)))
            except OSError:
                continue
    except OSError:
        return []
    return out


def proc_holds_lock(pid, lock_path: str = LOCK_PATH) -> bool:
    real = os.path.realpath(lock_path)
    for tgt in proc_fd_targets(pid):
        try:
            if os.path.realpath(tgt) == real:
                return True
        except OSError:
            continue
    return False


def proc_env(pid) -> dict:
    try:
        raw = pathlib.Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    out = {}
    for kv in raw.decode("utf-8", "replace").split("\0"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out


def proc_starttime(pid):
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text()
        # field 22 (1-indexed) after the comm field which may contain spaces
        rest = stat[stat.rindex(")") + 2:].split()
        return int(rest[19])
    except Exception:
        return None


def wait_proc_gone(pid, timeout_s: float = 120.0) -> bool:
    """Block until ``/proc/<pid>`` is gone (FIX 3: process fully terminated)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not os.path.exists(f"/proc/{pid}"):
            return True
        time.sleep(1.0)
    return not os.path.exists(f"/proc/{pid}")


# ------------------------------------------------------------------- ports
def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def wait_port_free(port: int, timeout_s: float = 300.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if port_free(port):
            return True
        time.sleep(3)
    return port_free(port)


# ------------------------------------------------------------------ http
def http_json(method: str, url: str, payload=None, timeout: float = 600.0):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def api_get(port: int, path: str, timeout: float = 240.0) -> str:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def api_post(port: int, path: str, timeout: float = 240.0) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def api_get_verbose(port: int, path: str, timeout: float = 240.0) -> dict:
    """GET returning ``{status, body, error}`` instead of raising.

    A non-2xx response is captured with its status so callers can make a
    fail-closed decision instead of stringifying an exception.
    """
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"status": int(getattr(r, "status", 200)), "error": None,
                    "body": r.read().decode("utf-8", "replace")}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        return {"status": int(exc.code), "body": body, "error": repr(exc),
                "http_error": True}
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "body": "", "error": repr(exc)}


def flush_cache_strict(port: int, timeout_s: float = 240.0,
                       attempts: int = 3, idle_timeout: float = 300.0) -> dict:
    """Execute ``/flush_cache`` and accept ONLY a confirmed success.

    FIX 4: the predecessor recorded ``HTTPError 400`` (and the console's
    ``Deferred flush_cache timed out while waiting for idle state``) as OK, so
    the cold-L1 precondition never executed and the gate still measured.  Here
    success requires HTTP 200 AND the ``Cache flushed`` body; every other
    outcome (non-2xx, timeout, empty body, request error) is a failure and the
    caller must return INVALID without issuing the measured request.
    """
    out = {"attempts": 0, "idle": False, "status": None, "body": "",
           "error": None, "ok": False}
    if not wait_idle(port, idle_timeout):
        out["error"] = "server never reached idle before /flush_cache"
        return out
    out["idle"] = True
    for _ in range(max(1, int(attempts))):
        out["attempts"] += 1
        r = api_get_verbose(port, f"/flush_cache?timeout={int(timeout_s)}",
                            timeout_s + 60.0)
        out["status"] = r.get("status")
        out["body"] = (r.get("body") or "")[:400]
        out["error"] = r.get("error")
        if r.get("status") == 200 and "cache flushed" in out["body"].lower():
            out["ok"] = True
            return out
        # a deferred flush that timed out leaves the server idle again; retry.
        if not wait_idle(port, min(120.0, idle_timeout)):
            break
    if not out["ok"]:
        out["error"] = out["error"] or (
            f"flush_cache not confirmed: status={out['status']} "
            f"body={out['body']!r}")
    return out


def generate(port: int, input_ids, max_new: int, seed: int = SEED,
             ignore_eos: bool = True, timeout: float = 3600.0) -> dict:
    """Greedy /generate with explicit pinned sampling (fail-closed).

    The prompt is already chat-template rendered with enable_thinking=false, so
    the SamplingParams surface never sees a chat-only kwarg.  ``sampling_seed``
    is the SamplingParams field (the predecessor used the wrong ``seed``).
    """
    payload = {
        "input_ids": [int(t) for t in input_ids],
        "sampling_params": {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "sampling_seed": int(seed),
            "max_new_tokens": int(max_new),
            "ignore_eos": bool(ignore_eos),
        },
    }
    t0 = time.perf_counter()
    try:
        d = http_json("POST", f"http://127.0.0.1:{port}/generate",
                      payload, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc),
                "seconds": time.perf_counter() - t0,
                "output_ids": None, "meta": None}
    oids = d.get("output_ids")
    if oids and isinstance(oids[0], list):
        oids = oids[0]
    meta = d.get("meta_info") or {}
    return {
        "ok": d.get("error") is None and oids is not None,
        "error": d.get("error"),
        "seconds": time.perf_counter() - t0,
        "output_ids": list(oids) if oids is not None else None,
        "meta": meta,
        "tier": tier_of(meta),
    }


def tier_of(meta: dict) -> dict:
    meta = meta or {}
    det = meta.get("cached_tokens_details") or {}
    tel = meta.get("hicache_telemetry") or {}
    return {
        "device": int(det.get("device") or 0),
        "host": int(det.get("host") or 0),
        "storage": int(det.get("storage") or 0),
        "storage_backend": det.get("storage_backend"),
        "l1_tokens": tel.get("l1_tokens"),
        "l2_tokens": tel.get("l2_tokens"),
        "l3_tokens": tel.get("l3_tokens"),
        "prefetch_origin": tel.get("prefetch_origin"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "completion_tokens": meta.get("completion_tokens"),
        "has_cached_tokens_details": bool(det),
        "has_hicache_telemetry": bool(tel),
    }


def ensure_ok(gate, resp: dict, label: str) -> bool:
    """Fail-closed guard: a request that did not execute is INVALID, not FAIL."""
    if not resp.get("ok"):
        gate.invalidate(f"{label}: /generate failed: {resp.get('error')!r}")
        return False
    if not resp.get("output_ids"):
        gate.invalidate(f"{label}: /generate returned no output_ids")
        return False
    return True


# --------------------------------------------------------------- console scan
_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")


def parse_kv(line: str) -> dict:
    return {k: v for k, v in _KV_RE.findall(line)}


def console_size(path) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def read_new_lines(path, offset: int):
    try:
        with open(path, "r", errors="replace") as fh:
            fh.seek(offset)
            return fh.readlines()
    except OSError:
        return []


def parse_storage_events(lines) -> dict:
    ev = {
        "prefetch_revoke": [], "restore_success": [], "restore_recompute": [],
        "restore_disposition": [], "extent_write": [], "extent_recycle": [],
        "kv_gate": [], "reclaim_relocated": [], "reclaim_refused": [],
        "dropped_no_backup": [], "dropped_scopes": [],
        "restore_backup": [], "match_anchor": [],
    }
    for ln in lines:
        if "evt=prefetch_revoke" in ln:
            ev["prefetch_revoke"].append(parse_kv(ln))
        elif "evt=restore_success" in ln:
            ev["restore_success"].append(parse_kv(ln))
        elif "evt=restore_recompute" in ln:
            ev["restore_recompute"].append(parse_kv(ln))
        elif "evt=restore_disposition" in ln:
            ev["restore_disposition"].append(parse_kv(ln))
        elif "evt=restore_backup" in ln:
            ev["restore_backup"].append(parse_kv(ln))
        elif "evt=rh_match_prepare" in ln:
            ev["match_anchor"].append(parse_kv(ln))
        elif "evt=extent_write" in ln:
            ev["extent_write"].append(parse_kv(ln))
        elif "evt=extent_recycle" in ln:
            ev["extent_recycle"].append(parse_kv(ln))
        elif "KV Cache is allocated. dtype:" in ln:
            ev["kv_gate"].append(ln)
        elif "reclaim relocated" in ln:
            ev["reclaim_relocated"].append(parse_reclaim_line(ln))
        elif "reclaim relocation" in ln and "refused" in ln:
            ev["reclaim_refused"].append(parse_reclaim_line(ln))
        elif _DROP_MARKER in ln:
            ev["dropped_no_backup"].append(ln.rstrip("\n"))
            ev["dropped_scopes"].append(parse_drop_no_backup(ln))
    return ev


def extent_write_bytes(events) -> int:
    total = 0
    for rec in events.get("extent_write", []):
        try:
            total += int(rec.get("bytes", 0))
        except (TypeError, ValueError):
            continue
    return total


def slim_storage_events(events, n: int = 6) -> dict:
    def tail(rows, k=None):
        return rows[-(k if k is not None else n):]
    drop_scopes = events.get("dropped_scopes")
    if drop_scopes is None:
        drop_scopes = [parse_drop_no_backup(l)
                       for l in events.get("dropped_no_backup", [])]
    return {
        "prefetch_revoke": tail(events.get("prefetch_revoke", [])),
        "restore_success": tail(events.get("restore_success", [])),
        "restore_recompute": tail(events.get("restore_recompute", [])),
        "restore_disposition": tail(events.get("restore_disposition", [])),
        "restore_backup_n": len(events.get("restore_backup", [])),
        "match_anchor_n": len(events.get("match_anchor", [])),
        "extent_recycle": tail(events.get("extent_recycle", [])),
        "extent_write_n": len(events.get("extent_write", [])),
        "extent_recycle_n": len(events.get("extent_recycle", [])),
        "extent_write_bytes": extent_write_bytes(events),
        "reclaim_relocated_n": len(events.get("reclaim_relocated", [])),
        "reclaim_refused_n": len(events.get("reclaim_refused", [])),
        "reclaim_relocated": tail(events.get("reclaim_relocated", [])),
        "reclaim_refused": tail(events.get("reclaim_refused", [])),
        "dropped_no_backup_n": len(events.get("dropped_no_backup", [])),
        "dropped_no_backup": tail(events.get("dropped_no_backup", []), 3),
        # Raw subtree roots only: the target-scoped verdict needs the target
        # node evidence and the offline refs verdict, which the callers supply.
        "dropped_roots": [d.get("root_id") for d in drop_scopes][-6:],
    }


def revoke_miss(events) -> bool:
    """True iff a storage query explicitly reported a zero-hit miss."""
    for rec in events.get("prefetch_revoke", []):
        try:
            if int(rec.get("storage_hit", -1)) == 0 and \
                    rec.get("miss_reason") == "miss":
                return True
        except (TypeError, ValueError):
            continue
    return False


def max_restore_n_tokens(events) -> int:
    best = 0
    for rec in events.get("restore_success", []):
        try:
            best = max(best, int(rec.get("n_tokens", 0)))
        except (TypeError, ValueError):
            continue
    return best


def revoke_storage_hit(events):
    """Last observed prefetch_revoke.storage_hit, or None."""
    best = None
    for rec in events.get("prefetch_revoke", []):
        try:
            best = int(rec.get("storage_hit"))
        except (TypeError, ValueError):
            continue
    return best


# ------------------------------------- target-scoped "dropped without backup"
#
# The product logs one of two shapes when a write-back cannot be backed up and
# the device/host copy is dropped:
#   unified_radix_cache: "write_back: KV subtree dropped without backup due to
#       host memory pressure, root node 123"
#   hiradix_cache:       "write_back: KV cache on device are dropped without
#       backup due to host memory pressure, subtree root 123, num_nodes 456"
#
# Treating ANY such line as a graded-target failure is wrong (unrelated filler
# subtrees are disposable), but treating a target drop as foreign is a false
# PASS.  The ONLY sound classification input available offline is a positive
# DELTA proof that the target's durable ref set did not shrink across the drop:
# compare the target's extent-index membership BEFORE the drop(s) with the
# membership AFTER, using monotone set proxies (present/absent counts, leading
# absent position, run count, longest run).  No decrease => the drop removed no
# durable ref => foreign.  Any decrease, or no usable pre-drop baseline, =>
# fail closed: target/unknown => INVALID.
#
# There is deliberately NO node-id ordering rule.  The previously assumed
# invariant ("a parent is allocated before its children, so a subtree rooted at
# R contains only node ids >= R") is FALSE in the tree under test:
# ``python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py``
# ``_split_node`` (:1126-1160) allocates a NEW, higher-id node and makes it the
# PARENT of the pre-existing, OLDER, lower-id child.  A drop rooted at such a
# split parent has an id above the observed maximum target node id while its
# subtree still contains a lower-id target descendant.  ``root_id`` is retained
# as record-only evidence (``target_node_evidence``) and must never gate a
# foreign verdict.
_DROP_MARKER = "without backup due to host memory pressure"
_RE_DROP_HIRADIX = re.compile(
    r"dropped without backup due to host memory pressure, subtree root (\d+), "
    r"num_nodes (\d+)")
_RE_DROP_UNIFIED = re.compile(
    r"dropped without backup due to host memory pressure, root node (\d+)")


def parse_drop_no_backup(line: str) -> dict:
    """Parse a dropped-without-backup line into its subtree root id.

    ``root_id`` is None when the line carries no parsable subtree root, so
    callers must fail closed (classify as unknown), never as foreign.
    """
    m = _RE_DROP_HIRADIX.search(line)
    if m:
        return {"root_id": int(m.group(1)), "num_nodes": int(m.group(2)),
                "format": "hiradix", "line": line.rstrip("\n")}
    m = _RE_DROP_UNIFIED.search(line)
    if m:
        return {"root_id": int(m.group(1)), "num_nodes": None,
                "format": "unified", "line": line.rstrip("\n")}
    return {"root_id": None, "num_nodes": None, "format": "unparsed",
            "line": line.rstrip("\n")}


def target_node_evidence(events, target_len: int) -> dict:
    """Best-effort node-id REPORT for the graded target (console only).

    REPORTING ONLY -- this is never a classification input; see ``DropScope``.
    ``node_ids``/``max_node_id`` are recorded for human review and for spotting
    an implausible drop root; they must not route a drop to ``foreign`` because
    the parent/child id ordering they would rely on is false (``_split_node``).

    ``durable_nodes`` are the ``restore_backup`` nodes at or below the maximum
    ``rh_match_prepare`` anchor whose ``fill_len`` equals the target length.
    """
    anchors = []
    for rec in events.get("match_anchor", []):
        try:
            if int(rec.get("fill_len", -1)) == int(target_len):
                anchors.append(int(rec.get("anchor_id")))
        except (TypeError, ValueError):
            continue
    anchors = sorted(set(anchors))
    max_anchor = anchors[-1] if anchors else None
    durable = []
    for rec in events.get("restore_backup", []):
        tok = rec.get("node")
        if tok in (None, "", "None"):
            continue
        try:
            n = int(tok)
        except (TypeError, ValueError):
            continue
        if max_anchor is not None and n <= max_anchor:
            durable.append(n)
    durable = sorted(set(durable))
    node_ids = sorted(set(anchors) | set(durable))
    return {
        "target_len": int(target_len),
        "anchors": anchors,
        "max_anchor": max_anchor,
        "durable_nodes": durable,
        "node_ids": node_ids,
        "max_node_id": (max(node_ids) if node_ids else None),
        "has_evidence": bool(node_ids),
    }


def _as_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_absent(mem):
    """Leading-absent position; ``None`` means "no absent page in the window"."""
    raw = mem.get("first_absent_index")
    return None if raw is None else _as_int(raw)


_DELTA_PROXIES = ("n_present", "n_absent", "first_absent_index", "n_runs",
                  "longest_run_len")


def _missing_delta_proxies(mem) -> list:
    """Proxy keys absent from a membership snapshot (L4: missing => unknown).

    A snapshot that simply omits a proxy must never be compared as if that
    proxy were unchanged; the caller cannot prove anything about it.
    """
    if not mem:
        return list(_DELTA_PROXIES)
    return [k for k in _DELTA_PROXIES if k not in mem]


def baseline_is_complete(mem) -> bool:
    """True only when a membership snapshot covers the FULL target window.

    The positive delta proof is only sound against a COMPLETE baseline.  A
    partial snapshot has an unpersisted region; pages in it can become durable
    after the snapshot and later be dropped (or their drop can be offset by
    concurrent growth), which the aggregate proxies cannot observe.  Such a
    baseline can therefore never justify a FOREIGN verdict -- the caller must
    fail closed (``unknown`` -> INVALID).

    Complete means: every proxy present, ``n_present > 0``, ``n_absent == 0``,
    no ``first_absent_index``, a single run whose length equals ``n_present``,
    and (when the window length is known) ``n_present >= query_window_len``.
    """
    if not mem or _missing_delta_proxies(mem):
        return False
    n_present = _as_int(mem.get("n_present"))
    n_absent = _as_int(mem.get("n_absent"))
    if n_present is None or n_present <= 0 or n_absent != 0:
        return False
    if mem.get("first_absent_index") is not None:
        return False
    n_runs = _as_int(mem.get("n_runs"))
    longest = _as_int(mem.get("longest_run_len"))
    if n_runs != 1 or longest is None or longest < n_present:
        return False
    window = _as_int(mem.get("query_window_len"))
    if window is not None and n_present < window:
        return False
    return True


def durable_delta_status(baseline, now, require_complete_baseline=True) -> str:
    """Positive delta proof that a drop removed no graded-target durable ref.

    ``baseline`` is a membership snapshot taken while NO dropped-without-backup
    event was in the console window (the pre-drop durable state) and ``now`` is
    the post-drop snapshot, both for the same query window.  Returns
    ``"intact"`` (provably no decrease), ``"lost"`` (provably decreased) or
    ``"unknown"`` (cannot prove either -> the caller fails closed).

    Two soundness requirements bound ``"intact"``:

    * **Complete baseline.**  With ``require_complete_baseline=True`` (the
      default, and what every call site uses) the baseline must pass
      :func:`baseline_is_complete`.  A partial baseline is ``unknown``: a page
      that became durable after the snapshot can be dropped, and the drop can
      also be masked by concurrent growth/backfill, neither of which the
      aggregate proxies can see (D1).
    * **All proxies present (L4).**  A snapshot missing any of ``n_present``,
      ``n_absent``, ``first_absent_index``, ``n_runs``, ``longest_run_len`` is
      ``unknown``; an omitted proxy is never treated as unchanged.

    The set proxies are monotone: ``n_present`` (must not fall), ``n_absent``
    (must not rise), ``first_absent_index`` (must not move earlier; ``None`` is
    the best value), ``n_runs`` (must not rise: a new hole splits a run) and
    ``longest_run_len`` (must not fall).
    """
    if not baseline or not now:
        return "unknown"
    if _missing_delta_proxies(baseline) or _missing_delta_proxies(now):
        return "unknown"
    if require_complete_baseline and not baseline_is_complete(baseline):
        return "unknown"
    bl_n = _as_int(baseline.get("n_present"))
    nw_n = _as_int(now.get("n_present"))
    if bl_n is None or nw_n is None or bl_n <= 0:
        return "unknown"
    # positive LOSS proofs
    if nw_n < bl_n:
        return "lost"
    bl_a, nw_a = _as_int(baseline.get("n_absent")), _as_int(now.get("n_absent"))
    if bl_a is not None and nw_a is not None and nw_a > bl_a:
        return "lost"
    bl_f, nw_f = _first_absent(baseline), _first_absent(now)
    if bl_f is None:
        if nw_f is not None:
            return "lost"
    elif nw_f is None or nw_f < bl_f:
        return "lost"
    bl_r, nw_r = _as_int(baseline.get("n_runs")), _as_int(now.get("n_runs"))
    if bl_r is not None and nw_r is not None and nw_r > bl_r:
        return "lost"
    bl_l = _as_int(baseline.get("longest_run_len"))
    nw_l = _as_int(now.get("longest_run_len"))
    if bl_l is not None and nw_l is not None and nw_l < bl_l:
        return "lost"
    return "intact"


def delta_status_with_rechecks(baseline, snapshots) -> str:
    """Worst-case no-decrease verdict across a baseline and re-snapshots.

    ``snapshots`` are consecutive post-drop membership snapshots, the first
    taken immediately after the drop lines and each further one a re-snapshot
    consumed before the verdict is final (D1(ii): a drop cannot hide between
    snapshots).  Any ``lost`` dominates; ``intact`` requires every snapshot to
    be ``intact``; a missing/unknown snapshot forces ``unknown`` (fail closed).
    """
    statuses = [durable_delta_status(baseline, s)
                for s in (snapshots or [])]
    if not statuses:
        return "unknown"
    if any(s == "lost" for s in statuses):
        return "lost"
    if all(s == "intact" for s in statuses):
        return "intact"
    return "unknown"


def combine_delta_status(statuses):
    """Combine per-target delta verdicts into ``True``/``False``/``None``.

    Any ``lost`` -> ``False`` (a target lost durable refs).  All ``intact``
    (and at least one) -> ``True``.  Anything else (missing/unknown) -> ``None``
    so the caller fails closed.
    """
    statuses = [s for s in statuses if s is not None]
    if not statuses:
        return None
    if any(s == "lost" for s in statuses):
        return False
    if all(s == "intact" for s in statuses):
        return True
    return None


class DropScope:
    """Classify a dropped-without-backup event against the graded target.

    The ONLY classification input is ``refs_intact``, the positive delta proof
    produced by :func:`durable_delta_status`/:func:`combine_delta_status`:

      * ``False`` -- the delta proves target durable refs were lost -> ``target``
        (INVALID);
      * ``True``  -- the delta positively proves no target durable ref was
        removed, measured against a COMPLETE baseline (see
        :func:`baseline_is_complete`) and confirmed by every re-snapshot
        -> ``foreign`` (the dropped copy was redundant; a filler drop is
        disposable);
      * ``None``  -- not established -> ``unknown`` -> INVALID (fail closed).

    ``root_id`` is accepted for recording only.  The node-id ordering bound was
    removed because its invariant is false (see the module block above); it must
    not steer a drop to ``foreign``.
    """

    TARGET = "target"
    FOREIGN = "foreign"
    UNKNOWN = "unknown"

    def __init__(self, refs_intact=None):
        self.refs_intact = refs_intact

    def classify(self, root_id=None) -> str:  # noqa: ARG002 (record-only)
        if self.refs_intact is False:
            return self.TARGET
        if self.refs_intact is True:
            return self.FOREIGN
        return self.UNKNOWN


def scope_drop_events(events, evidence=None, refs_intact=None) -> list:
    """Classify every dropped-without-backup event in ``events``.

    ``evidence`` (:func:`target_node_evidence`) is attached to each row for
    reporting but does NOT influence the verdict -- only ``refs_intact`` does.
    """
    evidence = evidence or {}
    scope = DropScope(refs_intact)
    raw = events.get("dropped_scopes")
    if raw is None:
        raw = [parse_drop_no_backup(l)
               for l in events.get("dropped_no_backup", [])]
    out = []
    for rec in raw:
        rec = dict(rec)
        rec["scope"] = scope.classify(rec.get("root_id"))
        rec["refs_intact"] = refs_intact
        rec["target_evidence"] = {
            "max_node_id": evidence.get("max_node_id"),
            "anchors": evidence.get("anchors"),
        }
        out.append(rec)
    return out


def drop_scope_ok(scoped) -> dict:
    """Fail-closed summary: ok only when every drop is provably FOREIGN.

    Only an explicit ``scope == FOREIGN`` counts as disposable.  Any other row
    -- ``target``, ``unknown``, or a row with a missing/unrecognised ``scope``
    key -- is fail-closed, so the caller returns INVALID (never FAIL/PASS).
    """
    foreign, target, unknown = [], [], []
    for d in scoped or []:
        s = d.get("scope")
        if s == DropScope.FOREIGN:
            foreign.append(d)
        elif s == DropScope.TARGET:
            target.append(d)
        else:
            unknown.append(d)
    return {
        "n_total": len(scoped or []),
        "n_foreign": len(foreign),
        "n_target": len(target),
        "n_unknown": len(unknown),
        # an EMPTY event list is vacuously ok (no drop events at all); a
        # non-empty list is ok only when every row is explicitly FOREIGN.
        "ok": not target and not unknown,
        "target_roots": [d.get("root_id") for d in target],
        "unknown_roots": [d.get("root_id") for d in unknown],
    }


def relocation_reserve_check(detail, reserve_bytes=0) -> dict:
    """Preflight for the F1 circular-reclaim relocation destination.

    ``detail`` is the offline victim slot detail produced by
    ``wal_forensics.py`` (``live_bytes``, ``target_live_refs``,
    ``relocation_headroom_bytes``, ``reclaim_relocatable``).  A 100%-live store
    with no destination capacity outside the victim is the product's EXPECTED
    fail-closed backpressure: it is INVALID geometry for a relocation-success
    measurement, never PASS/FAIL.  ``reserve_bytes`` is a caller-supplied
    minimum destination size (default 0 => the victim's own live bytes).
    """
    detail = detail or {}
    live = int(detail.get("live_bytes") or 0)
    headroom = int(detail.get("relocation_headroom_bytes") or 0)
    target_refs = int(detail.get("target_live_refs") or 0)
    required = max(live, int(reserve_bytes or 0))
    holds_target = target_refs > 0
    reclaimable = bool(detail.get("reclaim_relocatable")) and live > 0
    destination_ok = headroom >= required and required > 0
    return {
        "victim_slot": detail.get("slot"),
        "live_bytes": live,
        "relocation_headroom_bytes": headroom,
        "reserve_bytes": int(reserve_bytes or 0),
        "required_destination_bytes": required,
        "target_live_refs": target_refs,
        "holds_target_live_refs": holds_target,
        "destination_capacity_exists": destination_ok,
        "reclaim_relocatable": reclaimable,
        "ok": bool(holds_target and destination_ok and reclaimable),
    }


def assert_preconditions(gate, label: str, checks) -> bool:
    """Record required pre-measurement checks; any failure -> INVALID.

    ``checks`` is an iterable of ``(name, ok)`` or ``(name, ok, detail)`` or
    ``(name, ok, detail, reason)``.  Every check is registered as required (so
    it shows in the report); the first failure invalidates (never fails), and
    the caller MUST withhold the measured request and return INVALID.
    """
    failed = []
    for item in checks:
        name, ok = item[0], bool(item[1])
        detail = item[2] if len(item) > 2 else None
        reason = item[3] if len(item) > 3 else None
        gate.check(name, ok, detail=detail)
        if not ok:
            failed.append((name, reason or name))
    if failed:
        gate.invalidate(
            f"{label}: precondition(s) not established -> INVALID before the "
            "measured request: "
            + "; ".join(f"{n} ({r})" for n, r in failed))
        return False
    return True


# ------------------------------------------------------------- reclaim events
_RE_LOCATED = re.compile(
    r"reclaim relocated (\d+) live refs out of victim slots "
    r"\[([0-9,\s]*)\]\s*\((\d+) bytes\)")
_RE_REFUSED = re.compile(
    r"reclaim relocation of (\d+) live refs refused: no destination "
    r"capacity outside victims \[([0-9,\s]*)\]")
_SLOT_LIST = re.compile(r"\d+")


def parse_reclaim_line(line: str) -> dict:
    """Parse a reclaim relocation / refusal log line (FIX 2 evidence)."""
    m = _RE_LOCATED.search(line)
    if m:
        return {"kind": "relocated", "live_refs": int(m.group(1)),
                "slots": [int(s) for s in _SLOT_LIST.findall(m.group(2))],
                "bytes": int(m.group(3)), "line": line.rstrip("\n")}
    m = _RE_REFUSED.search(line)
    if m:
        return {"kind": "refused", "live_refs": int(m.group(1)),
                "slots": [int(s) for s in _SLOT_LIST.findall(m.group(2))],
                "bytes": None, "line": line.rstrip("\n")}
    return {"kind": "unknown", "live_refs": None, "slots": [],
            "bytes": None, "line": line.rstrip("\n")}


def reclaim_events_for_slot(events, slot: int) -> dict:
    """Relocation / refusal events that name ``slot`` as a reclaim victim."""
    relocated = [r for r in events.get("reclaim_relocated", [])
                 if slot in (r.get("slots") or [])]
    refused = [r for r in events.get("reclaim_refused", [])
               if slot in (r.get("slots") or [])]
    recycle = []
    for r in events.get("extent_recycle", []):
        try:
            if int(r.get("slot", -1)) == int(slot):
                recycle.append(r)
        except (TypeError, ValueError):
            continue
    return {"relocated": relocated, "refused": refused, "recycle": recycle}


def reclaim_hits_for_slots(events, slots) -> list:
    """All reclaim/recycle events naming any slot in ``slots``.

    Returns a list of ``(kind, slot, record)`` in a stable order:
    relocated, refused, recycle.  Used by F1 to detect the circular cursor
    wrapping into a slot that holds live target refs without pre-committing to
    one victim slot.
    """
    want = {int(s) for s in slots}
    out = []
    for kind, key in (("relocated", "reclaim_relocated"),
                      ("refused", "reclaim_refused")):
        for rec in events.get(key, []):
            for s in (rec.get("slots") or []):
                if int(s) in want:
                    out.append((kind, int(s), rec))
    for rec in events.get("extent_recycle", []):
        try:
            s = int(rec.get("slot"))
        except (TypeError, ValueError):
            continue
        if s in want:
            out.append(("recycle", s, rec))
    return out


def extent_recycle_count(events) -> int:
    return len(events.get("extent_recycle", []))


# ------------------------------------------------------------- host pool sizing
_HOST_POOL_RE = re.compile(
    r"Allocating (\w+) hierarchical KV host pool: (\d+) tokens, "
    r"([\d.]+) GB host memory")
_HOST_POOL_WARN_RE = re.compile(
    r"HiCache .*pool \((\d+) tokens\) is smaller than the device pool "
    r"\((\d+) tokens\)")


def parse_host_pool(console_path, prompt_tokens=None,
                    host_pool_margin: int = 0) -> dict:
    """Read the *actual* host-pool token counts the server allocated.

    The size is the authoritative precondition for reaching L3: a kv host pool
    below the graded prompt can only DROP the write-back, so every measured arm
    would see ``storage == 0``.  Parsed from the server's own allocation line.
    """
    try:
        txt = pathlib.Path(console_path).read_text(errors="replace")
    except OSError:
        return {"ok": False, "reason": "console missing", "pools": {}}
    pools = {}
    for name, tok, gb in _HOST_POOL_RE.findall(txt):
        pools[name] = {"tokens": int(tok), "gb": float(gb)}
    warnings = []
    for tok, dev in _HOST_POOL_WARN_RE.findall(txt):
        warnings.append({"pool_tokens": int(tok), "device_tokens": int(dev)})
    kv = pools.get("kv")
    out = {"pools": pools, "smaller_than_device_warnings": warnings,
           "kv_tokens": kv["tokens"] if kv else None,
           "kv_gb": kv["gb"] if kv else None,
           "mamba_tokens": (pools.get("mamba") or {}).get("tokens"),
           "raw_lines": [ln for ln in txt.splitlines()
                         if "hierarchical KV host pool" in ln][-4:]}
    if prompt_tokens is None:
        out["ok"] = kv is not None
        return out
    need = int(prompt_tokens) + int(host_pool_margin)
    out.update({"prompt_tokens": int(prompt_tokens),
                "host_pool_margin_tokens": int(host_pool_margin),
                "required_kv_host_tokens": need,
                "kv_headroom_tokens": (kv["tokens"] - need) if kv else None})
    out["ok"] = kv is not None and kv["tokens"] >= need
    return out


# --------------------------------------------------------------- metrics log
def latest_metric(dirs, prompt_tokens=None, rid=None, timeout_s=120.0):
    """Last request-metrics record matching prompt_tokens and/or rid."""
    deadline = time.monotonic() + timeout_s
    while True:
        best = None
        for d in dirs:
            try:
                names = [os.path.join(d, f) for f in os.listdir(d)
                         if f.startswith("sglang-request-metrics-")
                         and f.endswith(".log")]
            except OSError:
                continue
            names.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for path in names[:3]:
                try:
                    with open(path, "r", errors="replace") as fh:
                        for line in fh:
                            if not line.startswith("{"):
                                continue
                            if prompt_tokens is not None and (
                                    f'"prompt_tokens": {int(prompt_tokens)}'
                                    not in line):
                                continue
                            if rid is not None and f'"{rid}"' not in line:
                                continue
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            if prompt_tokens is not None and \
                                    rec.get("prompt_tokens") != int(prompt_tokens):
                                continue
                            if rid is not None and rec.get("id") != rid:
                                continue
                            best = rec
                except OSError:
                    continue
        if best is not None or time.monotonic() >= deadline:
            return best
        time.sleep(2.0)


# --------------------------------------------------------------- prompts / wal
def build_prompt(tree: str, model: str, marker: str, target_len: int,
                 out_json, seed: int = SEED, timeout: float = 900.0) -> dict:
    python = resolve_python(tree)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": os.path.join(tree, "src", "python"),
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cmd = [python, str(HARNESS_DIR / "prompt_builder.py"),
           "--model", model, "--marker", marker,
           "--target-len", str(int(target_len)), "--seed", str(int(seed)),
           "--out", str(out_json)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=env, cwd="/tmp")
    if proc.returncode != 0:
        raise GateBlocked(
            f"prompt_builder rc={proc.returncode}: "
            f"{proc.stdout[-800:]}{proc.stderr[-800:]}")
    return read_json(out_json)


def wal_forensics(tree: str, namespace: str, suffix: str, mode: str, out_json,
                  ids_json=None, query_window_len=None, timeout: float = 1800.0,
                  victim_slot=None, victim_slot_auto: bool = False):
    python = resolve_python(tree)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": os.path.join(tree, "src", "python"),
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cmd = [python, str(HARNESS_DIR / "wal_forensics.py"),
           "--mode", mode, "--tree", tree, "--namespace", namespace,
           "--suffix", suffix, "--out", str(out_json)]
    if ids_json is not None:
        cmd += ["--ids-json", str(ids_json)]
    if query_window_len is not None:
        cmd += ["--query-window-len", str(int(query_window_len))]
    if victim_slot is not None:
        cmd += ["--victim-slot", str(int(victim_slot))]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=env, cwd="/tmp")
    if proc.returncode != 0:
        raise GateInvalid(
            f"wal_forensics[{mode}] rc={proc.returncode}: "
            f"{proc.stdout[-800:]}{proc.stderr[-800:]}")
    return read_json(out_json)


def snapshot_and_membership(tree: str, namespace: str, suffix: str,
                            snapshot_dir: str, out_json, ids_json,
                            query_window_len=None, victim_slot=None,
                            attempts: int = 4) -> tuple:
    """Copy the store's durable metadata, then replay membership offline.

    The copy is a point-in-time set of manifest + WAL segments, so it can be
    torn by a concurrent checkpoint rotation; retry the pair on replay failure.
    Read-only w.r.t. the live store (never a live-store replay).
    """
    last = None
    for i in range(max(1, attempts)):
        d = snapshot_dir if i == 0 else f"{snapshot_dir}.r{i}"
        try:
            copied = copy_store(namespace, d)
            out = wal_forensics(tree, d, suffix, "membership", out_json,
                                ids_json=ids_json,
                                query_window_len=query_window_len,
                                victim_slot=victim_slot)
            return out, {"snapshot": d, "files": copied, "attempts": i + 1}
        except (GateInvalid, GateBlocked) as exc:
            last = exc
            time.sleep(2.0)
            continue
        except OSError as exc:
            last = exc
            time.sleep(2.0)
            continue
    raise GateInvalid(f"store snapshot/membership failed after "
                      f"{attempts} attempts: {last}")


# --------------------------------------------------------------- namespaces
def resolve_namespace(base_root: str, gate: str, rid: str,
                      reuse: bool = False) -> str:
    """Return a fresh per-run namespace; never touch the shared prod store."""
    if os.environ.get("SGLANG_GATE_NAMESPACE_REUSE") == "1":
        reuse = True
    base = os.path.join(base_root, TASK_ID)
    ns = os.path.join(base, f"{gate}-{rid}")
    real_ns = os.path.realpath(ns)
    real_prod = os.path.realpath(PRODUCTION_STORE)
    if real_ns == real_prod or real_ns.startswith(real_prod + os.sep):
        raise GateInvalid(f"namespace resolves inside shared prod store: {ns}")
    if os.path.isdir(ns) and os.listdir(ns) and not reuse:
        raise GateInvalid(
            f"namespace already populated (refusing to reuse another run's "
            f"store): {ns}; set SGLANG_GATE_NAMESPACE_REUSE=1 to override")
    os.makedirs(ns, exist_ok=True)
    return ns


def namespace_manifest(namespace, suffix=None) -> dict:
    suffix = suffix or DEFAULT_CONFIG_SUFFIX
    files = {}
    try:
        names = sorted(os.listdir(namespace))
    except OSError:
        names = []
    for name in names:
        path = os.path.join(namespace, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        files[name] = {"size": st.st_size, "mtime": st.st_mtime}
    current = None
    cur_path = os.path.join(namespace, f"hicache.meta{suffix}.wal.current")
    try:
        current = int(pathlib.Path(cur_path).read_text().strip())
    except Exception:
        current = None
    gens = sorted(int(m.group(1)) for f in names
                  if (m := re.match(rf"hicache\.meta{re.escape(suffix)}"
                                    r"\.wal\.(\d+)$", f)))
    return {"dir": namespace, "files": files, "wal_current": current,
            "wal_generations": gens, "config_suffix": suffix}


def copy_store(source: str, dest: str, include_data: bool = False) -> dict:
    """Copy a store's durable metadata to a self-contained snapshot.

    Copies the manifest + WAL segments + wal.current (everything the offline
    replay needs).  The multi-GiB sparse data file is skipped unless
    ``include_data=True``; offline forensics never reads it.  Read-only w.r.t.
    the source; the destination must not already exist.
    """
    dest_p = pathlib.Path(dest)
    if dest_p.exists():
        raise GateInvalid(f"snapshot destination exists: {dest}")
    dest_p.mkdir(parents=True)
    copied = {}
    for name in sorted(os.listdir(source)):
        is_data = name.startswith("hicache.data")
        is_meta = name.startswith("hicache.meta")
        if not is_meta and not (include_data and is_data):
            continue
        if ".tmp." in name or name.endswith(".lock"):
            continue
        src = os.path.join(source, name)
        if not os.path.isfile(src):
            continue
        dst = dest_p / name
        shutil.copyfile(src, dst)
        copied[name] = {"size": os.path.getsize(dst)}
    return copied


# --------------------------------------------------------------- server
def build_server_args(model: str, port: int, metrics_dir: str,
                      hc_size_gb: int = 2) -> list:
    return [
        "-m", "sglang.launch_server",
        "--model-path", model,
        "--host", "127.0.0.1", "--port", str(port),
        "--tp-size", "1",
        "--mem-fraction-static", "0.92",
        "--max-total-tokens", "65536",
        "--kv-cache-dtype", "fp8_e4m3",
        "--attention-backend", "flashinfer",
        "--linear-attn-prefill-backend", "triton",
        "--linear-attn-decode-backend", "triton",
        "--mamba-radix-cache-strategy", "extra_buffer",
        "--mamba-ssm-dtype", "float32",
        "--enable-hierarchical-cache",
        "--hicache-write-policy", "write_back",
        "--hicache-storage-backend", "extent",
        "--hicache-storage-prefetch-policy", "wait_complete",
        "--hicache-size", str(int(hc_size_gb)),
        "--enable-ready-horizon",
        "--reasoning-parser", "qwen3",
        "--tool-call-parser", "qwen3_coder",
        "--enable-metrics",
        "--export-metrics-to-file",
        "--export-metrics-to-file-dir", metrics_dir,
        "--disable-prefill-cuda-graph",
    ]


def launch_server(tree: str, model: str, port: int, namespace: str,
                  console_path: str, metrics_dir: str, hc_size_gb: int = 2,
                  extra_env=None, gpu_uuid: str = DEFAULT_GPU_UUID):
    python = resolve_python(tree)
    os.makedirs(metrics_dir, exist_ok=True)
    env = dict(os.environ)
    env.pop("SGLANG_PROFILE", None)
    env["PYTHONPATH"] = os.path.join(tree, "src", "python")
    env["CUDA_HOME"] = CUDA_HOME
    env["PATH"] = os.path.join(CUDA_HOME, "bin") + ":" + os.environ.get("PATH", "")
    env["CUDA_VISIBLE_DEVICES"] = gpu_uuid
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR"] = namespace
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    args = build_server_args(model, port, metrics_dir, hc_size_gb)
    fh = open(console_path, "ab")
    proc = subprocess.Popen(
        [python, "-u", *args], cwd="/tmp", env=env,
        stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        close_fds=True, start_new_session=True)
    return proc, fh, env


def wait_health(port: int, proc, timeout_s: float = 2400.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return {"ok": False, "reason": f"server exited rc={proc.returncode}"}
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=5) as r:
                if r.status == 200:
                    return {"ok": True}
        except urllib.error.HTTPError as exc:
            last = f"health {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(3)
    return {"ok": False, "reason": f"health timeout: {last}"}


def kv_dtype_gate(console_path) -> dict:
    try:
        txt = pathlib.Path(console_path).read_text(errors="replace")
    except OSError:
        return {"ok": False, "reason": "console missing"}
    m = re.search(r"KV Cache is allocated\. dtype: (torch\.\w+)", txt)
    m2 = re.search(r"max_total_tokens[^0-9]{0,6}(\d+)", txt)
    dtype = m.group(1) if m else None
    return {"ok": dtype == "torch.float8_e4m3fn", "kv_dtype": dtype,
            "max_total_tokens_seen": int(m2.group(1)) if m2 else None}


def stop_server(proc, console_fh, mode: str = "term",
                timeout_s: float = 240.0) -> dict:
    import signal
    if proc is None:
        return {"stopped": True}
    if proc.poll() is None:
        try:
            if mode == "kill":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:  # noqa: BLE001
            try:
                proc.send_signal(signal.SIGKILL if mode == "kill"
                                 else signal.SIGTERM)
            except Exception:  # noqa: BLE001
                pass
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:  # noqa: BLE001
                proc.kill()
            try:
                proc.wait(timeout=60)
            except Exception:  # noqa: BLE001
                pass
    if console_fh is not None:
        try:
            console_fh.flush()
            os.fsync(console_fh.fileno())
        except Exception:  # noqa: BLE001
            pass
        try:
            console_fh.close()
        except Exception:  # noqa: BLE001
            pass
    return {"stopped": proc.poll() is not None, "rc": proc.returncode}


def wait_idle(port: int, timeout_s: float = 300.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            m = api_get(port, "/metrics", timeout=30.0)
            running = 0.0
            for line in m.splitlines():
                if line.startswith(("sglang:num_running_reqs",
                                    "sglang:num_queue_reqs")):
                    running = max(running, float(line.rsplit(" ", 1)[1]))
            if running == 0.0:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.0)
    return False


def gpu_compute_apps() -> str:
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc!r}"
