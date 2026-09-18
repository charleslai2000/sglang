# KILLER-ATTRIBUTION-RECON-20260918

Terminal state: DONE

## Task

STRICTLY READ-ONLY forensic attribution of the process tree(s) associated with the
`mamba-sweep` experiment (`/tmp/opencode/mamba-sweep-20260918/`) and any identity-checked kill
actions against production SGLang on `:30000`. Attribute WHO is doing the killing using
process-lineage evidence only. No process is started, stopped, signalled, or modified; no write
occurred except this result artifact.

## Scope

- READ-ONLY. Observed via `ps`, `ss`, `curl` GET, `nvidia-smi`, `pgrep`, `cat`/`ls`/`stat`/`find`,
  `/proc/<pid>/{status,cmdline,fd}`, and `opencode.log` (read). No signals, no `pkill`/`killall`/
  `kill`, no `systemctl`, no lock acquisition, no writes outside this artifact, no git mutation.
- `/opt`, `/data`, `/var/log` were not touched.
- Attribution is limited to what live or preserved process lineage/artifacts establish.

## Result

- **`:30000` is DOWN.** At first read (00:03:58Z) and final read (00:06:24Z): `/health`=000,
  `/v1/models`=000, LAN `192.168.20.250:30000/health`=000. No listener on `:30000` at any read.
- **The running sweep belongs to the single live agent-host process `opencode` PID 1644932**
  (tty `pts/0`, started Thu 2026-09-17 20:44:27). Top-level ancestor chain:
  `sshd /usr/sbin/sshd -D` (PID 1272, PPID 1) → `sshd: ubuntu [priv]` (298128) →
  `sshd: ubuntu@pts/0` (298243) → `-bash` (298244) → **`opencode` (1644932)** →
  `bash -c ...bash run_cell.sh 48...` (1743336) → `run_cell.sh` (1743340) →
  `cell_supervise.sh` (1743344) → `sglang.launch_server --port 30160` (1743374).
- **There is exactly ONE live `opencode` host process on this host** (`pgrep -c -x opencode` = 1),
  with one controlling login session (`pts/0`). No second `opencode`/`node`/`bun` agent host is
  running. Both "automated sessions" therefore share one PTY/SSH session; they are logical
  sub-sessions within PID 1644932, not separable as distinct live process trees.
- **No M-line gate is running.** The named `.memory/agents/` artifacts
  (`GGUF-GATE-M4M3-20260918`, `PROD-STATE-CHECK-R2-20260918`, `G-COMMIT-ROSTER-VERIFY-20260918`,
  `R5-GATEA-CLOSURES-COMMIT-20260918`) exist only as on-disk files; none has a live process. The
  only cmdline matches for `gguf|sampled-smoke|run_sampled_smoke|3090-dev/gates|M4|M3` are
  **false positives** (case-insensitive `M3` matching `fp8_e4m3` / `mamba-ssm` text inside the
  sweep's own launch_server argv).
- **The per-cell sweep machinery does NOT kill `:30000`.** `run_cell.sh` only identity-checks and
  signals its own cell server PID (`state/cell-$CELL.pid`) on its own `$PORT` (30160). There is no
  `:30000` / `stop.sh prod` / `prod-20260917` target anywhere in `run_cell.sh` or
  `cell_supervise.sh`. The :30000-killing action is attributed (by the live-preserved P4 artifact,
  not independently reproducible now) to a `bash -c` kill script *launched from within the
  1644932 opencode tree*, not to the sweep cell scripts themselves.
- **State transition observed during recon:** sweep5's own cell self-stopped at ~00:06:10–00:06:18
  (`identity OK`; `load_rc=143`; server `kill_process_tree ... include_parent=False`; supervisor
  "releasing GPU lock"). By 00:06:24 there were no sweep processes and `nvidia-smi` showed no
  compute apps. The exact signaler of sweep5 is not established (processes are gone) → UNKNOWN.

## Evidence

### A1 — HTTP status (raw)
```
=== A1a: 127.0.0.1:30000/health ===
000
=== A1b: 127.0.0.1:30000/v1/models ===
000
=== A1c: 192.168.20.250:30000/health ===
000
```
Final read (00:06:24Z):
```
http://127.0.0.1:30000/health -> 000
http://127.0.0.1:30000/v1/models -> 000
http://192.168.20.250:30000/health -> 000
```

### A2 — `ss -ltnp` (raw, first read)
```
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      2048         0.0.0.0:30160      0.0.0.0:*    users:(("python",pid=1743374,fd=68))
LISTEN 0      4096      127.0.0.54:53         0.0.0.0:*
LISTEN 0      4096       127.0.1.1:46367      0.0.0.0:*    users:(("sglang::schedul",pid=1743490,fd=83))
LISTEN 0      4096         0.0.0.0:22         0.0.0.0:*
LISTEN 0      4096   127.0.0.53%lo:53         0.0.0.0:*
LISTEN 0      4096       127.0.1.1:39233      0.0.0.0:*    users:(("sglang::schedul",pid=1743490,fd=79))
LISTEN 0      4096       127.0.1.1:38445      0.0.0.0:*    users:(("sglang::schedul",pid=1743490,fd=87))
LISTEN 0      4096            [::]:22            [::]:*
LISTEN 0      4096               *:33175            *:*    users:(("sglang::schedul",pid=1743490,fd=73))
```
No `:30000` listener. (`:30160` owner 1743374; `sglang::scheduler` 1743490 holds ephemeral
loopback listeners.) Final read: `ss ... | grep -E ':30000|:30160'` → empty (both gone).

### A3 — `pgrep -af 'sglang|launch_server|run_cell|cell_supervise|load.py|supervise.sh|stop.sh|start.sh'` (raw)
```
1743336 /bin/bash -c cd /tmp/opencode/mamba-sweep-20260918/phase2 RID=$(cat state/cell-48.run_id); NS=$(cat state/cell-48.namespace) echo "=== CELL 48 RETRY run_id=$RID ns=$NS $(date -u) ===" bash run_cell.sh 48 "$RID" "$NS" 30160 16 2>&1 | tee logs-cell-48-sweep5.out echo "CELL48_RC=${PIPESTATUS[0]}" date -u
1743340 bash run_cell.sh 48 sweep5-mamba48-20260918T000006Z-1743252 /data/l3/sweep5-mamba48-20260918T000006Z-1743252 30160 16
1743344 bash /tmp/opencode/mamba-sweep-20260918/phase2/cell_supervise.sh 48 sweep5-mamba48-20260918T000006Z-1743252 /data/l3/sweep5-mamba48-20260918T000006Z-1743252 /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-48-sweep5-mamba48-20260918T000006Z-1743252 30160
1743374 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30160 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-48-sweep5-mamba48-20260918T000006Z-1743252 --disable-prefill-cuda-graph
1743489 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -c from multiprocessing.resource_tracker import main;main(27)
1743490 sglang::scheduler
1743491 sglang::detokenizer
1743829 /bin/bash -c for i in $(seq 1 10); do ... pgrep -af 'run_cell.sh|cell_supervise.sh|sglang.launch_server' ... done
1744116 ...torch._inductor.compile_worker... --parent=1743490 ...
1744156 /opt/sglang/.../python /tmp/opencode/mamba-sweep-20260918/phase2/load.py --base http://127.0.0.1:30160 ...
```
No `stop.sh`, no `start.sh`, no `supervise.sh` process at read time.

### A4 — `nvidia-smi` (raw)
```
pid, process_name, used_gpu_memory [MiB]
1743374, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1743490, sglang::scheduler, 22614 MiB
index, name, memory.total [MiB], memory.used [MiB], memory.free [MiB]
0, NVIDIA GeForce RTX 3090, 24576 MiB, 22989 MiB, 1136 MiB
```
Final read (00:06:24Z): no compute apps `pid, process_name, used_gpu_memory [MiB]` (empty).

### A5 — `cat` + `stat` of lock (raw)
```
{"owner": "sweep-cell-48-sweep5-mamba48-20260918T000006Z-1743252", "pid": 1743344, "generation": 16, "acquired": "2026-09-18T00:00:09Z"}
Modify: 2026-09-18 00:00:09.631378373 +0000
Access: 2026-09-18 00:00:09.638378580 +0000
Birth:  2026-09-16 11:57:06.337122290 +0000
```
Note: after sweep5 self-stopped (00:06:18) this file content is stale relative to live state.
Whether the flock is presently free is **UNKNOWN** — a read-only flock probe would require
acquiring the lock, which is forbidden by this task.

### B6 — `/tmp/opencode/mamba-sweep-20260918/phase2/` and `logs/` (names + mtimes)
phase2: `cell_supervise.sh` 23:13:20, `load.py` 23:18:57, `run_cell.sh` 23:19:05,
`prod-argv.txt` 23:13:41, `prod-env-relevant.txt` 23:13:41, `state/` 00:02:00,
`logs-cell-48-sweep5.out` 00:02:00. `logs/` contains cell dirs for sessions:
`cell-48-sweep-mamba48-...1726566` (23:16),
`cell-48-sweep2-...1727975` (23:29), `cell-56-sweep2-...1727975` (23:40),
`cell-64-sweep2-...1727975` (23:44), `cell-64-sweep2-...1736234` (23:49),
`cell-64-sweep3-...1737059` (23:52), `cell-48-sweep4-...1740204` (23:59),
`cell-48-sweep5-...1743252` (00:02).
RID names: `sweep`, `sweep2`, `sweep3`, `sweep4`, `sweep5`.

### B7/B13 — Parent chain to PID 1 (raw `/proc/<pid>/status` + cmdline)
```
PID=1743336 PPID=1644932 NAME=bash  CMD=/bin/bash -c cd /tmp/opencode/mamba-sweep-20260918/phase2 ... bash run_cell.sh 48 ...
PID=1644932 PPID=298244  NAME=opencode CMD=opencode
PID=298244  PPID=298243  NAME=bash   CMD=-bash
PID=298243  PPID=298128  NAME=sshd   CMD=sshd: ubuntu@pts/0
PID=298128  PPID=1272    NAME=sshd   CMD=sshd: ubuntu [priv]
PID=1272    PPID=1       NAME=sshd   CMD=sshd: /usr/sbin/sshd -D [listener] 0 of 10-100 startups
```
Top-level ancestor = `sshd` listener PID 1272 (PPID 1); interactive session = `pts/0`.

### B8 — Process trees (raw, selected)
```
1743336 1644932 1743336 1743336 ... bash run_cell.sh 48 sweep5-...
1743340 1743336 ... bash run_cell.sh 48 ...
1743344 1743340 ... bash .../cell_supervise.sh 48 ...
1743374 1743344 ... sglang.launch_server --port 30160 ...
1644932 298244 1644932 298244 ... opencode
298243 298128 298128 298128 ... sshd: ubuntu@pts/0
298128 1272   298128 298128 ... sshd: ubuntu [priv]
1272   1      1272   1272   ... sshd: /usr/sbin/sshd -D [listener]
```
```
PID 1644932 PPID 298244 PGID 1644932 SESS 298244 TT pts/0  STARTED Thu Sep 17 20:44:27 2026
```
`who`: `ubuntu pts/0 2026-09-17 07:03 (192.168.1.203)`. Only one interactive session.

### B9 — `/tmp/opencode` top-level, newest file mtime per session-like dir (raw)
```
prod-service-20260917  newest 2026-09-17 23:56:35  logs/prod-20260917T235414Z-1738571/server.console.log
mamba-sweep-20260918   newest 2026-09-18 00:04:49  phase2/logs/cell-48-sweep5-.../sglang-request-metrics-20260918_00.log
gguf-gate-20260917     newest 2026-09-17 15:37:44  POST_chat2.json
effort-probe-20260918  newest 2026-09-17 21:39:53  control-01.json
effort-confirm-20260918 newest 2026-09-17 21:51:47 effort_results.json
gatea-retry            newest 2026-09-17 21:28:02  unittest_final_d1.txt
smoke                  newest 2026-09-17 19:06:14  final_smoke.py
qwen3coder-adjudicate-20260918 newest 2026-09-17 23:33:43 probe6.py
audit-qwen3coder       newest 2026-09-17 23:55:03  probe_ns.py
p6-mamba-20260918      newest 2026-09-18 00:05:36  scripts/p6_run_cell.sh
gpu-3090.lock          Modify 2026-09-18 00:00:09
```
These are session artifacts; they do not by themselves establish live process ownership.

### C10 — Grep of sweep tree for `stop.sh`/kill/SIGTERM/identity (raw, selected)
```
/tmp/opencode/mamba-sweep-20260918/phase2/run_cell.sh:47:# stop: identity-checked server SIGTERM, then supervisor
/tmp/opencode/mamba-sweep-20260918/phase2/run_cell.sh:53:    *launch_server*--port\ $PORT*) echo "identity OK"; kill -TERM "$SPID" 2>/dev/null || true ;;
/tmp/opencode/mamba-sweep-20260918/phase2/run_cell.sh:54:    *) echo "WARN: pid $SPID identity mismatch; NOT signalling: $CMD" ;;
/tmp/opencode/mamba-sweep-20260918/phase2/run_cell.sh:58:  if [ -d "/proc/$SPID" ]; then echo "SIGKILL server"; kill -KILL "$SPID" 2>/dev/null || true; fi
/tmp/opencode/mamba-sweep-20260918/phase2/run_cell.sh:65:    case "$SCMD" in *cell_supervise.sh*) kill -TERM "$SUP" ...
```
SIGTERM lines exist only in `server.console.log` for each completed cell (self-termination at end
of cell), e.g. `cell-48-sweep2.../server.console.log:9314: SIGTERM received`.

### C11 — `run_cell.sh` stop block (quoted exactly; lines 47–59)
```
47: # stop: identity-checked server SIGTERM, then supervisor
48: SPID="$(cat "$STATE/cell-$CELL.pid" 2>/dev/null || true)"
49: echo "--- stop $(date -u +%Y-%m-%dT%H:%M:%SZ) server_pid=$SPID ---"
50: if [ -n "$SPID" ] && [ -d "/proc/$SPID" ]; then
51:   CMD="$(tr '\0' ' ' < /proc/$SPID/cmdline 2>/dev/null || true)"
52:   case "$CMD" in
53:     *launch_server*--port\ $PORT*) echo "identity OK"; kill -TERM "$SPID" 2>/dev/null || true ;;
54:     *) echo "WARN: pid $SPID identity mismatch; NOT signalling: $CMD" ;;
55:   esac
56:   D=$(( SECONDS + 240 ))
57:   while [ -d "/proc/$SPID" ] && [ "$SECONDS" -lt "$D" ]; do sleep 2; done
58:   if [ -d "/proc/$SPID" ]; then echo "SIGKILL server"; kill -KILL "$SPID" 2>/dev/null || true; fi
59: fi
```
`$PORT` is passed as `30160` from every sweep runner. **The stop block targets only the cell's own
server PID and its own port; it contains no `:30000`, no `stop.sh prod`, no `prod-*` target.**
`cell_supervise.sh` likewise only launches and `wait`s on its own `$SERVER_PID` (lines 84–135).

### C12 — Sweep logs mentioning `:30000` / `stop.sh prod` / `SIGTERM` / `prod-20260917`
```
/tmp/opencode/mamba-sweep-20260918/phase2/prod-env-relevant.txt:2:SGLANG_RUN_ID=prod-20260917T211800Z-1653969
/tmp/opencode/mamba-sweep-20260918/phase2/prod-env-relevant.txt:6:SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=/data/l3/prod-20260917T211800Z-1653969
/tmp/opencode/mamba-sweep-20260918/phase2/prod-argv.txt:1:... -m sglang.launch_server ... --port 30000 ...
```
These two files are **captured reference copies** of production argv/env used to derive the sweep
argv (`cell_supervise.sh` comment: "copy the captured production argv verbatim and change exactly
two things: --port and --max-mamba-cache-size"). No sweep log line invokes `stop.sh prod`.
The only `:30000` strings in the sweep tree are these reference captures.

### D14 — Processes matching gguf/sampled-smoke/run_sampled_smoke/3090-dev/gates/M4/M3
```
1743374 1743344 ... sglang.launch_server ... --mamba-ssm-dtype float32 ...   [FALSE POSITIVE]
```
Substring test on that command line:
```
pat=gguf:            (no match)
pat=sampled-smoke:   (no match)
pat=run_sampled_smoke:(no match)
pat=3090-dev/gates:  (no match)
pat=M4:              (no match)
pat=M3: m3           <-- matched inside "fp8_e4m3"
```
**No M2/M3/M4 GGUF gate process is running.** The only match is the case-insensitive `M3`
substring of `fp8_e4m3` in the sweep's own launch_server argv.

### D13 — Cross-reference: claimed kill script
- `agents/P4-PROD-RESTORE-AND-HOLD-20260918.md` (BLOCKED / KILLED-AGAIN) records: prod reached
  `/health` 200 at 23:56:27 (pid 1738819, run `prod-20260917T235414Z-1738571`), and was
  SIGTERM'd at 23:56:30 by a competing "identity-checked kill script (pid 1740056)" whose parent
  chain P4 states as
  `1740056 → run_cell.sh 1740231 → shell 1740227 → opencode 1644932 → bash 298244 → sshd pts/0`.
- Current liveness check: `pid=1740056 exists=no`, `pid=1740231 exists=no`, `pid=1740227 exists=no`.
  That specific kill script **cannot be independently reproduced now**; its chain is a preserved
  artifact claim (UNVERIFIED-cold). It terminates, by P4's own words, in the **same live opencode
  host 1644932** that currently contains the sweep.
- The preserved production log confirms the kill: `server.console.log` (run 1738571)
  `[2026-09-17 23:56:30] SIGTERM received ...` and `[23:56:35] kill_process_tree called:
  parent_pid=1738819, include_parent=True`; `state/gpu-owner.json` flipped to `free` /
  `supervisor-exit` at 23:56:29.

## Defects / blockers

- The live attribution target (the `bash -c` kill script reported as PID 1740056, and its parents
  1740231/1740227) had already exited; only the preserved P4 artifact describes it. Its parent
  chain is therefore reported as an artifact claim, not re-verified live.
- The only live agent host now is `opencode` 1644932. No second `opencode`/`node`/`bun` process
  exists on the host, so the prompt's "two automated sessions" cannot be separated by live process
  lineage; both appear to be logical sub-sessions within 1644932 over the single `pts/0` session.
- Whether the canonical flock is currently free is UNKNOWN (probing it would require acquiring the
  lock, which this read-only task forbids).
- sweep5's own terminator is not identifiable from surviving live procs (all exited) → UNKNOWN.

## Remaining claims / exclusions

- **Claim (established by live lineage):** the running `mamba-sweep` (sweep5 cell-48) and all of
  its child load/server processes descend from `opencode` PID 1644932 over `sshd pts/0`
  (root `sshd` PID 1272). No sweep or kill action originates from outside that tree in the live
  process set.
- **Claim (preserved artifact, not re-verified live):** the 23:56:30 `:30000` SIGTERM/killpg was
  performed by a `bash -c` kill script whose reported chain also roots at `opencode` 1644932.
- **Attribution to the named M-line artifacts:** `GGUF-GATE-M4M3-20260918`,
  `PROD-STATE-CHECK-R2-20260918`, `G-COMMIT-ROSTER-VERIFY-20260918`, and
  `R5-GATEA-CLOSURES-COMMIT-20260918` are on-disk result files only. **No live process, and no
  process-lineage evidence, ties any current sweep or kill action to them.** `GGUF-GATE-M4M3`
  lists a `stop.sh prod` step but no live gate process exists and its recorded state is WORKING
  (not executed). `PROD-STATE-CHECK-R2` is a read-only health report; `G-COMMIT-ROSTER-VERIFY`
  and `R5-GATEA-CLOSURES-COMMIT` are read-only git checks. By process lineage alone they are
  **not** the killer of `:30000`.
- **Separation of the two logical sessions is NOT achievable by live process lineage** on this
  host; both share one opencode host process and one SSH PTY. Any finer attribution would require
  a non-lineage source (e.g., opencode session DB), which is outside this task's authorized
  observation method.
- Exclusions: no process was signalled; no lock was acquired; no sweep evidence was edited; no git
  mutation; `/opt`, `/data`, `/var/log` untouched.

## Terminal state: DONE

Return:
- Terminal state: DONE
- Artifact path: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/KILLER-ATTRIBUTION-RECON-20260918.md
- (a) `:30000` UP/DOWN: DOWN (000/000/000).
- (b) Sweep owner lineage top ancestor: `sshd /usr/sbin/sshd -D` PID 1272 (PPID 1), session `pts/0`; live host = `opencode` PID 1644932.
- (c) Any M-line gate currently running: NO (only false positive `fp8_e4m3` substring match).
- (d) Does the sweep machinery itself kill `:30000`: NO — `run_cell.sh` only signals its own cell server PID/port; quoted: `*launch_server*--port\ $PORT*) echo "identity OK"; kill -TERM "$SPID" ...` (`$PORT`=30160, never 30000).
