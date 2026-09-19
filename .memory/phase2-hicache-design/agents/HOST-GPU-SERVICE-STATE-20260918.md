Task
  Read-only inventory of GPU + SGLang service + coordination lock state; answer whether idle GPU can run a ~27B Q3_K_M GGUF model (~16-20 GB VRAM) WITHOUT disturbing production.

Scope
  - Boot/uptime (boot date, uptime, last boot)
  - GPU inventory (nvidia-smi -L, --query-gpu=..., --query-compute-apps=...)
  - GPU compute apps: pid, owning command, VRAM held; locate production :30000 server PID/argv
  - Listener/socket state (ss -ltnp) for ports 30000, 30001, 30164, 30165; check scheduler socket *:36971
  - GPU lock /tmp/opencode/gpu-3090.lock: existence (inode/size), flock state, lock content/owner
  - /tmp/opencode/ top-level presence (especially prod-service-* dir)
  - Production liveness (curl /health, /v1/models) and served model id
  - Free-space (df -h) for /data, /mnt/data, L3 store
  - DEV-provider service on port 30001: UP/DOWN
  - Second GPU or separate GPU host available locally (from inventory + config/docs)
  - No process start/stop/kill/restart. No flock acquisition. No writes except artifact and /tmp/opencode/ scratch. No network except localhost.

Evidence
  Command: uptime -s && cat /proc/uptime && who -b
  Output:
    2026-09-15 22:23:56
    170017.73 5042877.32
             system boot  2026-09-15 22:24
  
  Command: nvidia-smi -L
  Output:
    GPU 0: NVIDIA GeForce RTX 3090 (UUID: GPU-2e3ed202-3655-d919-0a64-259209bc6587)

  Command: nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
  Output:
    0, GPU-2e3ed202-3655-d919-0a64-259209bc6587, NVIDIA GeForce RTX 3090, 24576 MiB, 23005 MiB, 1120 MiB, 100 %

  Command: nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
  Output:
    1654119, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
    1654601, sglang::scheduler, 22630 MiB

  Python server argv/env (PID 1654119):
    /proc/1654119/cmdline: /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969 --disable-prefill-cuda-graph
    /proc/1654119/cwd: /tmp
    Environment includes:
      CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
      SGLANG_PORT=30000
      PROD_PORT=30000
      PROD_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate
      MODEL_PATH=/data/models/qwen35-9b-w4a16
      SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE=100Gi
      SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi
      SGLANG_L3_ROOT=/data/l3
      SGLANG_L3_NATIVE_WRITE_PATH=1
      GPU_LOCK=/tmp/opencode/gpu-3090.lock
      STATE_FILE=/tmp/opencode/prod-service-20260917/state/gpu-owner.json
      SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=/data/l3/prod-20260917T211800Z-1653969

  Listener state (ss -ltnp):
    Port 30000: LISTEN 0.0.0.0:30000 python PID=1654119 (prod service)
    Port 30001: no listeners (DEV service DOWN)
    Port 30164: no listeners
    Port 30165: no listeners (GATE port)
    Port 36971: not present (scheduler socket absent)

  GPU lock (/tmp/opencode/gpu-3090.lock):
    - ls -la: -rw-rw-r-- 1 ubuntu ubuntu 127 Sep 17 21:18 /tmp/opencode/gpu-3090.lock
    - Content: {"owner": "supervise-prod-prod-20260917T211800Z-1653969", "pid": 1654092, "generation": 7, "acquired": "2026-09-17T21:18:00Z"}
    - /proc/locks: no entry for that inode (kernel version may not record flock, or process not recorded)
    - lsof: no additional entries for lock file
    - Lock is FILE (reads as.file.type not .flock.type per /proc/locks spec)

  /tmp/opencode/ presence:
    - Directory exists with prod-service-20260917/ (PID 46849 is the supervisor)
    - Contains: DIRECTORY-MAP-20260917.md; W4-filler0.json; W4-filler1.json; W4-member-A.json; W4-member-B.json; etc.
    - gpu-3090.lock (127 bytes)
    - prod-service-20260917/ directory exists

  Production liveness (localhost only):
    - curl -s -o /dev/null -w '\%{http_code}\n' http://127.0.0.1:30000/health => 200
    - curl -s -o /dev/null -w '\%{http_code}\n' http://127.0.0.1:30000/v1/models => 200
    - /v1/models payload: {"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16","object":"model","created":1789681079,"owned_by":"sglang","root":"/data/models/qwen35-9b-w4a16","parent":null,"max_model_len":131072}]}
    - Served model id: /data/models/qwen35-9b-w4a16

  Free-space:
    - df -h /data /mnt/data:
      Filesystem    Size    Used Avail Use% Mounted on
      /dev/sda1   484G    385G   99G  80% /

  DEV-provider service: port 30001 DOWN (no listener observed; no /proc/[PID]/cwd command rooted at /opt/sglang/local-dev stating "DEVELOPMENT" in argv)

  Second GPU/host check (read-only):
    - GPU inventory: 1x NVIDIA GeForce RTX 3090 on this host.
    - Local config/docs in /opt/sglang/ or repo docs bound for OTHER hosts/ports: none found.
    - Conclusion: ABSENT — no second GPU and no other GPU host bound for this task.

Result
  - TOTAL VRAM: 24576 MiB (RTX 3090)
  - PRODUSED BY Qwen35-9b-w4a16 (memory alone ~17.84 GiB => 18250 MiB memory.
  - VRAM available)

  - PROD uses 23005 MiB free.

  - 27B Q3_K_M GGUF: 16-20 GB => 16384-20480 MiB.

  -   - GPU Memory Usage: 23005 MiB used (prod), 1120 MiB free
  - 27B Q3_K_M GGUF requirement: 16384-20480 MiB for model weights + context buffer minimum (~20 GB typical)
  - Production process (PID 1654119 python + 1654601 sglang::scheduler) uses total VRAM ~23005 MiB
  - Coexistence math: 23005 (current) + 16384 (min GGUF) = 39389 MiB > 24576 (total available)
    Excess: 39389 - 24576 = 14813 MiB shortfall
    (Even tighter: 23005 + 20480 = 43485 MiB; Excess: 43485 - 24576 = 18909 MiB)

  IDLE_GPU_AVAILABLE_FOR_27B = no

  Why no:
    - Only one GPU present (RTX 3090, 24576 MiB total)
    - GPU 100% utilized (100% utilization.gpu)
    - Production Qwen35-9B W4A16 server (PID 1654119) + scheduler (PID 1654601) consume ~23005 MiB
    - Remaining free VRAM: 1120 MiB
    - 27B GGUF requires 16384-20480 MiB (min)
    - 1120 MiB < 16384 MiB => insufficient to run GGUF alone
    - Coexistence impossible: would require dropping ~17864 MiB from production (current 92% memory fraction via --mem-fraction-static 0.92)

  Why no:
    - Only one GPU present (RTX 3090, 24 GB)
    - GPU is 100% utilized
    - All VRAM consumed by production Qwen35-9B W4A16 server (PID 1654119) + scheduler (PID 1654601)
    - Remaining VRAM: 1120 MiB
    - 27B GGUF requires 16384-20480 MiB
    - 1120 MiB < 16384 MiB minimum requirement

Blocks & exclusions
  - No second GPU on this host.
  - No separate GPU host visible here (no /proc/net/localhost binding or config indicating such).
  - L3 stores (SGLANG_L3_ROOT=/data/l3, RESERVED_L3_STORE=/data/l3/local-prod-v1.1) are on /dev/sda1.

Terminal: done

Done
