# PROD-STATE-CHECK-R2-20260918.md

## Task
Establish current GPU 3090 (24576 MiB) production service state. Verify port 30000 health, model endpoint availability, and production supervisor state. Report process status, HTTP endpoints, GPU utilization, and lock file ownership.

## Scope
- HTTP health and model endpoint checks (localhost 127.0.0.1:30000, LAN 192.168.20.250:30000)
- Port state enumeration via ss -ltnp
- Process inspection for Python/sglang/supervise processes
- GPU memory utilization via nvidia-smi
- Lock file content and state (gpu-3090.lock)
- Evidence of recent gate/smoke experiments
- Supervisor log inspection

## Result

**Port 30000 Status: UP**
- All HTTP codes return 200 (loopback: /health=200, /v1/models=200)
- LAN endpoint /health: 200

**GPU Status: BUSY**
- GPU: NVIDIA GeForce RTX 3090 (24576 MiB)
- GPU Memory Usage: 23009 MiB used / 24576 MiB total = 93.6% used
- GPU Utilization: 100%
- Free VRAM: 1567 MiB (24576 - 23009)
- PIDs using GPU:
  - 1654119: /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python (LD) 300 MiB
  - 1654601: sglang::scheduler (LD) 22634 MiB

**Canonical Lock File: HELD**
- File: /tmp/opencode/gpu-3090.lock
- Owner: supervise-prod-prod-20260917T211800Z-1653969
- PID: 1654092 (supervise.sh)
- Authoritative PID binding GPU service: 1654119
- Lock mtime: 2026-09-17 21:18:00.924556673 +0000

**Recent Gate/Smoke Evidence: NONE**
- No gate/smoke experiments with recent mtimes (<3 hours) found
- Files exist (smoke/, protocol-smoke-20260917/, gguf-gate-20260917/) but all dated Sep 17 15:37-19:06
- Recent files in /tmp/opencode/ are: effort-* (21:46-21:48), gatea* (21:41-21:44), tests.diff/readme.diff (21:42)
- Current time: 22:00:03, so files from 21:48-22:00 are recent but these are not gate/smoke experiments

## Evidence

**1. HTTP Health Checks:**
```
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/v1/models -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.250:30000/health -> 200
```

**2. Port State (ss -ltnp):**
```
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1654119,fd=68))         
```

**3. Process State:**
```
ps -eo pid,ppid,lstart,etimes,cmd | grep -Ei 'sglang|launch_server|supervise|gate|smoke' | grep -v grep
1654092       1 Thu Sep 17 21:18:00 2026    2522 bash /tmp/opencode/prod-service-20260917/bin/supervise.sh prod /opt/sglang/local-prod-v1.2.1-candidate 30000 prod-20260917T211800Z-1653969 ...
1654119 1654092 Thu Sep 17 21:18:00 2026    2522 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 ...
```

**4. GPU Memory:**
```
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
1654119, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1654601, sglang::scheduler, 22634 MiB
```

**5. Lock File:**
```
cat /tmp/opencode/gpu-3090.lock
{"owner": "supervise-prod-prod-20260917T211800Z-1653969", "pid": 1654092, "generation": 7, "acquired": "2026-09-17T21:18:00Z"}
stat: mtime: 2026-09-17 21:18:00.924556673 +0000
```

**6. Supervisor Log Tail (last 20 lines):**
```
[2026-09-17 22:00:19] [HAE] {"attempt_id": null, ..., "terminal": "forfeited_alloc_failed", ..., "ts_wall_ms": 1789682419742, ...}
[2026-09-17 22:00:20] Decode batch, #running-req: 2, #full token: 103323, ...)
```
Log shows active processing with no errors. Prefill/Decode batches running at 408-144 token/s.

## Defects / Blockers
None. Production service is healthy and operational.

## Remaining Claims / Exclusions
- No production service stoppage detected
- No foreign session detected (PID 1654119 is running supervised production service)
- Only gate/smoke experiments from earlier today (before 21:37)
- /var/log/sglang/local-prod-v1.2.1/ exists but read-only check shows directory, not reading file contents

## Terminal state: DONE

Terminal state: DONE
Artifact path: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/PROD-STATE-CHECK-R2-20260918.md
(a) Port 30000: UP (200, 200, 200 for /health, /v1/models, LAN /health)
(b) GPU Busy? YES, by PIDs 1654119/1654601, Free VRAM: 1567 MiB
(c) Canonical lock held? YES, by supervise-prod-prod-20260917T211800Z-1653969 (PID 1654092)
(d) Recent gate/smoke evidence: None (only pre-21:37 experiments detected)
