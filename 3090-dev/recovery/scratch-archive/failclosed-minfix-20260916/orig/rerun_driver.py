#!/usr/bin/env python3
"""Second-pass driver: re-confirm M3 (richer generation capture) and first-run M4.

Same canonical lock discipline as session_driver.py.  Does not run the kernel
probe again (its evidence already exists); runs each model's server harness and
waits for port 30164 to be genuinely released between models.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import time
from datetime import datetime, timezone

RUNDIR = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916"
LOCK = "/tmp/opencode/gpu-3090.lock"
PY = "/opt/sglang/local-prod-v1/env/bin/python"
SRC = "/opt/sglang/local-prod-v1.1-candidate/src/python"
GPU = "GPU-2e3ed202-3655-d919-0a64-259209bc6587"
PORT = 30164
RUN_TAG = os.environ.get("RUN_TAG", "2")
SESSION_LOG = os.path.join(RUNDIR, f"session{RUN_TAG}.log")


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
                        "owner": "m3-m4-gpu-smoke-20260916(rerun)",
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


def listener_pid():
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


def wait_port_free(timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pid = listener_pid()
        if pid is None:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", PORT))
                return True
            except OSError:
                pass
            finally:
                s.close()
        time.sleep(3)
    pid = listener_pid()
    if pid:
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(
                errors="replace"
            )
        except Exception:  # noqa: BLE001
            cmd = ""
        log(f"port still held by pid={pid} cmd={cmd!r}")
        if "sglang.launch_server" in cmd:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(10)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return wait_port_free(60)
    return False


def gpu_state():
    apps = []
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
        apps = [x for x in out.splitlines() if x.strip()]
    except Exception:  # noqa: BLE001
        pass
    return {"apps": apps}


def main():
    os.makedirs(RUNDIR, exist_ok=True)
    log("=== rerun session start ===")
    lockfd = acquire_lock()
    try:
        log(f"gpu-clear: {gpu_state()}")
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["CUDA_VISIBLE_DEVICES"] = GPU
        for tag in ("m3", "m4"):
            ok = wait_port_free(240)
            log(f"port free before {tag}: {ok}")
            cmd = [PY, os.path.join(RUNDIR, "server_harness.py"), tag]
            p = subprocess.run(cmd, cwd="/tmp", env=env, timeout=3600)
            log(f"EXIT[server_harness_{tag}]: rc={p.returncode}")
            time.sleep(5)
    finally:
        fcntl.flock(lockfd, fcntl.LOCK_UN)
        os.close(lockfd)
        log("released canonical lock")
        with open(os.path.join(RUNDIR, f"rerun{RUN_TAG}_done.marker"), "w") as f:
            f.write(now() + "\n")
        log("=== rerun session end ===")


if __name__ == "__main__":
    main()
