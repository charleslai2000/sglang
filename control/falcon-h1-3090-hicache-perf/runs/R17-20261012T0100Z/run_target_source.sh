#!/usr/bin/env bash
# Run an R17-targeted measurement from the authorized 3090-24g-hicache worktree.
# Captures commit + dirty tracked source identity + import paths before execution.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
EXPECTED_BRANCH=3090-24g-hicache
EXPECTED_HEAD=6f612b0301416157e48fc5e40ac01680bc212b3c
if [[ "$(git -C "$ROOT" branch --show-current)" != "$EXPECTED_BRANCH" ]]; then
  echo "wrong branch; refusing run" >&2; exit 20
fi
if [[ "$(git -C "$ROOT" rev-parse HEAD)" != "$EXPECTED_HEAD" ]]; then
  echo "unexpected HEAD; refusing run" >&2; exit 21
fi
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/target-6f612b03-dirty-current"
mkdir -p "$RUN"
if [[ -e "$RUN/manifest.json" ]]; then echo "run directory already exists" >&2; exit 22; fi
PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}" \
  /home/ubuntu/venvs/sglang-3090/bin/python - "$ROOT" "$RUN" <<'PY'
import hashlib, importlib, json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); run=pathlib.Path(sys.argv[2])
files=sorted(subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root,text=True).splitlines())
h=hashlib.sha256()
for name in files:
 p=root/name; b=p.read_bytes(); h.update(name.encode()+b'\0'+b)
modules={}
for name in ['sglang','sglang.srt.models.falcon_h1','sglang.srt.server_args','sgl_kernel','sgl_kernel.load_utils','flashinfer']:
 try:
  m=importlib.import_module(name); p=pathlib.Path(m.__file__).resolve()
  modules[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
 except Exception as e: modules[name]={'error':repr(e)}
sub=lambda *a: subprocess.check_output(a,cwd=root,text=True).strip()
manifest={'branch':sub('git','branch','--show-current'),'head':sub('git','rev-parse','HEAD'),'dirty_tracked_sha256':h.hexdigest(),'dirty_paths':files,'model':'/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4','model_revision':'52036ae497a2c0c253e17f98cc8652f2f7082ae3','python':sys.executable,'python_version':sys.version,'modules':modules,'gpu':'RTX 3090; recheck immediately before each run','data_lineage':'target a5895b5d + tracked dirty SHA; never label exact HEAD'}
(run/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
PY
