#!/usr/bin/env python3
"""Smoke: boot the throwaway instrumented server on a tiny cell and confirm the
probe timeline is produced.  Deletes its own disposable store."""
import os
import pathlib
import random
import shutil
import sys

RUN = pathlib.Path("/var/log/sglang/local-prod-v1/phase8/l3-v1-cpu-gate-20260916")
sys.path.insert(0, str(RUN))
import fleet_matrix_v2 as fm  # noqa: E402

fm.SOURCE = pathlib.Path("/tmp/opencode/l3-v1-inst-src")
fm.L3_DIR = "/data/l3/l3-v1-inst-smoke/store"
orig = fm.hicache_args


def small(arm, prefix):
    a, e = orig(arm, prefix)
    e["SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE"] = "2Gi"
    e["SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE"] = "1Gi"
    return a, e


fm.hicache_args = small
fm.LOCK_PATH = pathlib.Path("/tmp/opencode/gpu-3090.lock")
outdir = RUN / "smoke"
shutil.rmtree("/data/l3/l3-v1-inst-smoke", ignore_errors=True)
pathlib.Path(fm.L3_DIR).mkdir(parents=True, exist_ok=True)
probe_out = outdir / "arm_C" / "l3-probe-timeline.jsonl"
probe_out.parent.mkdir(parents=True, exist_ok=True)
probe_out.unlink(missing_ok=True)
os.environ["L3_INST_PROBE"] = "1"
os.environ["L3_INST_PROBE_INTERVAL"] = "1.0"
os.environ["L3_INST_PROBE_OUT"] = str(probe_out)
specs = [{"context": 2600, "batch": 2, "output_len": 16, "decisive": False}]
res = fm.run_arm("C", specs, 8192, outdir, random.Random(20260916))
print("SMOKE RESULT", res)
