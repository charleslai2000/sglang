#!/usr/bin/env python3
"""Session driver for m3-m4-gpu-smoke-20260916.

Acquires the canonical GPU lock /tmp/opencode/gpu-3090.lock with bounded
backoff (60 s poll, up to ~45 min, never killing or racing another holder),
holds it for the whole session, runs the direct kernel probe, then each model's
server harness, and finally releases the lock.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

RUNDIR = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916"
LOCK = "/tmp/opencode/gpu-3090.lock"
PY = "/opt/sglang/local-prod-v1/env/bin/python"
SRC = "/opt/sglang/local-prod-v1.1-candidate/src/python"
GPU = "GPU-2e3ed202-3655-d919-0a64-259209bc6587"
PORT = 30164
SESSION_LOG = os.path.join(RUNDIR, "session.log")

M3_GGUF = "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf"
M4_GGUF = "/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    with open(SESSION_LOG, "a") as f:
        f.write(line + "\n")


def acquire_lock():
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o664)
    for i in range(46):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(
                fd,
                json.dumps(
                    {
                        "owner": "m3-m4-gpu-smoke-20260916",
                        "pid": os.getpid(),
                        "acquired": datetime.now(timezone.utc).isoformat(),
                    }
                ).encode(),
            )
            os.fsync(fd)
            log(f"acquired canonical lock {LOCK}")
            return fd
        except BlockingIOError:
            log(f"canonical lock busy (attempt {i + 1}/46); sleeping 60s")
            time.sleep(60)
    raise SystemExit("could not acquire canonical lock within ~45 min")


def gpu_state():
    st = {"port_free": None, "apps": [], "util_samples": []}
    import socket

    s = socket.socket()
    try:
        s.bind(("127.0.0.1", PORT))
        st["port_free"] = True
    except OSError:
        st["port_free"] = False
    finally:
        s.close()
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=20,
        ).strip()
        if out:
            st["apps"] = [x.strip() for x in out.splitlines() if x.strip()]
    except Exception as e:  # noqa: BLE001
        st["apps_error"] = str(e)
    for _ in range(5):
        try:
            u = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=10,
            ).strip()
            st["util_samples"].append(int(u))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    st["contended"] = bool(st["apps"]) or (max(st["util_samples"] or [0]) > 20)
    return st


def run(cmd, tag):
    log(f"RUN[{tag}]: {' '.join(cmd)}")
    t0 = time.time()
    p = subprocess.run(cmd, cwd="/tmp", capture_output=False, timeout=None)
    log(f"EXIT[{tag}]: rc={p.returncode} elapsed={round(time.time() - t0, 1)}s")
    return p.returncode


def port_listener_pid():
    try:
        out = subprocess.check_output(["ss", "-ltnp"], text=True, timeout=10)
        for ln in out.splitlines():
            if f":{PORT} " in ln:
                m = re.search(r"pid=(\d+)", ln)
                if m:
                    return int(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return None


def ensure_port_released(tag):
    for _ in range(30):
        if port_listener_pid() is None:
            return
        time.sleep(2)
    pid = port_listener_pid()
    if pid:
        try:
            cmdline = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(
                errors="replace"
            )
        except Exception:  # noqa: BLE001
            cmdline = ""
        log(f"WARN[{tag}]: port {PORT} still held by pid={pid} cmdline={cmdline!r}")
        if "sglang.launch_server" in cmdline:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(10)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            log(f"{tag}: terminated our leftover server pid={pid}")


def main():
    os.makedirs(RUNDIR, exist_ok=True)
    log("=== session start m3-m4-gpu-smoke-20260916 ===")
    log(f"gpu={GPU} port={PORT} python={PY} pythonpath={SRC}")
    lockfd = acquire_lock()
    try:
        for tag in ("m3", "m4"):
            os.makedirs(os.path.join(RUNDIR, tag, "metrics"), exist_ok=True)
        st = gpu_state()
        log(f"gpu-clear check: {st}")

        env = dict(os.environ)
        env["PYTHONPATH"] = SRC
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = GPU

        # Step 3 harness evidence: direct CUDA GGUF kernels on real payloads.
        for tag, gguf in (("m3", M3_GGUF), ("m4", M4_GGUF)):
            out = os.path.join(RUNDIR, tag, "kernel_probe.json")
            cmd = [PY, os.path.join(RUNDIR, "kernel_probe.py"), gguf, out]
            p = subprocess.run(cmd, cwd="/tmp", env=env, timeout=1800)
            log(f"EXIT[kernel_probe_{tag}]: rc={p.returncode}")

        for tag in ("m3", "m4"):
            st = gpu_state()
            log(f"gpu-clear before {tag}: {st}")
            cmd = [PY, os.path.join(RUNDIR, "server_harness.py"), tag]
            p = subprocess.run(cmd, cwd="/tmp", env=env, timeout=3600)
            log(f"EXIT[server_harness_{tag}]: rc={p.returncode}")
            ensure_port_released(tag)
            time.sleep(10)
    finally:
        fcntl.flock(lockfd, fcntl.LOCK_UN)
        os.close(lockfd)
        log("released canonical lock")
        with open(os.path.join(RUNDIR, "session_done.marker"), "w") as f:
            f.write(now() + "\n")
        log("=== session end ===")


if __name__ == "__main__":
    main()
