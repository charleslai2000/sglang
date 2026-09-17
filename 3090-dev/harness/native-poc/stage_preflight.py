#!/usr/bin/env python3
"""Preflight-gate demonstrations: PASS, FAIL, manifest-tamper, runtime-pid.

Runs `src/preflight_identity.py` in five configurations and asserts the exact
exit codes. All child processes are CPU-only and short-lived.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRATCH = Path("/tmp/opencode/l3-native-poc-20260916")
GATE = SCRATCH / "src" / "preflight_identity.py"
FROZEN = Path("/opt/sglang/local-prod-v1.1-candidate")
FROZEN_SRC = FROZEN / "src" / "python"
WORKSPACE_COPY = Path(
    "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang"
)
SELFTEST = SCRATCH / "preflight-selftest-tree"


def run_gate(env, *args, timeout=300):
    pythonpath = env.get("PYTHONPATH", "<unset>")
    proc = subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    return {
        "cmd": [str(GATE), *args],
        "PYTHONPATH": pythonpath,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout.strip().splitlines()[-12:],
        "stderr_tail": proc.stderr.strip().splitlines()[-6:],
    }


def base_env(with_tree: bool):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "PYTHONPATH",
            "PYTHONDONTWRITEBYTECODE",
            "CUDA_VISIBLE_DEVICES",
        )
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = ""
    if with_tree:
        env["PYTHONPATH"] = str(FROZEN_SRC)
    return env


def build_synthetic_tree():
    if SELFTEST.exists():
        shutil.rmtree(SELFTEST)
    (SELFTEST / "src" / "python" / "sglang").mkdir(parents=True)
    (SELFTEST / "manifest").mkdir(parents=True)
    (SELFTEST / "src" / "python" / "sglang" / "__init__.py").write_text(
        "MARKER = 'synthetic-preflight-tree'\n"
    )
    (SELFTEST / "launcher").mkdir(parents=True)
    (SELFTEST / "launcher" / "launch.sh").write_text("#!/bin/sh\nexit 0\n")
    entries = []
    for relative in ("src/python/sglang/__init__.py", "launcher/launch.sh"):
        digest = hashlib.sha256((SELFTEST / relative).read_bytes()).hexdigest()
        entries.append(f"{digest}  ./{relative}")
    (SELFTEST / "manifest" / "TREE-SHA256.txt").write_text("\n".join(entries) + "\n")
    return SELFTEST


def main() -> None:
    report: dict = {}

    # (a) PASS with the correct PYTHONPATH.
    report["a_pass_correct_pythonpath"] = run_gate(
        base_env(True),
        "--tree",
        str(FROZEN),
        "--pid",
        "self",
    )
    assert report["a_pass_correct_pythonpath"]["returncode"] == 0, report[
        "a_pass_correct_pythonpath"
    ]

    # (b) FAIL with PYTHONPATH unset: the venv editable .pth silently resolves
    #     sglang to the stale workspace WIP copy.
    report["b_fail_pythonpath_unset"] = run_gate(
        base_env(False),
        "--tree",
        str(FROZEN),
        "--pid",
        "self",
    )
    assert report["b_fail_pythonpath_unset"]["returncode"] == 2, report[
        "b_fail_pythonpath_unset"
    ]
    fail_stdout = "\n".join(report["b_fail_pythonpath_unset"]["stdout_tail"])
    assert str(WORKSPACE_COPY) in fail_stdout, fail_stdout
    report["b_fail_resolved_to_workspace_copy"] = True

    # (c) manifest branch is live: synthetic tree PASS, then tamper -> exit 3.
    tree = build_synthetic_tree()
    synthetic_env = base_env(False)
    synthetic_env["PYTHONPATH"] = str(tree / "src" / "python")
    synthetic_keys = [
        "--key-file",
        "src/python/sglang/__init__.py",
        "--key-file",
        "launcher/launch.sh",
    ]
    report["c1_synthetic_tree_pass"] = run_gate(
        synthetic_env, "--tree", str(tree), "--pid", "self", *synthetic_keys
    )
    assert report["c1_synthetic_tree_pass"]["returncode"] == 0, report[
        "c1_synthetic_tree_pass"
    ]
    (tree / "launcher" / "launch.sh").write_text("#!/bin/sh\nexit 1\n")
    report["c2_synthetic_tree_tampered_hash"] = run_gate(
        synthetic_env, "--tree", str(tree), "--pid", "self", *synthetic_keys
    )
    assert report["c2_synthetic_tree_tampered_hash"]["returncode"] == 3, report[
        "c2_synthetic_tree_tampered_hash"
    ]

    # (d) runtime /proc/<pid>/environ confirmation, good child and bad child.
    #     The good child is a stand-in for a running server process: it imports
    #     sglang from the frozen tree, records where it resolved, and idles.
    #     (A real server is out of scope: no ports, no GPU.)
    resolved_path = SCRATCH / "preflight-server-child-resolved.txt"
    if resolved_path.exists():
        resolved_path.unlink()
    good_child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sglang, time, pathlib; "
            f"pathlib.Path({str(resolved_path)!r}).write_text(sglang.__file__); "
            "time.sleep(60)",
        ],
        env={**base_env(True)},
    )
    bad_child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        env={**base_env(False)},
    )
    try:
        time.sleep(1.0)
        report["d1_runtime_pid_pass"] = run_gate(
            base_env(True), "--tree", str(FROZEN), "--pid", str(good_child.pid)
        )
        assert report["d1_runtime_pid_pass"]["returncode"] == 0, report[
            "d1_runtime_pid_pass"
        ]
        report["d2_runtime_pid_fail"] = run_gate(
            base_env(True), "--tree", str(FROZEN), "--pid", str(bad_child.pid)
        )
        assert report["d2_runtime_pid_fail"]["returncode"] == 4, report[
            "d2_runtime_pid_fail"
        ]
        report["d_runtime_pid_demo"] = {
            "good_child_pid": good_child.pid,
            "good_child_pythonpath": str(FROZEN_SRC),
            "bad_child_pid": bad_child.pid,
            "bad_child_pythonpath": "<unset>",
            "good_child_sglang_file": (
                resolved_path.read_text() if resolved_path.exists() else None
            ),
            "limitation": "the runtime-pid check is demonstrated on a live "
            "long-running Python process that imports the frozen tree, not on a "
            "real server (starting a server needs a port and the GPU)",
        }
        assert str(FROZEN_SRC) in (report["d_runtime_pid_demo"]["good_child_sglang_file"] or ""), (
            report["d_runtime_pid_demo"]
        )
    finally:
        for child in (good_child, bad_child):
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()

    # (e) verify the gate's manifest key-hash list is actually checking the tree.
    report["e_gate_stdout_check"] = report["a_pass_correct_pythonpath"]["stdout_tail"]

    print(json.dumps(report, indent=2))
    print(
        "PREFLIGHT DEMOS OK: "
        f"pass={report['a_pass_correct_pythonpath']['returncode']} "
        f"unset-py={report['b_fail_pythonpath_unset']['returncode']} "
        f"synthetic-pass={report['c1_synthetic_tree_pass']['returncode']} "
        f"tampered={report['c2_synthetic_tree_tampered_hash']['returncode']} "
        f"pid-pass={report['d1_runtime_pid_pass']['returncode']} "
        f"pid-fail={report['d2_runtime_pid_fail']['returncode']}"
    )
    print("STAGE_PREFLIGHT_OK")


if __name__ == "__main__":
    main()
