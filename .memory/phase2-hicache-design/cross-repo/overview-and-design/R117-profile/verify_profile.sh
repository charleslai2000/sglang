#!/usr/bin/env bash
# Read-only verifier for the frozen local RTX 3090 SGLang profile (R117).
# Re-derives live facts and compares them against profile.json.
# Exits 0 only on full match; otherwise prints the exact mismatching field(s) and exits non-zero.
# Idempotent and read-only: it never starts/stops/reconfigures the server and writes nothing.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTIVATE="/mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh"

if [ -r "$ACTIVATE" ]; then
  # shellcheck disable=SC1090
  source "$ACTIVATE" >/dev/null 2>&1
fi

exec python3 - "$SCRIPT_DIR" <<'PY'
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.request

profile_dir = sys.argv[1]
profile_path = os.path.join(profile_dir, "profile.json")
with open(profile_path, "r", encoding="utf-8") as fh:
    prof = json.load(fh)

mismatches = []


def check(field, expected, got):
    if expected != got:
        mismatches.append("%s: expected %r, got %r" % (field, expected, got))


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# --- health + liveness -------------------------------------------------------
launch = prof["launch"]
pid = launch["process_id"]
child = launch["scheduler_child_pid"]
try:
    with urllib.request.urlopen("http://127.0.0.1:30000/health", timeout=10) as resp:
        check("health.http_status", 200, resp.status)
except Exception as exc:  # noqa: BLE001
    check("health.http_status", 200, "EXC:%s" % exc)
for name, p in (("launch.process_id", pid), ("launch.scheduler_child_pid", child)):
    try:
        os.kill(p, 0)
    except OSError as exc:
        check(name, "alive", "DEAD:%s" % exc)

# --- argv --------------------------------------------------------------------
with open("/proc/%d/cmdline" % pid, "rb") as fh:
    raw = fh.read().split(b"\0")
live_argv = [x.decode() for x in raw if x]
check("launch.argv", launch["argv"], live_argv)

# --- launch script hash ------------------------------------------------------
script = launch["launch_script"]
if os.path.isfile(script):
    with open(script, "rb") as fh:
        check("launch.launch_script_sha256", launch["launch_script_sha256"],
              hashlib.sha256(fh.read()).hexdigest())
else:
    check("launch.launch_script", "exists", "MISSING")

# --- environ -----------------------------------------------------------------
env_blob = read("/proc/%d/environ" % pid)
live_env = dict(
    item.split("=", 1) for item in env_blob.split("\0") if "=" in item
)
for key, expected in launch["env_material"].items():
    check("launch.env_material.%s" % key, expected, live_env.get(key, "<UNSET>"))

# --- software ----------------------------------------------------------------
sw = prof["software"]
head = subprocess.run(
    ["git", "-C", sw["repo"], "rev-parse", "HEAD"],
    capture_output=True, text=True, check=False,
).stdout.strip()
check("software.repo_head", sw["repo_head"], head)
check("software.python_version", sw["python_version"], platform.python_version())

import torch  # noqa: E402
import triton  # noqa: E402
import transformers  # noqa: E402
import sglang  # noqa: E402

check("software.torch", sw["torch"], torch.__version__)
check("software.triton", sw["triton"], triton.__version__)
check("software.transformers", sw["transformers"], transformers.__version__)
check("software.sglang", sw["sglang"], sglang.__version__)
check("software.sglang_import_path", sw["sglang_import_path"],
      os.path.realpath(sglang.__file__))
check("software.cuda_runtime", sw["cuda_runtime"], str(torch.version.cuda))

# --- hardware (GPU pinned by UUID) ------------------------------------------
hw = prof["hardware"]["gpu"]
pin = hw["uuid"]
nvsmi = subprocess.run(
    ["nvidia-smi",
     "--query-gpu=index,uuid,name,driver_version,memory.total,compute_cap",
     "--format=csv,noheader,nounits"],
    capture_output=True, text=True, check=False,
).stdout.strip().splitlines()
row = None
for line in nvsmi:
    cols = [c.strip() for c in line.split(",")]
    if len(cols) >= 6 and cols[1] == pin:
        row = cols
        break
if row is None:
    check("hardware.gpu.uuid", pin, "NOT FOUND in nvidia-smi")
else:
    check("hardware.gpu.index", hw["index"], int(row[0]))
    check("hardware.gpu.model", hw["model"], row[2])
    check("hardware.gpu.driver_version", hw["driver_version"], row[3])
    check("hardware.gpu.vram_total_mib", hw["vram_total_mib"], int(row[4]))
    check("hardware.gpu.compute_capability", hw["compute_capability"], row[5])
    os.environ["CUDA_VISIBLE_DEVICES"] = pin
    props = torch.cuda.get_device_properties(0)
    check("hardware.gpu.multi_processor_count", hw["multi_processor_count"],
          props.multi_processor_count)
    check("hardware.gpu.vram_total_bytes", hw["vram_total_bytes"],
          props.total_memory)

# --- l3 storage stats --------------------------------------------------------
l3 = prof["profile_capacity_semantics"]["l3_storage_current"]
total = 0
file_count = 0
subdir_count = 0
for root, dirs, files in os.walk(l3["dir"]):
    subdir_count += len(dirs)
    for name in files:
        file_count += 1
        try:
            total += os.stat(os.path.join(root, name)).st_size
        except OSError:
            pass
check("l3_storage_current.size_bytes", l3["size_bytes"], total)
check("l3_storage_current.file_count", l3["file_count"], file_count)
check("l3_storage_current.subdir_count", l3["subdir_count"], subdir_count)

# --- provenance markers in the live server log -------------------------------
bind = prof["provenance_bind"]
log_path = launch["server_log"]
pattern = ('"deployment_manifest_digest": "[0-9a-f]+"'
           '|"profile_id": "[^"]+"'
           '|"run_id": "[^"]+"'
           '|"source_build": "[0-9a-f:]+"')
found = subprocess.run(
    ["grep", "-aoE", pattern, log_path],
    capture_output=True, text=True, check=False,
).stdout
markers = set()
for line in found.splitlines():
    line = line.strip()
    if '"deployment_manifest_digest": "' in line:
        markers.add(line.split('"')[3])
    elif line.startswith('"profile_id": "') :
        markers.add(line.split('"')[3])
    elif line.startswith('"run_id": "'):
        markers.add(line.split('"')[3])
    elif line.startswith('"source_build": "'):
        markers.add(line.split('"')[3])
for key in ("profile_id", "run_id", "source_build", "deployment_manifest_digest"):
    check("provenance_bind.%s (live log) present" % key, True, bind[key] in markers)

# --- R114 manifest cross-check ----------------------------------------------
r114 = "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R114-bundle/manifest.json"
if os.path.isfile(r114):
    m114 = json.load(open(r114, "r", encoding="utf-8"))
    rt = m114.get("runtime", {})
    check("R114.runtime.process_id", bind["process_id"], rt.get("process_id"))
    check("R114.runtime.run_id", bind["run_id"], rt.get("run_id"))
    check("R114.runtime.profile_id", bind["profile_id"], rt.get("profile_id"))
    check("R114.runtime.source_build", bind["source_build"], rt.get("source_build"))
else:
    check("R114.manifest", "exists", "MISSING")

# --- result ------------------------------------------------------------------
if mismatches:
    print("PROFILE VERIFY: FAIL (%d mismatch(es))" % len(mismatches))
    for m in mismatches:
        print("  - " + m)
    sys.exit(1)
print("PROFILE VERIFY: PASS (all live-derived fields match profile.json)")
sys.exit(0)
PY
