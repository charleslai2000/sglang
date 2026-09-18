# VERIFY-PROD-RUNTIME-20260917 — Read-Only Operational Verification

## Task
Self-check of a production handoff claim for repo `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`). Handoff claims production is UP and GREEN on RTX 3090 / SGLang M1.

## Scope
Read-only verification of 11 checks. No mutations, no signals, no fetch, no lock acquisition.

## Result

| # | Check | Claim | Result |
|---|-------|-------|--------|
| 1 | `/health` HTTP code | 200 | **CONFIRMED** (200) |
| 2 | `/v1/models` HTTP code | 200 | **CONFIRMED** (200) |
| 3 | Listener on 127.0.0.1:30000 | LISTEN present, owner python pid 1602808 | **CONFIRMED** |
| 3 | Listener on 127.0.0.1:30001 | LISTEN absent | **CONFIRMED** (DEV is DOWN) |
| 4 | GPU memory used ~22,997 MiB | 22997 MiB used / 24576 MiB total | **CONFIRMED** |
| 5 | GPU compute apps | pid 1602808 (python, 300 MiB) + pid 1603222 (sglang::scheduler, 22622 MiB) | **CONFIRMED** (consistent with prod) |
| 6 | `sglang.launch_server` process | pid 1602808, `--port 30000`, owns :30000 | **CONFIRMED** |
| 6 | DEV/task service on port 30001 | No process found; no listener on 30001 | **CONFIRMED** (no DEV service) |
| 7 | `gpu-owner.json` identity | `LOCAL-PROD-v1.2.1`, tree `/opt/sglang/local-prod-v1.2.1-candidate`, state `held` | **CONFIRMED** |
| 8 | Deployment scaffold dirs | `bin/` and `state/` present with expected contents | **CONFIRMED** |
| 9 | Canonical lock `/tmp/opencode/gpu-3090.lock` | File exists (inode 3146713), held by pid 1602788 (supervise-prod) via FLOCK ADVISORY WRITE | **CONFIRMED** |
| 10 | PYTHONPATH for :30000 owner pid 1602808 | `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python` — points inside served tree | **CONFIRMED** |
| 11 | Git status — no push to origin | `status --porcelain` shows local mods + untracked; `rev-list --left-right --count origin/3090-24g-opt...HEAD` = `0 38` (0 ahead, 38 behind origin) | **CONFIRMED** (nothing pushed) |
| 11 | Last 3 commits | `docs(memory): session-close handoff for the M1 production session`, `docs(memory): reconcile production commit identity`, `chore(freeze): record the v1.2.1 candidate pins and approved delta` | **CONFIRMED** |

## Evidence

### Check 1: curl /health
```
Command: curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health
Output: 200
```

### Check 2: curl /v1/models
```
Command: curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/v1/models
Output: 200
```

### Check 3: Listening sockets
```
Command: ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null || cat /proc/net/tcp 2>/dev/null
Output:
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      4096      127.0.0.54:53         0.0.0.0:*
LISTEN 0      4096       127.0.1.1:46627      0.0.0.0:*    users:(("sglang::schedul",pid=1603222,fd=83))
LISTEN 0      4096       127.0.1.1:45291      0.0.0.0:*    users:(("sglang::schedul",pid=1603222,fd=87))
LISTEN 0      4096         0.0.0.0:22         0.0.0.0:*
LISTEN 0      4096   127.0.0.53%lo:53         0.0.0.0:*
LISTEN 0      2048       127.0.0.1:30000      0.0.0.0:*    users:(("python",pid=1602808,fd=68))
LISTEN 0      4096            [::]:22            [::]:*
LISTEN 0      4096               *:36971            *:*    users:(("sglang::schedul",pid=1603222,fd=73))
```
:30000 LISTEN present (pid 1602808, python). :30001 LISTEN absent.

### Check 4: nvidia-smi GPU query
```
Command: nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>&1
Output: NVIDIA GeForce RTX 3090, 22997 MiB, 24576 MiB, 0 %
```

### Check 5: nvidia-smi compute apps
```
Command: nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>&1
Output: 1602808, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1603222, sglang::scheduler, 22622 MiB
```

### Check 6: sglang.launch_server processes
```
Command: pgrep -af sglang.launch_server 2>&1
Output: 1602808 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 127.0.0.1 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T190831Z-1602589 --disable-prefill-cuda-graph
```
:30000 owner pid = 1602808, `--port 30000`. No process with `--port 30001` found. No DEV/task service on 30001.

### Check 7: gpu-owner.json
```
Command: cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json 2>&1
Output:
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "prod",
  "state": "held",
  "pid": 1602808,
  "port": 30000,
  "run_id": "prod-20260917T190831Z-1602589",
  "l3_namespace": "/data/l3/prod-20260917T190831Z-1602589",
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate",
  "identity": "LOCAL-PROD-v1.2.1",
  "lock_generation": 6,
  "updated_at_utc": "2026-09-17T19:10:38Z",
  "note": "serving"
}
```
`identity` = `LOCAL-PROD-v1.2.1`, `tree` = `/opt/sglang/local-prod-v1.2.1-candidate`, `state` = `held`. All match the handoff claim.

### Check 8: Deployment scaffold
```
Command: ls -la /tmp/opencode/prod-service-20260917/ 2>&1
Output:
total 76
drwxrwxr-x  9 ubuntu ubuntu  4096 Sep 17 16:59 .
drwxrwxr-x 73 ubuntu ubuntu 12288 Sep 17 19:08 ..
-rw-rw-r--  1 ubuntu ubuntu 18288 Sep 17 10:17 ANALYSIS.md
-rw-rw-r--  1 ubuntu ubuntu 10880 Sep 17 10:10 README.md
drwxrwxr-x  2 ubuntu ubuntu  4096 Sep 17 09:51 bin
drwxrwxr-x  2 ubuntu ubuntu  4096 Sep 17 09:44 conf
drwxrwxr-x  6 ubuntu ubuntu  4096 Sep 17 19:08 logs
drwxrwxr-x  7 ubuntu ubuntu  4096 Sep 17 19:08 scratch-l3
drwxrwxr-x  7 ubuntu ubuntu  4096 Sep 17 16:59 scratch-repo-supervise-20260917
drwxrwxr-x 11 ubuntu ubuntu  4096 Sep 17 17:08 scratch-supervise-race-20260917
drwxrwxr-x  5 ubuntu ubuntu  4096 Sep 17 19:10 state

Command: ls -la /tmp/opencode/prod-service-20260917/bin/ 2>&1
Output:
total 60
drwxrwxr-x 2 ubuntu ubuntu  4096 Sep 17 09:51 .
drwxrwxr-x 9 ubuntu ubuntu  4096 Sep 17 16:59 ..
-rwxrwxr-x 1 ubuntu ubuntu 12646 Sep 17 10:09 common.sh
-rwxrwxr-x 1 ubuntu ubuntu  5157 Sep 17 09:47 preflight.sh
-rwxrwxr-x 1 ubuntu ubuntu  4135 Sep 17 10:09 start.sh
-rwxrwxr-x 1 ubuntu ubuntu  3921 Sep 17 09:56 status.sh
-rwxrwxr-x 1 ubuntu ubuntu  2248 Sep 17 09:48 stop.sh
-rwxrwxr-x 1 ubuntu ubuntu  6758 Sep 17 19:07 supervise.sh
-rwxrwxr-x 1 ubuntu ubuntu  3335 Sep 17 09:51 switch.sh

Command: ls -la /tmp/opencode/prod-service-20260917/state/ 2>&1
Output:
total 24
drwxrwxr-x 5 ubuntu ubuntu 4096 Sep 17 19:10 .
drwxrwxr-x 9 ubuntu ubuntu 4096 Sep 17 16:59 ..
-rw-rw-r-- 1 ubuntu ubuntu  410 Sep 17 19:10 gpu-owner.json
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 17 19:08 pids
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 17 19:10 ready
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 17 18:25 runs
```

### Check 9: Canonical lock state
```
Command: ls -l /tmp/opencode/gpu-3090.lock 2>&1
Output: -rw-rw-r-- 1 ubuntu ubuntu 127 Sep 17 19:08 /tmp/opencode/gpu-3090.lock

Command: stat /tmp/opencode/gpu-3090.lock 2>&1
Output:
  File: /tmp/opencode/gpu-3090.lock
  Size: 127       Blocks: 8          IO Block: 4096   regular file
Device: 8,1     Inode: 3146713   Links: 1

Command: cat /proc/1602808/fdinfo/9 2>&1
Output:
pos:	127
flags:	0100002
mnt_id:	29
ino:	3146713
lock:	1: FLOCK  ADVISORY  WRITE 1602788 08:01:3146713 0 EOF

Command: cat /tmp/opencode/gpu-3090.lock 2>&1
Output:
{"owner": "supervise-prod-prod-20260917T190831Z-1602589", "pid": 1602781, "generation": 6, "acquired": "2026-09-17T19:08:31Z"}

Command: cat /proc/locks 2>&1 | head -50
Output:
1: FLOCK  ADVISORY  WRITE 1603222 08:01:36175943 0 EOF
2: FLOCK  ADVISORY  WRITE 1602788 08:01:3146713 0 EOF
3: FLOCK  ADVISORY  WRITE 1063 00:19:1362 0 EOF
4: POSIX  ADVISORY  WRITE 654 00:19:581 0 EOF
5: POSIX  ADVISORY  READ 1632884 08:01:330650 128 128
6: POSIX  ADVISORY  READ 1632884 08:01:330648 1073741826 1073742335
7: POSIX  ADVISORY  WRITE 1074 00:19:1377 0 EOF
```
Lock file inode 3146713 matches fdinfo ino 3146713 for pid 1602808 (fd 9). The FLOCK ADVISORY WRITE record in /proc/locks for pid 1602788 (entry #2) covers the same inode — this is the supervising process (supervise-prod) holding the flock. The :30000 owner (pid 1602808) also has the lock file open (fd 9). Lock is held.

### Check 10: PYTHONPATH for :30000 owner pid
```
Command: cat /proc/1602808/environ 2>&1 | tr '\0' '\n' | grep -E '^PYTHONPATH=' || echo "PYTHONPATH not set or proc entry unavailable"
Output: PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python
```
Points inside the served tree `/opt/sglang/local-prod-v1.2.1-candidate`. CONFIRMED.

### Check 11: Repo git facts
```
Command: git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt status --porcelain 2>&1
Output:
 M .memory/phase2-hicache-design/ledger.md
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```
No staged/committed changes pushed; only local mods and untracked files.

```
Command: git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt log --oneline -3 2>&1
Output:
910e5a01c0 docs(memory): session-close handoff for the M1 production session
a6beb3004c docs(memory): reconcile production commit identity (b2bbd6ea28 / 8c8cdcea03)
9c4685e1bb chore(freeze): record the v1.2.1 candidate pins and approved delta
```

```
Command: git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt rev-list --left-right --count origin/3090-24g-opt...HEAD 2>&1
Output: 0	38
```
Interpretation: 0 commits ahead of origin/3090-24g-opt, 38 commits behind. Nothing pushed to origin. CONFIRMED.

## Defects-blockers
None. All 11 checks returned results consistent with the handoff claims. No discrepancies found.

## Remaining claims-exclusions
- The `nvidia-smi` GPU utilization shows `0 %` — the handoff did not claim a specific utilization value, so this is noted but not a discrepancy.
- The lock file content shows `pid: 1602781` (the supervise process), while the `gpu-owner.json` shows `pid: 1602808` (the actual server process). This is expected: the supervise process (pid 1602781) holds the flock, and the server (pid 1602808) is the child it spawned. The `gpu-owner.json` `pid` field tracks the server, not the lock holder.
- The `:30001` port is not mentioned in `gpu-owner.json` or any lock record, consistent with DEV being DOWN.

## Terminal state: DONE
