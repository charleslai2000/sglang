# PROD-STATE-CHECK-R3-20260918

Terminal state: DONE

## Task

Bounded, READ-ONLY host-state probe (task `PROD-STATE-CHECK-R3-20260918`) to establish the
current factual state of the production service on `:30000` against the possibility that the
concurrent RCA task `M2-CONCURRENCY-DEGRADATION-RCA-20260918` had taken production down and
either (a) was still actively working the GPU test window or (b) abandoned it.

Items 1-8: liveness; listeners/owning pids; sglang processes; GPU state + compute apps; canonical
lock holder + inode; scaffold state and newest run/console log; evidence of an active window owner;
any scratch-port (3016x) server.

## Scope

Read-only. No process signals, no start/stop of production, no GPU acquisition, no inference load.
Only the permitted `GET /health` and `GET /v1/models` on `:30000` were issued, plus one
`curl` PID-agnostic sleep to observe state transition. No writes outside this result artifact.
Read-only `ps`, `ss`, `nvidia-smi`, `/proc`, `lsof`, `fuser`, `find`, `stat`, `cat`.

## Result

**The premise "production is down" was true at the instant the probe began, but only transiently:
production was in the middle of a cold-start restart that was already in flight and actively owned.
By 18:39:31Z production was UP and serving.**

(a) **Is production `:30000` currently UP or DOWN?**
**UP (now), and it was transiently DOWN mid-restart when the probe started.**
Observed HTTP codes:

| time (UTC) | `127.0.0.1:30000/health` | `127.0.0.1:30000/v1/models` | LAN `192.168.20.250:30000/health` |
|---|---|---|---|
| 18:37:52 | 000 | 000 | 000 |
| 18:38:25 | 000 | (not re-issued) | (n/a) |
| 18:39:44 | 200 | 200 | (n/a) |
| 18:40:05 | 200 | (n/a) | (n/a) |
| 18:40:05 | 200 | 200 | 200 |

At 18:37:52 there was **no listener on `:30000`** (`ss -ltnp` matched nothing), which is why the
code was `000` (connection refused / no listener), not an application error. The listener appeared
between 18:38:44 and 18:39:44; the supervisor recorded `/health` 200 at 18:39:31 (cold start 106.8 s).
Final state: listener `0.0.0.0:30000` owned by `python` pid **1840571**.

(b) **Is anything currently holding the GPU / on a scratch port (window still ACTIVE), or is the box idle?**
The box is **NOT idle, and the test window is NOT active.** The GPU is now held by **production M2**:

- `nvidia-smi` (final): `19067 MiB used / 5058 MiB free, 100% util`
- compute apps: `1840571` `/opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python` (300 MiB) and
  `1841198` `sglang::scheduler` (18752 MiB)
- No server is bound to any scratch port: `ss -ltnp` shows only `:30000`; `:30164`, `:30165`, `:30166`
  are unbound. The last RCA scratch server on `:30164` (pid 1838720) had already exited at 18:36:35Z
  (`/proc/1838720` absent).
- Canonical GPU lock `/tmp/opencode/gpu-3090.lock` (inode **3146713**) is held, owner
  `supervise-m2-m2-20260918T183744Z-1840331`, pid 1840544, generation 1.

(c) **If production is DOWN: any sign of a live owner still working the window, or abandoned/left-down?**
Production is not down now, so this is answered historically for the 18:37:52 DOWN instant:
**there was a live owner actively restoring it — not abandoned.** The DOWN instant was a
106.8 s cold-start gap, not a left-down service. Evidence of a live owner:

- A fresh production start driver was spawned at **18:37:25** (`timeout 600 bash bin/start.sh m2`,
  pid 1840328, cwd `/tmp/opencode/prod-service-20260917`) by the active opencode session pid 1758196.
- `supervise.sh` (pid 1840544) acquired the canonical lock at **18:37:45** and launched
  `sglang.launch_server` on port 30000 (pid 1840571, started 18:37:44).
- The supervisor log records the full successful lifecycle, culminating in
  `[18:39:31] === m2 UP: pid=1840571 port=30000 cold_start=106.8s ===`, and `state/ready/m2.ready`
  was created / `gpu-owner.json` flipped to `"state": "serving"` at 18:39:31.

The RCA test window itself had already ended before the restart: the last RCA scratch server exited
at 18:36:35Z, and the newest file under `/tmp/opencode/M2-RCA-20260918/` is stamped 18:36:35.

## Evidence

### E1 — Liveness (step 1)
First probe (18:37:52Z):
```
=== /health 127.0.0.1:30000 ===
000
=== /v1/models 127.0.0.1:30000 ===
000
=== /health LAN 192.168.20.250:30000 ===
000
```
Second (18:38:19Z): health `000`, `/v1/models` `000`.
Post-recovery (final):
```
127.0.0.1:30000/health -> 200
127.0.0.1:30000/v1/models -> 200
192.168.20.250:30000/health -> 200
```

### E2 — Listeners and owning pids (step 2)
First probe (18:37:52Z) — nothing matching:
```
=== ss listeners ===
NO_MATCH_SS
=== full ss (all tcp listen) ===
State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess
LISTEN 0      4096      127.0.0.54:53        0.0.0.0:*
LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
LISTEN 0      4096   127.0.0.53%lo:53        0.0.0.0:*
LISTEN 0      4096            [::]:22           [::]:*
```
Final (18:40:05Z):
```
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1840571,fd=68))
```

### E3 — sglang processes with full command lines (step 3)
First probe (18:37:52Z): **none** (`pgrep -af 'sglang.launch_server|sglang::scheduler'` matched only
the probe shell itself; the later full `ps | grep -iE 'sglang|launch_server|scheduler'` at 18:38:09
showed the launcher still in its identity-preflight stage, pid 1840571, argv below).
Final:
```
1840571 /opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/m2-20260918T183744Z-1840331 --disable-prefill-cuda-graph
1841198 sglang::scheduler
```
Port used: **30000**. No sglang process used a 3016x port at probe time.

### E4 — GPU (step 4)
First `nvidia-smi` (18:37:52Z) — allocated but not yet initialized by CUDA, which is why the probe
initially looked like an idle box:
```
|   0  NVIDIA GeForce RTX 3090        On  |   00000000:00:10.0 Off |                  N/A |
| 41%   42C    P8             20W /  350W |       1MiB /  24576MiB |      0%      Default |
| Processes: No running processes found
pid, process_name, used_gpu_memory [MiB]      <- empty
```
Final (after recovery):
```
19067 MiB, 5058 MiB, 100 %        (memory.used, memory.free, utilization.gpu)
1840571, /opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python, 300 MiB
1841198, sglang::scheduler, 18752 MiB
```

### E5 — Canonical lock (step 5)
```
stat: /tmp/opencode/gpu-3090.lock inode=3146713 size=123 mtime=2026-09-18 18:37:45
content: {"owner": "supervise-m2-m2-20260918T183744Z-1840331", "pid": 1840544, "generation": 1, "acquired": "2026-09-18T18:37:45Z"}
/proc/locks: 1: FLOCK  ADVISORY  WRITE 1840551 08:01:3146713 0 EOF
lsof:  bash   1840544 ubuntu 9u REG 8,1 123 3146713 /tmp/opencode/gpu-3090.lock
       python 1840571 ubuntu 9u REG 8,1 123 3146713 /tmp/opencode/gpu-3090.lock
fuser: 1840544 bash, 1840571 bash(transient)/python  (transient holders not persistent)
```
Lock file **inode = 3146713**, currently **HELD** (FLOCK WRITE).
Note: `/proc/locks` reports holder PID **1840551**, and `/proc/1840551` no longer exists
(`ls: cannot access '/proc/1840551'`). lsof/fuser and `/proc/<pid>/fd/9` show the live descriptors:
`/proc/1840544/fd/9 -> /tmp/opencode/gpu-3090.lock` and `/proc/1840571/fd/9 -> /tmp/opencode/gpu-3090.lock`.
Interpretation (inference, marked): `flock -n 9` is invoked as an external utility inside
`gpu_lock_acquire`; the flock utility exits, but the flock(2) lock remains attached to the shared
open file description inherited by supervisor 1840544 and its child server 1840571. So the
`/proc/locks` PID is the (exited) utility's PID and is not the effective holder. The lock is
genuinely held by 1840544/1840571.

Anomaly (observation, not central): `state/runs/prod.run` from the earlier prod run recorded
`lock_generation=3`, while the current lock file and supervisor log both say `generation=1`, and the
RCA run at 18:31:41 also logged `generation=1`. The generation counter is therefore not monotonic
across the 18:37 restart; the lock file was rewritten from generation 1. The presence and exclusivity
of the flock is unaffected (mutual exclusion is inode/fd based, not counter based).

### E6 — Scaffold state (step 6)
`/tmp/opencode/prod-service-20260917/state/gpu-owner.json` at first read (18:37:45Z) — mtime
`2026-09-18 18:37:45.062`:
```
{"gpu":"GPU-2e3ed202-...","role":"m2","state":"held","pid":1840571,"port":30000,
 "run_id":"m2-20260918T183744Z-1840331","l3_namespace":"","tree":"/opt/sglang/local-prod-v1.2.1-candidate-M2",
 "identity":"LOCAL-PROD-v1.2.1-M2","lock_generation":1,"updated_at_utc":"2026-09-18T18:37:45Z","note":"starting"}
```
Same file at 18:39:31Z (after recovery) — inode changed, mtime `2026-09-18 18:39:31.857`:
```
... "state": "held", "pid": 1840571, "port": 30000, "run_id": "m2-20260918T183744Z-1840331",
    "lock_generation": 1, "updated_at_utc": "2026-09-18T18:39:31Z", "note": "serving"
```
Newest run directory: `/tmp/opencode/prod-service-20260917/logs/m2-20260918T183744Z-1840331`
(created 18:37:45). `server.console.log` tail (final):
```
=== LOCAL-PROD-v1.2.1-M2 launcher (M2; L3/HiCache EXPLICITLY DISABLED) ===
tree=/opt/sglang/local-prod-v1.2.1-candidate-M2
model=/data/models/omnicoder-9b-gptq-int4 port=30000
...
[2026-09-18 18:39:45] Prefill batch, #new-seq: 1, #new-token: 21, #cached-token: 0 ...
[2026-09-18 18:39:45] Decode batch, #running-req: 1 ...
[2026-09-18 18:39:45] INFO: 127.0.0.1:xxxxx - "GET /health HTTP/1.1" 200 OK
[2026-09-18 18:39:45] INFO: 127.0.0.1:xxxxx - "GET /v1/models HTTP/1.1" 200 OK
```
`supervisor.log` (complete):
```
[18:37:45] canonical GPU lock ACQUIRED generation=1 owner=supervise-m2-m2-20260918T183744Z-1840331 pid=1840544
[18:37:45] supervisor launching m2 on port 30000 (tree=/opt/sglang/local-prod-v1.2.1-candidate-M2)
[18:38:08] /proc/1840571/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
[18:39:31] COLD START (launch -> /health 200): 106.8s
[18:39:31] === m2 UP: pid=1840571 port=30000 cold_start=106.8s ===
```
Newest state file mtimes: `state/gpu-owner.json` 18:39:31, `state/runs/m2.run` 18:39:31,
`state/ready/m2.ready` 18:39:31, `state/pids/*` 18:37:45.

### E7 — Evidence of an active window owner (step 7)
At the first pass (18:37:55Z, window ~last 30 min), newest `/tmp/opencode` entries:
```
18:37:45.064  /tmp/opencode/prod-service-20260917/state
18:37:45.062  /tmp/opencode/prod-service-20260917/state/gpu-owner.json
18:37:45.054  /tmp/opencode/prod-service-20260917/logs/m2-20260918T183744Z-1840331/server.console.log
18:37:45.027  /tmp/opencode/gpu-3090.lock
18:36:35.703  /tmp/opencode/M2-RCA-20260918/logs/hicache-iso-30164-.../driver.log
18:36:35.703  /tmp/opencode/M2-RCA-20260918/hicacheIsoLaunch.out
18:36:30.847  /tmp/opencode/M2-RCA-20260918/logs/hicache-iso-30164-.../server.console.log
```
So the **newest activity was the production restart (18:37:45)**, and the newest RCA activity was
18:36:35. `gpu-owner.json` mtime at first read = **18:37:45**; after recovery = **18:39:31**.
The restart driver's parent is the live opencode session:
```
1840328 1758196  /bin/bash -c cd /tmp/opencode/prod-service-20260917 timeout 600 bash bin/start.sh m2 2>&1 | tail -25 echo "START_RC=$?"
1758196 298244   opencode            (cwd of 1840331 -> /tmp/opencode/prod-service-20260917)
```
(pid 1758196 is the same opencode session that is the parent of this probe's own shell; this
establishes that the restore was initiated by the active orchestration, not by a stray/abandoned
process — inference from process parentage.)

RCA window end evidence (`/tmp/opencode/M2-RCA-20260918/`):
```
driver.log tail:
RCA_UP pid=1838720 run_id=hicache-iso-30164-20260918T183141Z-1838693 cold_start_s=98 maxtotal=262144
SERVER_EXITED pid=1838720 2026-09-18T18:36:35Z
```
`pgrep -af 'M2-RCA'` -> `NONE`; no process references any prior RCA run pid.

### E8 — Scratch/experiment port (step 8)
No sglang server is currently on any 3016x port. Only `:30000` is bound. Last scratch run was on
`:30164`:
```
launch_argv.txt (last RCA scratch run):
ARGV: .../python -u -m sglang.launch_server ... --port 30164 ... --enable-cache-report --enable-hierarchical-cache --hicache-write-policy write_back --hicache-size 32
server.pid = 1838720   -> ps: PID_NOT_RUNNING ; /proc/1838720 absent
```
Start time of that scratch server: launched at ~18:31:41Z, exited 18:36:35Z (it is gone now, so no
live `ps -o lstart=` is available for it; the launch line and exit line are the timeline evidence).

### E9 — Stop/restore handoff (timeline anchor)
`/tmp/opencode/M2-RCA-20260918/stop-prod-m2-r3.txt`:
```
[18:17:58] m2: terminating supervisor pid=1835482 (SIGTERM; it will release the GPU lock)
[18:17:58] m2: stopping owned server pid=1835509 (SIGTERM, graceful)
[18:18:19] m2 stopped; GPU released; state published as free
```
This confirms production was **deliberately stopped at 18:17:58Z** to open the RCA GPU window, and
the RCA artifact `M2-CONCURRENCY-DEGRADATION-RCA-20260918.md` still carries
`Restored-state record: PENDING (production currently stopped for the warm-control window)`.

## Defects or blockers

No probe blockers. READ-ONLY constraints were honored (no signals, no start/stop, no GPU acquire,
no load).

Discrepancies observed (report, not fix):
1. `/proc/locks` names a non-existent holder PID 1840551 for inode 3146713, while the live lock is
   held via fd 9 by 1840544/1840571. Explained above (external `flock` utility's PID). Cosmetic, but
   anyone parsing `/proc/locks` alone would misidentify the lock owner.
2. Lock `generation` reset to 1 at the 18:37 restart despite an earlier recorded `lock_generation=3`
   (prod.run). Exclusivity is intact; the counter is not monotonic.
3. The RCA result artifact still states production is stopped and "Restored-state record: PENDING",
   which is now stale: production was restarted at 18:37:25 and reached `/health` 200 at 18:39:31.

## Remaining claims or exclusions

Established:
- Production `:30000` was DOWN at 18:37:52-18:38:25 (no listener; HTTP `000`) **only because a
  supervised restart was in its cold-start window**, and is UP now (HTTP 200 on health, models, LAN).
- The GPU is owned by production M2 (sglang::scheduler pid 1841198, 18752 MiB, 100% util).
- No scratch port is bound; the RCA scratch server (pid 1838720, port 30164) exited at 18:36:35Z.
- Canonical lock inode 3146713 is held by the production supervisor (owner
  `supervise-m2-m2-20260918T183744Z-1840331`, supervisor pid 1840544, generation 1).
- The restart was owned by the active opencode session (pid 1758196); no evidence of an abandoned
  down state.

Not established / exclusions:
- I did not sample continuously across 18:37:52-18:39:31; the exact listener-appearance instant is
  bounded rather than exact (no listener at 18:38:25/18:38:44-ish; listener present by 18:39:44;
  supervisor /health 200 logged 18:39:31).
- GPU utilization and memory are instantaneous samples; no load was generated, so "serving" is
  asserted from the `/health` 200 and supervisor ready record, not from a chat completion.
- I did not verify whether the concurrently acting orchestrator intended this restart (authority
  question), only that the process lineage is the live opencode session.
- Historical crash/kill attribution of the earlier 18:17 stop is out of scope; only the recorded
  SIGTERM handoff in `stop-prod-m2-r3.txt` is asserted.

## Terminal state: DONE
