# PROD-STATE-PROBE-20260918-R2

Task: Read-only determination of the CURRENT production service state on port 30000 after the failed
M2-replacement window task, so the orchestrator can decide the next step (restore M1 vs continue M2).

Scope: Status probe only. No stop/start/restart/signal/kill, no GPU allocation, no config or git
changes. Only an HTTP GET to `/health` and `/v1/models` was issued to 127.0.0.1:30000 (and one GET to
the LAN IP). Evidence window: 2026-09-18 08:36:00Z–08:40:40Z UTC.

Result: **SERVICE_DOWN** — nothing is serving port 30000 (or any 3000x port). M1 was deliberately
stopped at 08:33:53Z by the failed window task; M2 was never started.

Terminal state: DONE

---

## Result detail

| Item | Finding |
|---|---|
| `:30000` listener | **NONE**. `ss -ltnp` shows only :53 and :22. `/proc/net/tcp` has no `:7530` (=30000). `fuser -n tcp 30000` exit 1. `curl /health` → HTTP 000 (curl exit 7, connection refused). |
| Live `--model-path` | **N/A** — no process exists to read. Last served model was M1 `/data/models/qwen35-9b-w4a16`. |
| M1 (`/data/models/qwen35-9b-w4a16`) | **NOT RUNNING**. 0 non-self processes. |
| M2 (`/data/models/omnicoder-9b-gptq-int4`) | **NOT RUNNING and NOT partially started**. 0 non-self processes; no listener on 30000/30001 or any other port; no M2 launcher script or log was ever created. |
| GPU | **IDLE**: 1 MiB used / 24124 MiB free / 24576 MiB total; **no compute apps**. |
| Canonical lock | `/tmp/opencode/gpu-3090.lock` is **stale** (owner PID dead) and the flock is **FREE**. |
| M1 stop time | 08:33:53Z (supervisor log) → graceful exit completed 08:34:19Z; state published `role=free` at 08:34:25Z. |
| M2 start attempt | **Never happened**. The worker died at 08:34:26Z on `AI_APICallError: Provider error 502 ... Provider unreachable` because it had just stopped the very provider (port 30000) it depended on. |

**Causal chain (from the live OpenCode log `/home/ubuntu/.local/share/opencode/log/opencode.log`), session `ses_f4c5ad6efffe7KANI5qHcdOEBS`, agent=devops-executor, model=worker:**

1. `08:33:09.987` — `cat /proc/1750878/environ >/tmp/m1_env.txt` (captures live M1 env).
2. `08:33:28` — reads `/proc/1750878/cmdline` and `/proc/1750878/environ`.
3. `08:33:49.856` — writes `/tmp/m1-rollback.sh` (NB: this script only STOPS M1; it does not start/restore M1 — see Defects).
4. `08:33:53.685` — executes `bash /tmp/opencode/prod-service-20260917/bin/stop.sh prod /opt/sglang/local-prod-v1.2.1-candidate` → **stops M1**.
5. `08:33:53.725` — M1 supervisor logs `WARN: supervisor exiting rc=0; releasing GPU lock`.
6. `08:34:19` — M1 server completes graceful exit (`kill_process_tree called: parent_pid=1750878`).
7. `08:34:25.872` — `state/gpu-owner.json` published `role=free, state=free, pid=null, note=stopped`.
8. `08:34:26.123` — worker stream error `AI_APICallError: Provider error 502 ... Provider unreachable` (the model provider endpoint ran on :30000).
9. `08:34:28.655` — `AI_APICallError: No available targets for combo: worker`. The window task dies **before** launching M2.

**Competing hypothesis tested and rejected:** "M2 partially started on a different port." Rejected — there is
no M2 process, no M2 script/log, and no non-22/53 listener. **Competing hypothesis tested and rejected:**
"M1 rolled back / restarted by the worker." Rejected — the same worker that stopped M1 errored out at
08:34:26, and no post-08:34 sglang process or new log directory exists (newest prod log dir is the
00:21:51Z run; newest file under `/tmp/opencode` is 00:42:45Z).

---

## Evidence (exact commands + real output)

### 1. Is anything listening on :30000?

```
$ ss -ltnp
State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess
LISTEN 0      4096      127.0.0.54:53        0.0.0.0:*
LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
LISTEN 0      4096   127.0.0.53%lo:53        0.0.0.0:*
LISTEN 0      4096            [::]:22           [::]:*
```

```
$ ss -ltn | grep -E ':3000[0-9]' ; echo "ss_grep_exit=$?"
ss_grep_exit=1        # no 3000x listener

$ grep -iE ':7530|:7531' /proc/net/tcp /proc/net/tcp6 ; echo "exit=$?"
exit=1                # 30000 (0x7530) and 30001 (0x7531) absent from kernel TCP tables

$ fuser -n tcp 30000 ; echo "exit=$?"
exit=1
```

**PID / cmdline:** none — there is no PID to report. No process makes up the service.

### 2. Which model is being served? HTTP codes/bodies

```
$ curl -s -m 5 -o /tmp/opencode/.r2-health-body -w 'HTTP_CODE=%{http_code} EXIT_CONNECT=%{exitcode}\n' http://127.0.0.1:30000/health
HTTP_CODE=000 EXIT_CONNECT=7
$ cat /tmp/opencode/.r2-health-body
cat: /tmp/opencode/.r2-health-body: No such file or directory

$ curl -s -m 5 -o /tmp/opencode/.r2-models-body -w 'HTTP_CODE=%{http_code}\n' http://127.0.0.1:30000/v1/models
HTTP_CODE=000
$ cat /tmp/opencode/.r2-models-body
cat: /tmp/opencode/.r2-models-body: No such file or directory

$ curl -s -m 5 -o /dev/null -w 'HTTP_CODE=%{http_code}\n' http://192.168.20.250:30000/health
HTTP_CODE=000
```

Both `curl -o` files were not created because the connection never opened (curl exit 7 = couldn't connect).
LAN IP confirmed as this host: `ip -brief addr` → `eth0 UP 192.168.20.250/24`.

There is no live argv to read. The **last** served model (recorded in the M1 server console at
`/tmp/opencode/prod-service-20260917/logs/prod-20260918T002151Z-1750622/server.console.log`) was:

```
'server_args={... 'model_path': '/data/models/qwen35-9b-w4a16', ...
 'host': '0.0.0.0', 'port': 30000, ...
 'served_model_name': '/data/models/qwen35-9b-w4a16', ...}
```

### 3. Is M1 running?

```
$ ps -eo pid,ppid,etimes,lstart,args | grep -i 'qwen35-9b-w4a16' | grep -v grep
exit_grep=1        # no match
```

Clean non-self `/proc` sweep (patterns assembled at runtime; excludes self+parent):

```
$ python3 - <<'PYEOF'
import os, glob
pats = ['qwen35' + '-9b-w4a16', 'omnicoder' + '-9b-gptq-int4', 'launch' + '_server']
me = os.getpid(); ppid = os.getppid(); rows = []
for d in glob.glob('/proc/[0-9]*'):
    pid = int(d.split('/')[-1])
    if pid in (me, ppid): continue
    try:
        comm = open(d + '/comm').read().strip()
        cl = open(d + '/cmdline','rb').read().replace(b'\0',b' ').decode('utf-8','replace').strip()
    except Exception: continue
    for p in pats:
        if p in cl: rows.append((pid, comm, cl[:120]))
print("matches (pid, comm, cmdline):")
for r in rows: print("  ", r)
print("total non-self matches =", len(rows))
PYEOF
matches (pid, comm, cmdline):
total non-self matches = 0
```

**M1 PIDs: NONE.** The last M1 PIDs were server pid 1750878 / supervisor pid 1750851; both are dead
(`ls -la /proc/1750851` → `No such file or directory`).

### 4. Is M2 running (or partially started)?

Same sweep as §3 → **0 matches** for `omnicoder-9b-gptq-int4`. No M2 process, and no listener on any
port other than 22/53 (see §1). There is no M2 log directory and no M2 launcher anywhere:

```
$ find /tmp/opencode -iname '*omnicoder*' -o -iname '*m2*'
/tmp/opencode/m2_check.py
/tmp/opencode/m2_check.log
# (all other hits are unrelated source-tree filenames such as lfm2.py, internlm2.py, minimax_m2.py)

$ find /tmp/opencode/prod-service-20260917 -iname '*omnicoder*' -o -iname '*m2*'
(no output)

$ ps -ef | grep -i omnicoder | grep -v grep
exit_grep=1
```

`m2_check.py`/`m2_check.log` are dated Sep 16 (a weight-median CPU probe of the M2 safetensors), not an
M2 server start. The 48 GiB `/data/models/omnicoder-9b-gptq-int4` directory exists but was never loaded.

### 5. GPU state

```
$ nvidia-smi
|   0  NVIDIA GeForce RTX 3090 ...  P8  20W / 350W |       1MiB /  24576MiB |      0%   Default |
| Processes: No running processes found

$ nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv
pid, process_name, used_gpu_memory [MiB], gpu_uuid
(empty)

$ nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv
memory.used [MiB], memory.free [MiB], memory.total [MiB]
1 MiB, 24124 MiB, 24576 MiB
```

**Total used 1 MiB / free 24124 MiB / total 24576 MiB. No PID holds GPU memory.**

### 6. Lock state

`/tmp/opencode/gpu-3090.lock` (verbatim):

```
{"owner": "supervise-prod-prod-20260918T002151Z-1750622", "pid": 1750851, "generation": 19, "acquired": "2026-09-18T00:21:51Z"}
```

- Owner PID 1750851 is **dead** (`/proc/1750851` absent).
- The flock is **not held** (read-only non-blocking test):
  ```
  $ python3 -c "import fcntl;f=open('/tmp/opencode/gpu-3090.lock');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);print('LOCK_FREE');fcntl.flock(f,fcntl.LOCK_UN)"
  LOCK_FREE
  ```
- This is the same 128-byte file seen before the incident (mtime 2026-09-18 00:21:51Z, unchanged).
- Other `*.gpu.lock` files (`fleet-forensics-20260916`, `fleet-throughput-forensics-20260916`,
  `m1-formal-graph-on-20260916`) are all Sep 16 and empty/stale.

`/tmp/opencode/prod-service-20260917/state/gpu-owner.json` (verbatim, updated 08:34:25Z):

```json
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "free",
  "state": "free",
  "pid": null,
  "port": null,
  "run_id": "",
  "l3_namespace": "",
  "tree": "",
  "identity": "",
  "lock_generation": 19,
  "updated_at_utc": "2026-09-18T08:34:25Z",
  "note": "stopped"
}
```

### 7. Recent in-progress M2 launcher scripts / logs under /tmp/opencode

There is **no M2 launcher script and no M2 serve log**. Newest files under `/tmp/opencode` (top of
`ls -lat`):

```
2026-09-18 00:42:45  qwen3coder-impl-20260918/  (dir; contains only probe.py)
2026-09-18 00:24:13  PROD-UP-R1-hold.sh
2026-09-18 00:24:09  PROD-UP-R1-smoke.json
2026-09-18 00:24:03  PROD-UP-R1-start.out
2026-09-18 00:21:51  gpu-3090.lock
```

The only files created **during** the incident window (08:33–08:34) are in `/tmp` (not
`/tmp/opencode`), and all are M1-named:

```
$ stat /tmp/m1_env.txt      -> Birth 2026-09-18 08:33:09, Modify 08:33:09
$ stat /tmp/m1-rollback.sh  -> Birth 2026-09-18 08:33:49, Modify 08:33:49
$ stat /tmp/b15-probe.log   -> Birth 2026-09-15 22:29:58, Modify 2026-09-18 08:34:12
```

- `/tmp/m1_env.txt` — the captured M1 environment (`SGLANG_PORT=30000`, `MODEL_PATH=/data/models/qwen35-9b-w4a16`, `SGLANG_RUN_ID=prod-20260918T002151Z-1750622`).
- `/tmp/m1-rollback.sh` — 45-line script; **it only stops M1** (calls `stop.sh`). It contains no start/exec of `launch_server`. **It is NOT a restore command.**
- `/tmp/b15-probe.log` — a 102 MB M1 forward-pass telemetry stream; last line at Unix ts 1789720452 = `Fri Sep 18 08:34:12 UTC 2026` (M1's last decode). No M2 lines.

Last 20 lines of the only 08:00-window prod log (`.../prod-20260918T002151Z-1750622/supervisor.log`, full file):

```
[00:21:51] canonical GPU lock ACQUIRED generation=19 owner=supervise-prod-prod-20260918T002151Z-1750622 pid=1750851
[00:21:51] supervisor launching prod on port 30000 (tree=/opt/sglang/local-prod-v1.2.1-candidate)
[00:22:15] /proc/1750878/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
[00:24:03] COLD START (launch -> /health 200): 132.0s
[00:24:03] === prod UP: pid=1750878 port=30000 cold_start=132.0s ===
[08:33:53] WARN: supervisor exiting rc=0; releasing GPU lock
```

Last lines of M1 `server.console.log`:

```
[2026-09-18 08:34:17] Gracefully exiting... Remaining number of requests 0. Remaining requests remaining_rids=[].
[rank0]:[W918 08:34:18] Warning: destroy_process_group() was not called before program exit...
[2026-09-18 08:34:19] kill_process_tree called: parent_pid=1750878, include_parent=False, pid=1750878
```

### 8. The recorded M1 launch command (verbatim)

**Canonical/service entrypoint used by the production scaffold (this is what the orchestrator should use
to restore M1):**

```
bash /tmp/opencode/prod-service-20260917/bin/start.sh prod
```

or, explicitly selecting the frozen tree:

```
bash /tmp/opencode/prod-service-20260917/bin/start.sh prod /opt/sglang/local-prod-v1.2.1-candidate
```

`start.sh` runs preflight, refuses if the port/GPU is busy, allocates a unique L3 namespace, then hands
off to `bin/supervise.sh`, which holds `/tmp/opencode/gpu-3090.lock` and invokes the frozen launcher:

```
setsid env \
  SGLANG_PORT=30000 \
  SGLANG_PROFILE=perf \
  SGLANG_RUN_ID=<new unique run id> \
  SGLANG_L3_ROOT=/data/l3 \
  SGLANG_LOG_DIR=<log dir> \
  bash /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh
```

**The frozen launcher's exact M1 server argv** (from `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh`,
`ARGS` array, `SGLANG_PROFILE=perf` ⇒ `L2_GB=32`), which `exec`s verbatim:

```
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/qwen35-9b-w4a16 \
  --host 0.0.0.0 --port 30000 \
  --tp-size 1 \
  --mem-fraction-static 0.92 \
  --max-total-tokens 524288 \
  --context-length 131072 \
  --max-running-requests 8 \
  --max-mamba-cache-size 48 \
  --kv-cache-dtype fp8_e4m3 \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --enable-hierarchical-cache \
  --hicache-write-policy write_back \
  --hicache-storage-backend extent \
  --hicache-storage-prefetch-policy wait_complete \
  --hicache-size 32 \
  --enable-ready-horizon \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --export-metrics-to-file \
  --export-metrics-to-file-dir <LOG_DIR> \
  --disable-prefill-cuda-graph
```

Corroborating single-line record of the same M1 argv for port 30000 (from
`/tmp/opencode/mamba-sweep-20260918/phase2/prod-argv.txt`):

```
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969 --disable-prefill-cuda-graph
```

Required launch env (from `/tmp/m1_env.txt` and `launcher/launch.sh`):
`PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`,
`CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587`, `CUDA_HOME=/usr/local/cuda-12.9`.
Do **not** call `launch_server` directly without the launcher; the tree's editable venv binding resolves
`sglang` to the live WIP workspace unless `PYTHONPATH` is set (noted by the scaffold's own preflight).

### 9. Negative self-checks

1. **No listener on any 3000x port** — `ss -ltnp` output above lists only 22/53; `ss -ltn | grep ':3000[0-9]'` exit 1; `/proc/net/tcp` has no `:7530`. A glob miss is not used as proof; both the socket table and `/proc/net/tcp` were inspected.
2. **No process holds GPU memory** — `nvidia-smi --query-compute-apps` returned only the CSV header (empty rows); GPU shows 1 MiB used / no running processes.
3. **No M1, M2, or launch_server process exists** — non-self `/proc/*/cmdline` sweep printed `total non-self matches = 0`. (An earlier naive `ps -ef | grep -c` returned 2 for each pattern; those were self-matches from my own probe shell's command line, disproven by the runtime-assembled-pattern sweep.)
4. **No M2 launch attempt** — no M2-named file under `/tmp/opencode/prod-service-20260917`, no process, no port, no log.
5. **Read-only compliance** — I did not stop/start/signal/configure anything, did not run `nvidia-smi` in a memory-allocating mode, did not modify git, and did not run the `m1-rollback.sh` script. The only writes were this single artifact and (transiently) an attempted curl output path that was never created.

---

## Defects / blockers

1. **`/tmp/m1-rollback.sh` is misnamed and dangerous as a recovery tool.** It only stops M1
   (`stop.sh prod` / `kill -TERM 1750878`); it contains **no start/restore path**. If the orchestrator
   treats it as the "recorded M1 launch command," it will stop an already-stopped service and restore
   nothing. Use `bin/start.sh prod` (or the exact argv in §8) instead.
2. **The failed window task stopped production before it could start M2.** Its own logs show the worker
   executed `stop.sh` at 08:33:53 and then died at 08:34:26 with
   `AI_APICallError: Provider error 502 ... Provider unreachable` — i.e. the worker depended on the
   LLM provider served on :30000, so stopping M1 killed the worker's own control channel. This confirms
   the orchestrator's hypothesis and the mechanism note in the ledger.
3. **Stale lock metadata.** `gpu-3090.lock` still names dead owner pid 1750851 / generation 19, and
   `gpu-owner.json` already says `free`. The file is cosmetic here (flock is free), but a restore path
   that reads the lock owner rather than testing the flock could mis-detect an owner.
4. **No M2 artifact lineage.** No M2 launch script, no M2 serve log, and no M2 launch window log were
   ever produced. M2 was never brought up even partially.

## Remaining claims / exclusions

- **Not established:** whether `start.sh prod` will succeed right now (that would require executing it,
  which is out of scope). GPU/port/lock preconditions are all clear, but the frozen-tree identity gate
  and cold start were not exercised.
- **Not established:** whether M2 can serve at all; no evidence of an M2 launch attempt was found.
- **Not claimed:** M2 provenance/identity (separate MLINE artifacts address that).
- **Excluded from scope:** restarting M1 (this probe is read-only), any provider/port-30000 recovery
  action, and any M2 cutover.
- `docker` is not installed (`docker: command not found`), so no container-based service could be
  hidden; excluded as a source of a listener.
- `nvidia-smi` reported "No running processes" and `/dev/nvidia*` device nodes exist, so the absence of
  GPU memory holders is genuine, not a permissions artifact.
