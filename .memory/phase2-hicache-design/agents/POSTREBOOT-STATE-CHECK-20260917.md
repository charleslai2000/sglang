# POSTREBOOT-STATE-CHECK-20260917

## Task
Read-only reconnaissance to establish the EXACT current state of the host and SGLang production
service after an alleged reboot of the host. Checks 1-12 as specified in the task. No
start/stop/kill/signal, no GPU lock acquisition, no writes outside this artifact.

## Scope
- Read-only observation only. No mutation of any process, file, lock, GPU, or git state.
- Targets: host services (ports 30000/30001), SGLang process tree, GPU (nvidia-smi), /tmp/opencode
  scaffold + lock, /opt/sglang frozen tree + manifest, uptime/boot, repo git facts.
- Repo: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt
- Result artifact: this file.

## Result

**The premise of the task is NOT supported by evidence: this host has NOT rebooted.**
Uptime shows boot at **2026-09-15 22:23:56** (system boot 2026-09-15 22:24), i.e. roughly
**46.5 hours** of uptime at check time. `/tmp/opencode/` and its entire contents are intact
(including the "discardable across reboot" scaffold), and the production SGLang service on
127.0.0.1:30000 is **UP and healthy** (HTTP 200 on both /health and /v1/models), with the GPU
lock actively held by the live service supervisor.

The service running is the expected one:
- Tree: `/opt/sglang/local-prod-v1.2.1-candidate` (present)
- Identity: `LOCAL-PROD-v1.2.1`, SOURCE_COMMIT `b2bbd6ea28`, TREE_HASH
  `3bd285d51e3fdb0c338400dd0203bf8d131f26504baf1076084eea372849f7c8`
- Run ID: `prod-20260917T190831Z-1602589`
- launch_server PID 1602808; supervisor `supervise.sh` PID 1602781

### Summary table

| # | Check | Observed | Interpretation |
|---|-------|----------|----------------|
| 1 | /health http_code | `200` | UP |
| 2 | /v1/models http_code | `200` | UP |
| 3 | LISTEN 30000 | `LISTEN 127.0.0.1:30000 users:(("python",pid=1602808,fd=68))` | UP, owner pid visible |
| 3 | LISTEN 30001 | absent | ABSENT |
| 4 | `pgrep -af sglang.launch_server` | PID 1602808 full launch_server cmdline | RUNNING |
| 5 | GPU name/mem/util | `NVIDIA GeForce RTX 3090, 22997 MiB, 24576 MiB, 0 %` | GPU allocated, idle util |
| 6 | compute apps | PID 1602808 python 300 MiB; PID 1603222 sglang::scheduler 22622 MiB | 2 compute apps, ~22.9 GB used |
| 7 | /tmp/opencode/ | present, populated (76 entries) | PRESENT |
| 7 | prod-service-20260917/ | present, full scaffold (bin/conf/logs/state/scratch) | PRESENT |
| 7 | bin/ | present: common.sh preflight.sh start.sh status.sh stop.sh supervise.sh switch.sh | PRESENT |
| 7 | state/gpu-owner.json | present, `state: held`, pid 1602808, port 30000, run_id prod-20260917T190831Z-1602589, lock_generation 6, note "serving" | PRESENT/HELD |
| 7 | /tmp/opencode/gpu-3090.lock | present, 127 bytes, inode 3146713 | PRESENT |
| 8 | lock held? | `/proc/locks` FLOCK ADVISORY WRITE pid 1602788 dev 08:01 inode 3146713; live fds held by LIVE PIDs 1602781 and 1602808 | **HELD** |
| 9 | /opt/sglang/ | present (v1, v1.1, v1.1.2, v1.2, v1.2.1 candidates, opencodex trees) | PRESENT |
| 9 | frozen tree | present: env->, launcher, manifest, src, tools | PRESENT |
| 9 | manifest identity | SOURCE_COMMIT b2bbd6ea28; TREE_HASH 3bd285d5...; identity LOCAL-PROD-v1.2.1 | PRESENT |
| 10 | boot time | `uptime -s` = 2026-09-15 22:23:56; /proc/uptime = 167410.56s; who -b = 2026-09-15 22:24 | **NO RECENT REBOOT (uptime ~46.5h)** |
| 11 | git HEAD | `910e5a01c05da1311925bc5fd174f9a0ec04b3a3` | recorded |
| 11 | git status | 8 modified + several untracked (incl. this agents/ dir) | dirty worktree |
| 11 | git log -3 | 910e5a01c0 / a6beb3004c / 9c4685e1bb | recorded |
| 12 | leftover sglang/gate procs | Only the ACTIVE service tree (supervise.sh, launch_server, scheduler, detokenizer, resource_tracker, inductor worker). No gate_a / f2_restart / dead-run leftovers. | no leftovers |

## Evidence

### Check 1 / 2 — HTTP status
```
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health
200
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/v1/models
200
```

### Check 3 — Listening sockets
```
$ ss -ltnp
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                                       
LISTEN 0      4096      127.0.0.54:53         0.0.0.0:*                                                 
LISTEN 0      4096       127.0.1.1:46627      0.0.0.0:*    users:(("sglang::schedul",pid=1603222,fd=83))
LISTEN 0      4096       127.0.1.1:45291      0.0.0.0:*    users:(("sglang::schedul",pid=1603222,fd=87))
LISTEN 0      4096         0.0.0.0:22         0.0.0.0:*                                                 
LISTEN 0      4096   127.0.0.53%lo:53         0.0.0.0:*                                                 
LISTEN 0      4096       127.0.1.1:35791      0.0.0.0:*    users:(("sglang::schedul",pid=1603222,fd=79))
LISTEN 0      2048       127.0.0.1:30000      0.0.0.0:*    users:(("python",pid=1602808,fd=68))         
LISTEN 0      4096            [::]:22            [::]:*                                                 
LISTEN 0      4096               *:36971            *:*    users:(("sglang::schedul",pid=1603222,fd=73))

$ netstat -ltnp
/bin/bash: line 1: netstat: command not found
```
Port 30000 = 0x7530. `/proc/net/tcp` local_address `0100007F:7530` state `0A` (LISTEN) present.
Port 30001 = 0x7531 absent from `/proc/net/tcp`.

### Check 4 — pgrep
```
$ pgrep -af sglang.launch_server
1602808 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 127.0.0.1 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T190831Z-1602589 --disable-prefill-cuda-graph
```

### Check 5 / 6 — GPU
```
$ nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
NVIDIA GeForce RTX 3090, 22997 MiB, 24576 MiB, 0 %

$ nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
1602808, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1603222, sglang::scheduler, 22622 MiB
```

### Check 7 — /tmp/opencode scaffold
```
$ ls -la /tmp/opencode/
<present; 76 entries; includes prod-service-20260917, gpu-3090.lock, logs, locks, build/freeze scratch>

$ ls -la /tmp/opencode/prod-service-20260917/
drwxrwxr-x  9 ubuntu ubuntu  4096 Sep 17 16:59 .
drwxrwxr-x 76 ubuntu ubuntu 12288 Sep 17 20:39 ..
-rw-rw-r--  1 ubuntu ubuntu 18288 Sep 17 10:17 ANALYSIS.md
-rw-rw-r--  1 ubuntu ubuntu 10880 Sep 17 10:10 README.md
drwxrwxr-x  2 ubuntu ubuntu  4096 Sep 17 09:51 bin
drwxrwxr-x  2 ubuntu ubuntu  4096 Sep 17 09:44 conf
drwxrwxr-x  6 ubuntu ubuntu  4096 Sep 17 19:08 logs
drwxrwxr-x  7 ubuntu ubuntu  4096 Sep 17 10:18 scratch-l3
drwxrwxr-x  7 ubuntu ubuntu  4096 Sep 17 16:59 scratch-repo-supervise-20260917
drwxrwxr-x 11 ubuntu ubuntu  4096 Sep 17 17:08 scratch-supervise-race-20260917
drwxrwxr-x  5 ubuntu ubuntu  4096 Sep 17 19:10 state

$ ls -la /tmp/opencode/prod-service-20260917/bin/
-rwxrwxr-x 1 ubuntu ubuntu 12646 Sep 17 10:09 common.sh
-rwxrwxr-x 1 ubuntu ubuntu  5157 Sep 17 09:47 preflight.sh
-rwxrwxr-x 1 ubuntu ubuntu  4135 Sep 17 10:09 start.sh
-rwxrwxr-x 1 ubuntu ubuntu  3921 Sep 17 09:56 status.sh
-rwxrwxr-x 1 ubuntu ubuntu  2248 Sep 17 09:48 stop.sh
-rwxrwxr-x 1 ubuntu ubuntu  6758 Sep 17 19:07 supervise.sh
-rwxrwxr-x 1 ubuntu ubuntu  3335 Sep 17 09:51 switch.sh

$ cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json
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

$ ls -l /tmp/opencode/gpu-3090.lock
-rw-rw-r-- 1 ubuntu ubuntu 127 Sep 17 19:08 /tmp/opencode/gpu-3090.lock
```

### Check 8 — canonical lock held
```
$ cat /tmp/opencode/gpu-3090.lock
{"owner": "supervise-prod-prod-20260917T190831Z-1602589", "pid": 1602781, "generation": 6, "acquired": "2026-09-17T19:08:31Z"}

$ stat /tmp/opencode/gpu-3090.lock
Device: 8,1	Inode: 3146713

$ cat /proc/locks
1: FLOCK  ADVISORY  WRITE 1603222 08:01:36175943 0 EOF
2: FLOCK  ADVISORY  WRITE 1602788 08:01:3146713 0 EOF
3: FLOCK  ADVISORY  WRITE 1063 00:19:1362 0 EOF
4: POSIX  ADVISORY  WRITE 654 00:19:581 0 EOF
5: POSIX  ADVISORY  READ 1644932 08:01:330650 128 128
6: POSIX  ADVISORY  READ 1644932 08:01:330648 1073741826 1073742335
7: POSIX  ADVISORY  WRITE 1074 00:19:1377 0 EOF
```
Line 2: device `08:01` + inode `3146713` == the canonical lock file. The reported locker PID
1602788 no longer has a `/proc` entry (it was the flock caller and has exited), but the lock is
still ACTIVE because the open file description is inherited by live processes:
```
$ lsof /tmp/opencode/gpu-3090.lock
COMMAND     PID   USER   FD   TYPE DEVICE SIZE/OFF  NODE NAME
bash    1602781 ubuntu    9u   REG    8,1      127 3146713 /tmp/opencode/gpu-3090.lock
python  1602808 ubuntu    9u   REG    8,1      127 3146713 /tmp/opencode/gpu-3090.lock
```
Interpretation: lock HELD (generation 6), owner live via fds 1602781/1602808. No one may be
granted this lock while these fds remain open.

### Check 9 — frozen tree + manifest
```
$ ls -la /opt/sglang/
drwxr-xr-x  9 root   root   4096 Sep 17 18:32 .
drwxr-xr-x  4 root   root   4096 Sep 15 21:59 ..
drwxr-xr-x  6 root   root   4096 Sep 15 22:31 local-prod-v1
drwxr-xr-x  6 root   root   4096 Sep 15 22:31 local-prod-v1.1-candidate
drwxr-xr-x  6 ubuntu ubuntu 4096 Sep 17 07:28 local-prod-v1.1.2-candidate
drwxrwxr-x  6 ubuntu ubuntu 4096 Sep 17 18:19 local-prod-v1.2-candidate
drwxrwxr-x  6 ubuntu ubuntu 4096 Sep 17 18:35 local-prod-v1.2.1-candidate
drwxr-xr-x 23 root   root   4096 Sep 17 13:41 opencodex-provider-2d4e33a832
drwx------  4 ubuntu ubuntu 4096 Sep 17 16:30 opencodex-provider-run

$ ls -la /opt/sglang/local-prod-v1.2.1-candidate/
lrwxrwxrwx  1 ubuntu ubuntu   30 Sep 17 18:35 env -> /home/ubuntu/venvs/sglang-3090
dr-xr-xr-x  2 ubuntu ubuntu 4096 Sep 17 18:35 launcher
drwxrwxr-x  2 ubuntu ubuntu 4096 Sep 17 18:36 manifest
dr-xr-xr-x 24 ubuntu ubuntu 4096 Sep 17 18:35 src
dr-xr-xr-x  2 ubuntu ubuntu 4096 Sep 17 18:35 tools

$ cat /opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json | head -40
{
  "LAUNCHER_HASH": "38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914",
  "LOADED_SO_HASH": { ... "verified_at_freeze": true, "verified_at_launch": false },
  "RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "3bd285d51e3fdb0c338400dd0203bf8d131f26504baf1076084eea372849f7c8",
  "freeze_tool": "v1.1.2-freeze-20260917",
  "frozen_at_utc": "2026-09-17T18:36:32Z",
  "generated_by": "bin/freeze.sh",
  "gpu_touched": false,
  ...
  "launcher": { "path": ".../launcher/launch.sh", "sha256": "38487942de..." }
}
```
Manifest identity present. SOURCE_COMMIT `b2bbd6ea28`, TREE_HASH `3bd285d5...`,
launcher sha256 matches LAUNCHER_HASH. NOTE: `gpu_touched: false` in the manifest and
`verified_at_launch: false` for the loaded `.so` — recorded as-is, not evaluated here.

### Check 10 — Uptime / boot proof
```
$ uptime -s
2026-09-15 22:23:56
$ cat /proc/uptime
167410.56 4966664.47
$ who -b
         system boot  2026-09-15 22:24
```
167410.56 s = 46.50 hours = ~1 day 22 h 30 m of uptime. Boot was 2026-09-15, long before the
production service launch (2026-09-17T19:08Z) and before this check. **No reboot occurred.**

### Check 11 — Repo git facts (read-only)
```
$ git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt rev-parse HEAD
910e5a01c05da1311925bc5fd174f9a0ec04b3a3

$ git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt status --porcelain
 M .memory/phase2-hicache-design/ledger.md
 M 3090-dev/gates/production/README.md
 M 3090-dev/gates/production/f2_restart_recovery.py
 M 3090-dev/gates/production/gate_a_content_integrity.py
 M 3090-dev/gates/production/gate_a_f1_cold_l1.py
 M 3090-dev/gates/production/gate_common.py
 M 3090-dev/gates/production/test_gate_helpers.py
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? .memory/protocol-subagent-smoke-20260917/
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py

$ git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt log --oneline -3
910e5a01c0 docs(memory): session-close handoff for the M1 production session
a6beb3004c docs(memory): reconcile production commit identity (b2bbd6ea28 / 8c8cdcea03)
9c4685e1bb chore(freeze): record the v1.2.1 candidate pins and approved delta
```
Working tree is dirty (pre-existing; not modified by this task). No fetch/commit/reset issued.

### Check 12 — Process scan (READ-ONLY /proc/*/cmdline)
Matching processes (all belong to the single ACTIVE production service tree; none are leftovers
from a dead run and none are gate_a / f2_restart processes):
```
PID 1602781: bash /tmp/opencode/prod-service-20260917/bin/supervise.sh prod /opt/sglang/local-prod-v1.2.1-candidate 30000 prod-20260917T190831Z-1602589 /data/l3/prod-20260917T190831Z-1602589 /tmp/opencode/prod-service-20260917/logs/prod-20260917T190831Z-1602589 1789672111.963197255
PID 1602808: .../env/bin/python -u -m sglang.launch_server ... (full flags above)
PID 1603221: .../env/bin/python -c from multiprocessing.resource_tracker import main;main(27)
PID 1603222: sglang::scheduler
PID 1603223: sglang::detokenizer
PID 1603676: .../torch/_inductor/compile_worker/__main__.py ... --parent=1603222 ...
```
Process relationship:
```
PID    PPID
1602781       1   (supervise.sh, session leader)
1602808 1602781   (sglang.launch_server)
1603221 1602808   (resource_tracker)
1603222 1602808   (sglang::scheduler)
1603223 1602808   (sglang::detokenizer)
1603676 1603222   (inductor compile worker)
```

## Defects / blockers
- **Premise mismatch (material).** The task states the host was rebooted and that `/tmp` is
  discardable across reboot. Evidence shows the host booted 2026-09-15 22:23:56 (uptime ~46.5 h)
  and `/tmp/opencode` is fully intact. Any plan that assumes a fresh boot / lost `/tmp` / a cold
  service is incorrect. This is reported, not acted upon (read-only scope).
- `/proc/locks` reports the canonical lock's original flock caller as PID 1602788, which no longer
  has a `/proc` entry. This is not a defect in the lock: live PIDs 1602781 and 1602808 still hold
  fd 9 on inode 3146713, so the FLOCK remains genuinely held (generation 6). The stale PID number
  is a `/proc/locks` display artifact of an inherited open file description.
- Manifest records `gpu_touched: false` and `verified_at_launch: false` for the loaded `.so`.
  Recorded verbatim; not adjudicated in this read-only pass.

## Remaining claims / exclusions
- NOT verified: actual request throughput/quality of the running service (only HTTP 200 and
  process/GPU presence were checked).
- NOT verified: whether the running process's loaded code exactly matches TREE_HASH at runtime
  (manifest hash was read; runtime attestation not performed).
- NOT verified: contents of `/data/l3/prod-20260917T190831Z-1602589` namespace or logs.
- NOT performed (forbidden): any start/stop/kill/signal, flock acquisition, git mutation, writes to
  /opt, /data, /var/log, or any /tmp/opencode state file. Only this artifact was written.
- No reboot claim is made; the evidence positively contradicts a post-2026-09-15 reboot.

## Changed artifacts
- Created (only change): `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/POSTREBOOT-STATE-CHECK-20260917.md`

## Terminal state: DONE
