#!/usr/bin/env python3
"""Non-GPU mechanism validation for the fail-closed / logprob-extractor fixes.

Label: MECHANISM VALIDATION WITH SYNTHETIC INPUTS.  This validates the
fail-closed mechanism and the logprob extractor; it is NOT a claim about real
runtime behaviour of any served model.

Usage:
  python verify_failclosed.py                # run every check
  python verify_failclosed.py --scenario X   # internal: exit-code probe subprocess
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

M2_PATH = "/var/log/sglang/local-prod-v1/phase8/m2-bringup-smoke-20260916/m2_smoke.py"
SH_PATH = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/server_harness.py"
SD_PATH = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/session_driver.py"
RD_PATH = "/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/rerun_driver.py"
PY = "/opt/sglang/local-prod-v1/env/bin/python"
SCRATCH = "/tmp/opencode/failclosed-minfix-20260916"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def all_pass_art(with_vision):
    art = {
        "status": "completed",
        "kv_gate": {"ok": True, "dtype": "torch.float8_e4m3fn", "tokens": 8192},
        "step1_finite_logits": {
            "p1": {"http": 200, "n_logprob_values_checked": 10, "n_nonfinite": 0},
            "p2": {"http": 200, "n_logprob_values_checked": 12, "n_nonfinite": 0},
        },
        "step2_semantic": {
            "arithmetic": {"http": 200},
            "capital": {"http": 200},
            "echo": {"http": 200},
            "chat_arithmetic": {"http": 200},
        },
    }
    if with_vision:
        art["step2_vision"] = {"color": {"http": 200}, "shape": {"http": 200}}
    return art


SCENARIOS = {
    "blocked_port_busy": ({"status": "blocked_port_busy"}, False, True),
    "skipped": ({"status": "skipped"}, False, True),
    "server_not_ready": ({"status": "server_failed", "health_error": "health timeout after 1200s"}, False, True),
    "probe_not_executed": ({"status": "completed", "kv_gate": {"ok": True},
                            "step2_semantic": {"arithmetic": {"http": 200}}}, False, True),
    "missing_result_entirely": ({}, False, True),
    "all_gates_passed_m3": (all_pass_art(False), False, False),
    "all_gates_passed_m4": (all_pass_art(True), True, False),
}


def scenario_exit_probe(name):
    """Subprocess entry: emit the real module exit code for a synthetic artifact."""
    sh = load("server_harness", SH_PATH)
    art, rv, _ = SCENARIOS[name]
    verdict, failures = sh.evaluate_verdict(json.loads(json.dumps(art)))
    print(json.dumps({"verdict": verdict, "failures": failures}))
    sys.exit(sh.verdict_exit_code(verdict))


def check_status_mapping():
    print("\n[1] synthetic status -> process exit code (real server_harness helpers)")
    ok = True
    for name, (_, _, expect_nonzero) in SCENARIOS.items():
        p = subprocess.run([PY, os.path.abspath(__file__), "--scenario", name],
                           capture_output=True, text=True, cwd=SCRATCH,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        rc = p.returncode
        info = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
        good = (rc != 0) == expect_nonzero
        print(f"    {name:24s} rc={rc:3d} expect_nonzero={expect_nonzero!s:5s} "
              f"{'OK' if good else 'FAIL'}  {info}")
        ok = ok and good
    print("    RESULT:", "PASS" if ok else "FAIL")
    return ok


def check_real_preflight():
    print("\n[2] real preflight-failure paths (no GPU lock, no server launched)")
    ok = True
    sh = load("server_harness", SH_PATH)
    tmp = os.path.join(SCRATCH, "preflight_m3m4")
    os.makedirs(os.path.join(tmp, "m3"), exist_ok=True)
    sh.RUNROOT = tmp
    # Hold a listener on a scratch port so the harness's first check (port_free)
    # fails; this aborts before Popen and before the driver lock is ever involved.
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    sh.PORT = s.getsockname()[1]
    s.listen(1)
    sys.argv = ["server_harness.py", "m3"]
    rc = sh.main()
    s.close()
    report = json.load(open(os.path.join(tmp, "m3", "report.json")))
    good = rc != 0 and report.get("status") == "blocked_port_busy" and report.get("verdict") == "FAIL"
    print(f"    server_harness m3 blocked_port_busy: rc={rc} status={report.get('status')!r} "
          f"verdict={report.get('verdict')!r} {'OK' if good else 'FAIL'}")
    print(f"      verdict_failures={report.get('verdict_failures')}")
    ok = ok and good

    # m2 preflight (safetensors count) happens BEFORE lock acquisition too.
    m2 = load("m2_smoke", M2_PATH)
    tmp2 = os.path.join(SCRATCH, "preflight_m2")
    empty_model = os.path.join(SCRATCH, "empty_model_dir")
    os.makedirs(tmp2, exist_ok=True)
    os.makedirs(empty_model, exist_ok=True)
    # m2_smoke binds REPORT/DRIVER_LOG at import; redirect EVERY write path so
    # the historical run-directory artifacts are never touched.
    m2.RUN_DIR = tmp2
    m2.REPORT = os.path.join(tmp2, "report.json")
    m2.DRIVER_LOG = os.path.join(tmp2, "driver.log")
    m2.MODEL_DIR = empty_model
    rc2 = m2.main()
    rep2 = json.load(open(m2.REPORT))
    if m2._logf:
        m2._logf.close()
    good2 = rc2 != 0 and rep2.get("status") == "blocked_safetensors_preflight"
    print(f"    m2_smoke empty model dir preflight: rc={rc2} status={rep2.get('status')!r} "
          f"{'OK' if good2 else 'FAIL'}")
    ok = ok and good2
    print("    RESULT:", "PASS" if ok else "FAIL")
    return ok


def check_driver_missing_result():
    print("\n[3] drivers treat a missing model verdict as failure")
    ok = True
    tmp = os.path.join(SCRATCH, "drivers")
    shutil.rmtree(tmp, ignore_errors=True)
    for name, mod_path in (("session_driver", SD_PATH), ("rerun_driver", RD_PATH)):
        mod = load(name, mod_path)
        mod.RUNDIR = os.path.join(tmp, name)
        os.makedirs(os.path.join(mod.RUNDIR, "m3"), exist_ok=True)
        missing = mod.read_verdict("m3")
        fail_rc = mod.session_exit_code(["server_harness_m3 rc=2 verdict='FAIL'"])
        pass_rc = mod.session_exit_code([])
        with open(os.path.join(mod.RUNDIR, "m3", "report.json"), "w") as f:
            json.dump({"verdict": "FAIL"}, f)
        failed = mod.read_verdict("m3")
        good = (missing is None and failed == "FAIL" and fail_rc != 0 and pass_rc == 0)
        print(f"    {name}: missing verdict={missing!r} read FAIL={failed!r} "
              f"exit(failures)={fail_rc} exit([])={pass_rc} {'OK' if good else 'FAIL'}")
        ok = ok and good
    print("    RESULT:", "PASS" if ok else "FAIL")
    return ok


def old_finite_values(x):
    """Reproduce the PRE-FIX extractor for contrast only (test code)."""
    out = []
    if isinstance(x, bool):
        return out
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, list):
        for v in x:
            out += old_finite_values(v)
    elif isinstance(x, dict):
        for v in x.values():
            out += old_finite_values(v)
    return out


def check_finite_logits_extractor():
    print("\n[4] finite-logits extractor returns ONLY logprobs; NaN/Inf still detected")
    m2 = load("m2_smoke", M2_PATH)
    meta_info = {
        "input_token_logprobs": [[-0.5, 1234, "A"], [-1.5, 5678, "B"]],
        "output_token_logprobs": [[-0.25, 99, "C"]],
        "input_top_logprobs": [[[-0.5, 1234, "A"], [-2.0, 42, "Z"]]],
        "output_top_logprobs": [[[-0.1, 7, "Q"]]],
    }
    vals = (m2.logprob_values(meta_info["input_token_logprobs"])
            + m2.logprob_values(meta_info["output_token_logprobs"])
            + m2.top_logprob_values(meta_info["input_top_logprobs"])
            + m2.top_logprob_values(meta_info["output_top_logprobs"]))
    want = sorted([-0.5, -1.5, -0.25, -0.5, -2.0, -0.1])
    got = sorted(vals)
    only_logprobs = (got == want) and all(v <= 0 for v in got)
    old = old_finite_values([meta_info[k] for k in meta_info])
    print(f"    new vals={got}")
    print(f"    old extractor vals(min/max)=({min(old)}, {max(old)})  "
          f"-> old max is a token id, new max={max(got)}")
    bad_meta = {"output_token_logprobs": [[float("nan"), 1, "x"], [float("inf"), 2, "y"],
                                          [-1.0, 3, "z"]]}
    bad_vals = m2.logprob_values(bad_meta["output_token_logprobs"])
    bad = [v for v in bad_vals if not math.isfinite(v)]
    detected = len(bad) == 2
    print(f"    injected NaN/Inf detected: {detected} ({len(bad)} non-finite of "
          f"{len(bad_vals)}; values checked still only logprob slots)")
    good = only_logprobs and detected
    print("    RESULT:", "PASS" if good else "FAIL")
    return good


def check_stream_final_chunk():
    print("\n[5] D3: cumulative-chunk SSE -> final text == last chunk (not concat)")
    chunks = ["a", "a b", "a b c", "a b c d"]

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i, c in enumerate(chunks):
                obj = {"text": c, "meta_info": {"completion_tokens": i + 1}}
                self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    m2 = load("m2_smoke", M2_PATH)
    m2.HOST = "127.0.0.1"
    m2.PORT = srv.server_address[1]
    code, ttft, t_last, n, text, meta, err = m2.http_stream("/generate", {"text": "x"})
    srv.shutdown()
    concatenated = "".join(chunks)
    good = (code == 200 and err is None and text == chunks[-1]
            and len(text) == len(chunks[-1]) and n == len(chunks))
    print(f"    http={code} n_chunks={n} returned_len={len(text)} last_chunk_len={len(chunks[-1])} "
          f"concat_len={len(concatenated)} inflation={len(concatenated)/len(chunks[-1]):.1f}x")
    print(f"    returned text={text!r} {'OK' if good else 'FAIL'}")
    print("    RESULT:", "PASS" if good else "FAIL")
    return good


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--scenario":
        scenario_exit_probe(sys.argv[2])
        return
    print("=== MECHANISM VALIDATION WITH SYNTHETIC INPUTS (no GPU, no server) ===")
    results = [
        check_status_mapping(),
        check_real_preflight(),
        check_driver_missing_result(),
        check_finite_logits_extractor(),
        check_stream_final_chunk(),
    ]
    print("\n=== OVERALL:", "PASS" if all(results) else "FAIL", "===")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
