#!/usr/bin/env python3
"""Text-only vision-scope validation for server_harness.py.

LABEL: MECHANISM VALIDATION WITH SYNTHETIC INPUTS.  No GPU, no lock, no port,
no server.  Writes only under the scratch RUNROOT.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys

SH_PATH = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/server_harness.py"
PY = "/opt/sglang/local-prod-v1/env/bin/python"
SCRATCH = "/tmp/opencode/failclosed-minfix-20260916/vision_scope_scratch"


def load():
    spec = importlib.util.spec_from_file_location("server_harness", SH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def text_pass_art():
    return {
        "model_key": "synthetic",
        "status": "completed",
        "kv_gate": {"ok": True, "dtype": "torch.float8_e4m3fn", "tokens": 8192},
        "step1_finite_logits": {
            "p1": {"http": 200, "n_logprob_values_checked": 72, "n_nonfinite": 0},
            "p2": {"http": 200, "n_logprob_values_checked": 102, "n_nonfinite": 0},
        },
        "step2_semantic": {
            "arithmetic": {"http": 200, "contains_expected": True},
            "capital": {"http": 200, "contains_expected": True},
            "echo": {"http": 200},
            "chat_arithmetic": {"http": 200},
        },
    }


def m4_text_pass():
    a = text_pass_art()
    a["step2_vision"] = {
        "model_multimodal": True,
        "color": {"http": 400, "expected": ["green"], "answer": None,
                  "raw": {"error": "Model only supports text input"}},
        "shape": {"http": 400, "expected": ["circle"], "answer": None,
                  "raw": {"error": "Model only supports text input"}},
    }
    return a


def m4_text_gate_failed():
    a = m4_text_pass()
    a["step2_semantic"]["arithmetic"]["http"] = 500
    return a


def m4_text_gate_missing():
    a = m4_text_pass()
    del a["step1_finite_logits"]["p2"]
    return a


def m4_vision_unexpected():
    a = m4_text_pass()
    a["step2_vision"]["color"] = {"http": 500, "raw": {"error": "boom"}}
    return a


def text_fail_vision_200():
    a = m4_text_pass()
    a["step2_vision"]["color"] = {"http": 200, "answer": "green", "contains_expected": True}
    a["step2_vision"]["shape"] = {"http": 200, "answer": "circle", "contains_expected": True}
    a["step2_semantic"]["capital"]["http"] = 503
    return a


def m4_blocked():
    return {"model_key": "m4", "status": "blocked_port_busy"}


CASES = {
    # name: (art_factory, require_vision, initial_rc, expect_verdict, expect_zero_exit)
    "m4_text_only_pass": (m4_text_pass, True, 0, "PASS", True),
    "m4_text_gate_failed": (m4_text_gate_failed, True, 0, "FAIL", False),
    "m4_text_gate_missing": (m4_text_gate_missing, True, 0, "FAIL", False),
    "m3_text_only_pass": (text_pass_art, False, 0, "PASS", True),
    "m4_vision_unexpected": (m4_vision_unexpected, True, 0, "PASS", True),
    "text_fail_vision_200": (text_fail_vision_200, True, 0, "FAIL", False),
    "m4_blocked_port_busy": (m4_blocked, True, 2, "FAIL", False),
}


def run_case(name):
    """Subprocess entry: run finish() against scratch, print record, exit with rc."""
    sh = load()
    factory, rv, initial_rc, _, _ = CASES[name]
    art = factory()
    outdir = os.path.join(SCRATCH, name)
    os.makedirs(outdir, exist_ok=True)
    rc = sh.finish(outdir, art, initial_rc, rv)
    written = json.load(open(os.path.join(outdir, "report.json")))
    print(json.dumps({
        "case": name,
        "verdict": written.get("verdict"),
        "verdict_failures": written.get("verdict_failures"),
        "vision_scope": written.get("vision_scope"),
        "vision_scored": written.get("vision_scored"),
        "vision_record": written.get("vision_record"),
    }))
    sys.exit(rc)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--case":
        run_case(sys.argv[2])
        return
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)
    print("=== TEXT-ONLY VISION-SCOPE MECHANISM VALIDATION (SYNTHETIC INPUTS) ===")
    ok = True
    for name, (_, _, _, exp_verdict, exp_zero) in CASES.items():
        p = subprocess.run([PY, os.path.abspath(__file__), "--case", name],
                           capture_output=True, text=True, cwd=SCRATCH,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rc = p.returncode
        good = (rec["verdict"] == exp_verdict) and ((rc == 0) == exp_zero)
        vr = rec["vision_record"] or {}
        blob = json.dumps(vr)
        no_pass = ("passed" not in blob.lower())
        print(f"\n  {name}: rc={rc} verdict={rec['verdict']} "
              f"[expect verdict={exp_verdict} zero_exit={exp_zero}] {'OK' if good else 'FAIL'}")
        print(f"    vision_scope={rec['vision_scope']!r} vision_scored={rec['vision_scored']!r}")
        print(f"    vision_record={json.dumps(vr)}")
        if rec["verdict_failures"]:
            print(f"    verdict_failures={rec['verdict_failures']}")
        ok = ok and good and no_pass
    print("\n=== OVERALL:", "PASS" if ok else "FAIL", "===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
