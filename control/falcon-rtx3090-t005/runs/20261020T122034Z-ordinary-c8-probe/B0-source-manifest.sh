#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/workspaces/3rdparty/sglang-hicache
run=control/falcon-rtx3090-t005/runs/20261020T122034Z-ordinary-c8-probe
printf 'timestamp_utc=%s\n' "$(date -u +%FT%TZ)"
printf 'head='; git rev-parse HEAD
printf 'branch='; git branch --show-current
printf 'runtime_diff_sha256='; git diff --binary HEAD -- python/sglang/srt/managers/scheduler.py python/sglang/srt/managers/cache_controller.py python/sglang/srt/managers/scheduler_components/ready_horizon.py python/sglang/srt/mem_cache/unified_radix_cache.py | sha256sum | awk '{print $1}'
sha256sum control/falcon-rtx3090-t005/runs/hash_model_identity.py python/sglang/srt/managers/scheduler.py python/sglang/srt/managers/cache_controller.py python/sglang/srt/managers/scheduler_components/ready_horizon.py python/sglang/srt/mem_cache/unified_radix_cache.py python/sglang/srt/mem_cache/kv_cache_configurator.py python/sglang/srt/mem_cache/memory_pool.py /data/sglang-hicache/nsys-2026.5.1/bootstrap/sitecustomize.py /data/sglang-hicache/nsys-2026.5.1/bootstrap/usercustomize.py /home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.abi3.so
printf '\n-- python/runtime versions --\n'
/home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
import sys,torch,importlib.metadata as m
print('python',sys.version); print('torch',torch.__version__,'torch_cuda',torch.version.cuda)
for x in ('sglang','sglang-kernel','flashinfer-python','transformers','triton'):
 try: print(x,m.version(x))
 except Exception as e: print(x,type(e).__name__,str(e))
PY
printf '\n-- GPU --\n'; nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.limit --format=csv
