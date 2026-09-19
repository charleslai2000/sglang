# P0-PROD-LIVENESS-CHECK-20260918

Status: DONE

## Task
Urgent READ-ONLY liveness check of the production SGLang service after a GPU experiment task died mid-flight
(that task had permission to stop/restart prod). Establish exact current state. Read-only; do not fix.

## Scope
Observation only. No start/stop/restart/signal, no pkill/killall, no lock acquisition (probe released
immediately, lock file not written), no edits except this artifact, no git mutation, nothing launched.
Host: ubuntu@192.168.20.250, 2026-09-17 ~23:09 UTC.

## Result

```
PRODUCTION: DOWN
LAN:        NOT-REACHABLE
LEFTOVERS:  none (no leftover process; orphaned experiment artifact files/dirs exist on disk only, listed below)
```

Leftover experiment *process*: NONE. No `sglang.launch_server`, no `supervise.sh`, no server on 30000 or
30160, no load-test/benchmark process. The prod server and supervisor both exited at 23:05-23:06 UTC and
were NOT restarted. Production is stopped, not running.

## Evidence

### 1. Process state
```
$ date
Thu Sep 17 23:09:23 UTC 2026

$ pgrep -af '[s]glang.launch_server'
(no output; exit=1)

$ pgrep -af '[s]upervise.sh'
(no output; exit=1)

$ ps -eo pid,ppid,lstart,etime,cmd | grep -iE '[p]ython|[s]glang|[l]oad.?test|[b]enchmark'
   1134       1 Tue Sep 15 22:24:06 2026  2-00:45:19 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
(only the unrelated unattended-upgrades process; no sglang/launch_server/load-test)

Recorded prod PIDs from state/runs/prod.run and logs (1654092 supervisor, 1654119 server, 1653969 run token):
$ for p in 1654092 1654119 1653969; do [ -d /proc/$p ] && echo alive || echo gone; done
pid 1654092 GONE
pid 1654119 GONE
pid 1653969 GONE
```
No `sglang.launch_server` and no `supervise.sh` matches exist. Every recorded prod PID is gone, so
`ps -o pid,ppid,lstart,etime,cmd -p <pids>` has no rows to report.

### 2. Ports / listeners
```
$ ss -ltnp | grep -E '30000|30160|3016[0-9]'
(no output; grep exit=1)

$ ss -ltnp
State  Recv-Q Send-Q Local Address:Port Peer Address:PortProcess
LISTEN 0      4096      127.0.0.54:53        0.0.0.0:*
LISTEN 0      4096         0.0.0.0:22        0.0.0.0:*
LISTEN 0      4096   127.0.0.53%lo:53        0.0.0.0:*
LISTEN 0      4096            [::]:22           [::]:*
```
- Bound on 30000: NO (nothing).
- Bound on 192.168.20.250: NO.
- Bound on 0.0.0.0:30000: NO.
- Leftover measurement server on 30160 (or any 3016x): NO — none bound.
Only loopback DNS resolvers (53) and SSH (22) are listening.

### 3. Health (loopback and LAN)
```
$ curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health
curl: (7) Failed to connect to 127.0.0.1 port 30000 after 0 ms: Couldn't connect to server
000

$ curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://192.168.20.250:30000/health
curl: (7) Failed to connect to 192.168.20.250 port 30000 after 0 ms: Couldn't connect to server
000

$ curl -sS -m 5 http://127.0.0.1:30000/v1/models
curl: (7) Failed to connect to 127.0.0.1 port 30000 after 0 ms: Couldn't connect to server
(no body; curl exit=7)
```
LAN interface itself is up and configured (192.168.20.250/24 on eth0), but the service is not listening,
so LAN health is NOT-REACHABLE.

### 4. GPU
```
$ nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
NVIDIA GeForce RTX 3090, 1 MiB, 24576 MiB, 0 %

$ nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
(no output; exit=0)
```
GPU memory is 1 MiB / 24576 MiB, 0% util, no compute processes. GPU is clean/free.

### 5. Canonical lock /tmp/opencode/gpu-3090.lock
```
$ cat /tmp/opencode/gpu-3090.lock
{"owner": "supervise-prod-prod-20260917T211800Z-1653969", "pid": 1654092, "generation": 7, "acquired": "2026-09-17T21:18:00Z"}

$ stat /tmp/opencode/gpu-3090.lock
  File: /tmp/opencode/gpu-3090.lock
  Size: 127        Blocks: 8          IO Block: 4096   regular file
Access: (0664/-rw-rw-r--)  Uid: ( 1000/ ubuntu)   Gid: ( 1000/ ubuntu)
Access: 2026-09-17 21:18:00.930556853 +0000
Modify: 2026-09-17 21:18:00.924556673 +0000
Change: 2026-09-17 21:18:00.924556673 +0000
Birth:  2026-09-16 11:57:06.337122290 +0000
```
Fresh non-mutating flock probe (LOCK_EX|LOCK_NB, released immediately; file opened O_RDONLY, never written):
```
$ python3 -c "...open p, flock(LOCK_EX|LOCK_NB)..."
held=no (free) - probe acquired and released
probe_exit=0
```
`/proc/locks` has no entry for inode 3146713 (the lock file):
```
$ grep -i gpu-3090 /proc/locks
(no output; grep exit=1)
$ cat /proc/locks
1: FLOCK  ADVISORY  WRITE 1063 00:19:1362 0 EOF
2: POSIX  ADVISORY  WRITE 654 00:19:581 0 EOF
3: POSIX  ADVISORY  READ 1644932 08:01:330650 128 128
4: POSIX  ADVISORY  READ 1644932 08:01:330648 1073741826 1073742335
5: POSIX  ADVISORY  WRITE 1074 00:19:1377 0 EOF
```
LOCK STATUS: FREE (not held). The file's JSON content is stale metadata from generation 7 owner pid 1654092
(now gone); mtime unchanged at 21:18:00, confirming the probe did not write it.

### 6. Scaffold state
```
$ cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json
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
  "lock_generation": 7,
  "updated_at_utc": "2026-09-17T23:06:37Z",
  "note": "stopped"
}

$ cat /tmp/opencode/prod-service-20260917/state/runs/prod.run
role=prod
pid=1654119
supervisor_pid=1654092
port=30000
tree=/opt/sglang/local-prod-v1.2.1-candidate
run_id=prod-20260917T211800Z-1653969
namespace=/data/l3/prod-20260917T211800Z-1653969
lock_generation=7
cold_start_s=127.9
started_at_utc=2026-09-17T21:20:08Z

$ ls -la .../state/runs/
-rw-rw-r-- 1 ubuntu ubuntu 260 Sep 17 21:20 prod.run

$ ls -la .../state/pids/
(empty)

$ ls -la .../state/ready/
(empty)
```
Newest supervisor.log (`logs/prod-20260917T211800Z-1653969/supervisor.log`, last 40 lines = whole file):
```
[21:18:00] canonical GPU lock ACQUIRED generation=7 owner=supervise-prod-prod-20260917T211800Z-1653969 pid=1654092
[21:18:00] supervisor launching prod on port 30000 (tree=/opt/sglang/local-prod-v1.2.1-candidate)
[21:18:24] /proc/1654119/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
[21:20:08] COLD START (launch -> /health 200): 127.9s
[21:20:08] === prod UP: pid=1654119 port=30000 cold_start=127.9s ===
[23:05:31] WARN: supervisor exiting rc=0; releasing GPU lock
```
A stop WAS attempted/completed: at 23:05:31 the supervisor exited rc=0 and released the GPU lock.
`server.console.log` ends with the kill of the server process tree:
```
[2026-09-17 23:06:32] INFO:     192.168.1.203:48054 - "POST /v1/chat/completions HTTP/1.1" 500 Internal Server Error
[2026-09-17 23:06:32] kill_process_tree called: parent_pid=1654119, include_parent=False, pid=1654119
```
No start was attempted after the stop: no newer `supervisor.log` exists, no run dir newer than
`prod-20260917T211800Z-1653969` (mtime 23:05), `state/pids/` is empty, `state/ready/` is empty, and
`gpu-owner.json` was updated to `state: free, note: "stopped"` at 23:06:37 with no subsequent change.

### 7. Orphaned experiment artifacts
Processes: none (see item 1). Port 30160: nothing bound. No load-test/locust/wrk/hey/vegeta/benchmark
process. Disk-only orphaned artifacts (paths only, not modified):
```
/tmp/opencode/mamba-sweep-20260918/            (dir; contains only empty phase0/, mtime 22:49)
/tmp/opencode/mam_metrics.txt                  (22:38)
/tmp/opencode/mam_metrics2.txt                 (22:56)
/tmp/opencode/mam_metrics3.txt                 (23:03)
/tmp/opencode/probe_audit.py                   (22:12)
/tmp/opencode/test_audit_launcher_fixed.py     (22:11)
```
These are leftover files from the dead experiment, not running services.

### 8. Repo / artifact state (read-only, no mutation)
```
$ git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt rev-parse HEAD
3f2a417e95330829c57c4cb8446e764abb801313
$ git -C ... log -3 --oneline
3f2a417e95 test(gates): close Gate-A/F1 drop-predicate and evidence conditions (harness-only, no runtime change)
910e5a01c0 docs(memory): session-close handoff for the M1 production session
a6beb3004c docs(memory): reconcile production commit identity (b2bbd6ea28 / 8c8cdcea03)
```
Agent artifact line counts (MAMBA-SWEEP / QWEN3CODER-SCOPE-ADJUDICATE / V122-TOOLCHAIN-COMPLETE):
```
$ wc -l .memory/phase2-hicache-design/agents/MAMBA-SWEEP-48-56-64-20260918.md \
        .memory/phase2-hicache-design/agents/QWEN3CODER-SCOPE-ADJUDICATE-20260918.md \
        .memory/phase2-hicache-design/agents/V122-TOOLCHAIN-COMPLETE-20260918.md
  10 MAMBA-SWEEP-48-56-64-20260918.md
  25 QWEN3CODER-SCOPE-ADJUDICATE-20260918.md
  30 V122-TOOLCHAIN-COMPLETE-20260918.md
  65 total
```
All three are short (10/25/30 lines) and consistent with stub/status-only artifacts, but I did not
inspect their content beyond line counts (task asked for line counts only).

## Defects / blockers

DEFECT (reported, not fixed): **Production is DOWN.** The prod SGLang service on port 30000 is not
running. It was deliberately stopped at 23:05:31-23:06:32 UTC (supervisor exit rc=0 releasing the lock;
server process tree killed) and no restart occurred. The dead experiment did not leave prod running.

Restore preconditions — all currently satisfied (this task did NOT perform the restore):
- Port 30000: FREE (nothing bound locally or on 192.168.20.250).
- Canonical GPU lock `/tmp/opencode/gpu-3090.lock`: FREE (flock probe acquired/released; no /proc/locks entry).
- GPU: CLEAN (1 MiB used, 0% util, no compute apps).
- `state/gpu-owner.json`: `state: free`, `note: "stopped"` — consistent with the free lock.
- Recorded prod PIDs (1654092/1654119/1653969): all GONE — no stale process to clear.
- `state/pids/` and `state/ready/` are empty.
- Prod tree referenced by `state/runs/prod.run`: `/opt/sglang/local-prod-v1.2.1-candidate`.

Needed to restore (for a separate authorized task, NOT done here): run
`/tmp/opencode/prod-service-20260917/bin/start.sh prod` (which runs preflight, refuses if a material GPU
holder or non-free port exists, then hands off to `bin/supervise.sh` to acquire the lock, launch the
frozen tree, and wait for `/health 200`; last cold start was 127.9s). The orchestrator should dispatch
the restore as its own task with authority to start services.

## Remaining claims / exclusions
- VERDICT scope: state measured 2026-09-17T23:09Z. No guarantees about state after this observation.
- I did not run `ps -o ... -p <pids>` with rows because all recorded PIDs are gone; the GONE checks are
  the equivalent evidence.
- I did not read the substantive content of the three .memory agent artifacts (line counts only, as asked).
- The lock file's stale JSON (generation 7, pid 1654092) is metadata only; it does NOT indicate the lock is
  held — the flock is free and no /proc/locks entry exists.
- No start/stop/restart/signal was performed; no process was launched; no lock was acquired (probe
  released immediately and wrote nothing); no git mutation; only this artifact was written.
- Root cause of the stop (which task/host called the stop) was not investigated — outside read-only scope.

## Terminal state: DONE
