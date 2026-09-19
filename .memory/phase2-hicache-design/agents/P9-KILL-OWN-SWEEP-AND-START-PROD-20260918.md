# P9-KILL-OWN-SWEEP-AND-START-PROD-20260918

Status: BLOCKED

## Task
Terminate this orchestrator's OWN 48/56/64 mamba-sweep automation (owner-cancelled), preserve its disk
evidence, then start production on `:30000` and hold it. Sole GPU owner for this window.

## Scope
- In scope: terminate only the sweep tree `/tmp/opencode/mamba-sweep-20260918/` (`run_cell.sh`,
  `cell_supervise.sh`, `load.py`, `launch_server --port 30160`) and any wrapper that could restart it;
  preserve disk evidence; start production via `/tmp/opencode/prod-service-20260917/bin/start.sh prod`;
  verify; 120 s hold-check.
- Out of scope (per dispatch HARD CONSTRAINTS): any process whose cmdline does not reference
  `/tmp/opencode/mamba-sweep-20260918/` or port 30160; `pkill`/`killall`; deleting/editing evidence;
  editing `/opt`, `/data`, `/var/log`, the repo; git mutation; changing the prod tree/launcher/config;
  acquiring the lock myself; new sweep/benchmark/load; `3090-dev/gates/**`.

## Result
- **Named sweep (`mamba-sweep-20260918`) automation: fully TERMINATED.** No auto-restart loop exists.
  Its cell-48/sweep5 tree (wrapper/`run_cell.sh`/`cell_supervise.sh`/`launch_server:30160`/`load.py`)
  was identity-checked and terminated by process group; `:30160` freed; canonical lock released
  (fresh non-mutating probe = FREE). Disk evidence preserved (64 MB, untouched).
- **Production WAS started and fully verified** (pid 1746457, run `prod-20260918T000656Z-1746209`,
  cold start 132.0 s; loopback `/health` 200; `/v1/models` 200; LAN `192.168.20.250:30000` health 200;
  1 inference smoke 200).
- **Hold result: KILLED-AGAIN.** During the 120 s hold a *different, out-of-scope* sweep automation
  `/tmp/opencode/p6-mamba-20260918/` (`p6_run_cell.sh`/`p6_supervise.sh`, launched 00:10:43)
  took canonical lock generation 18 and started its own `launch_server --port 30160`.
  Production exited at 00:10:19–00:10:31 (supervisor log `exiting rc=0`; `gpu-owner.json`
  `note="stopped"`; prod pid/run files removed). New pid of the competing server: **1747952**.
- Per STEP 7, production was **NOT restarted a second time**, and the out-of-scope p6 tree was
  **NOT** killed (dispatch authorizes only `/tmp/opencode/mamba-sweep-20260918/` + port 30160;
  "NEVER kill anything else").
- LAN HTTP code at last verification for prod: **200** (before the kill). Final `:30000` = DOWN.
- New production pid (the one that was started then killed): **1746457**.

## Evidence

### Authority (quoted)
- `OWNER-APPROVAL-20260918-PROD-START` (ledger lines 9520-9535): start production `:30000` now;
  to do so abort this line's own mamba sweep incl. active cell, release GPU + canonical lock;
  revert via identity-checked `start.sh prod` (no pkill); verify health/models + LAN + smoke.
- Owner cancellation of 48/56/64 (ledger lines 9752-9758): "先把 `48→56→64` 取消。现在只做一件事：
  把 Mamba L2 的真实容量账算清楚 … 先算账，不测试。"
- Owner port ownership (ledger lines 9597-9612): "你在负责这个 30000，GPU 控制权我负责。"
- Self-attribution (ledger lines 10659-10691): killer = this line's own sweep automation;
  P9 = sole GPU owner; terminate `run_cell.sh`/`cell_supervise.sh`/`load.py`/`launch_server:30160`.
- Concurrent ledger growth: file was 10,709 lines at dispatch start and 10,913 lines at close;
  later entries (10800-10913) add a root owner ruling that `48/56/64` is permanently cancelled and
  the card is production+test shared, and a FINAL owner-ordered stop closing all ownership
  (including `P9 … TERMINATED, 结果未消费`). These were not part of the dispatch packet and are
  recorded here as context; they do not broaden this task's named kill scope.

### Pre-teardown inventory (2026-09-18 ~00:05Z)
- 1743336 PGID 1743336 `/bin/bash -c` wrapper (`run_cell.sh 48 ... 30160 16`), parent opencode 1644932.
- 1743340 PGID 1743336 `bash run_cell.sh 48 sweep5-mamba48-20260918T000006Z-1743252 ... 30160 16`.
- 1743341 PGID 1743336 `tee logs-cell-48-sweep5.out`.
- 1743344 PGID 1743344 (SID 1743344) `bash cell_supervise.sh 48 ... 30160`.
- 1743374 PGID 1743374 `launch_server … --port 30160 --max-mamba-cache-size 48` (the sweep server).
- 1743489/1743490/1743491/1744116 PGID 1743374 children (`resource_tracker`, `sglang::scheduler`,
  `sglang::detokenizer`, torch inductor worker).
- 1744156 PGID 1743336 `python load.py --base http://127.0.0.1:30160 ...`; 1744157 tee load-summary.
- 1745084 PGID 1745084 bash poller (read-only 60×10 s wait; no restart).
- `ss -ltnp`: `0.0.0.0:30160` LISTEN pid 1743374. **Nothing on `:30000`**; loopback health 000.
- canonical lock: `{"owner":"sweep-cell-48-sweep5-mamba48-20260918T000006Z-1743252","pid":1743344,
  "generation":16,"acquired":"2026-09-18T00:00:09Z"}`.
- `nvidia-smi --query-compute-apps`: 1743374 (300 MiB), 1743490 `sglang::scheduler` (22618 MiB).
- No restart loop found: wrapper is a single `bash -c` (no loop); no cron/systemd/nohup sweep refs.

### Sweep disk evidence inventory (preserved, read-only, 64 MB)
- `/tmp/opencode/mamba-sweep-20260918/phase2/`: `run_cell.sh`, `cell_supervise.sh`, `load.py`,
  `alloc-48/56/64.json`, `alloc-64b/64c.txt`, `logs-cell-*.out`, `prod-argv.txt`,
  `prod-env-relevant.txt`, `wait_ts.txt`.
- `phase2/logs/` 8 cell dirs (48 ×3 full sets, 48-sweep4 partial, 48-sweep5 in-progress,
  56 complete, 64-sweep2 partial, 64-sweep2b empty, 64-sweep3 partial).
- `phase2/state/` cell-48/56/64 pid/run/namespace + `sup-*.pid`.
- Nothing moved/edited/deleted.

### Teardown sequence (identity-checked; TERM → bounded wait → KILL if needed)
1. `load.py`/tee (1744156, 1744157): `kill -TERM` by PID (cmdline matched `load.py`/`load-summary`).
   Effect after 5 s: gone.
2. `cell_supervise.sh` group (1743344): `kill -TERM -1743344`. Effect: gone.
3. `run_cell.sh` wrapper group (1743336, members 1743336/1743340/1743341): `kill -TERM -1743336`.
   Effect after 5 s: all gone.
4. `launch_server` group (1743374) and poller group (1745084): `kill -TERM -1743374` and
   `kill -TERM -1745084`. Group 1743374 had already emptied (supervisor EXIT trap released the lock);
   `:30160` freed within ~3 s.
No SIGKILL was required.

### Clean-state verification (after teardown, before prod start)
- `pgrep -af 'run_cell.sh|cell_supervise.sh|load.py|sglang.launch_server|supervise.sh'` → NONE.
- `ss -ltnp | grep -E '30000|30160'` → NOTHING.
- `ps … | grep mamba-sweep-20260918` → NONE.
- `nvidia-smi --query-compute-apps` → empty.
- Fresh non-mutating flock probe on `/tmp/opencode/gpu-3090.lock` (O_RDONLY, LOCK_EX|LOCK_NB, release,
  no write): **LOCK_PROBE=FREE**. File mtime unchanged (`00:00:09.63Z`).

### start.sh output (verbatim, truncated to key lines)
```
[00:06:37] === start role=prod port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate ===
[00:06:37] P2 manifest digest OK: 5ed662d0…
[00:06:37] P3 launcher sha OK: 4ae68470…
[00:06:37] P4 launcher enforces the source-identity gate
[00:06:37] P5 launcher enforces the per-run L3 namespace gate
[00:06:47] P6 sglang.__file__ OK: …/local-prod-v1.2.1-candidate/src/python/sglang/__init__.py
[00:06:56] P7 shared production L3 store present and MUST NOT be cleared: /data/l3/local-prod-v1.1
[00:06:56] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate
[00:06:56] port 30000 free
[00:06:56] L3 namespace (unique, never cleared): /data/l3/prod-20260918T000656Z-1746209
[00:06:56] supervisor pid=1746430 (holds the canonical GPU lock for the server lifetime)
[00:09:08] === prod UP ===
role=prod
pid=1746457
supervisor_pid=1746430
port=30000
tree=/opt/sglang/local-prod-v1.2.1-candidate
run_id=prod-20260918T000656Z-1746209
namespace=/data/l3/prod-20260918T000656Z-1746209
lock_generation=17
cold_start_s=132.0
started_at_utc=2026-09-18T00:09:08Z
START_RC=0
```

### Production verification block (2026-09-18T00:09:11–00:09:15Z)
- `pgrep -af sglang.launch_server` → 1746457 … `--port 30000` (full argv matches frozen prod profile).
- `ss -ltnp | grep 30000` → `LISTEN 0 2048 0.0.0.0:30000 … users:(("python",pid=1746457,fd=68))`.
- loopback `GET /health` → **200**.
- `GET /v1/models` →
  `{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16","object":"model",…,"max_model_len":131072}]}`.
- LAN `GET http://192.168.20.250:30000/health` → **200**.
- inference smoke (1×, model `/data/models/qwen35-9b-w4a16`, max_tokens 8) →
  `HTTP 200`, body id `a98fe04ec687434fbb8f91787fb5e8e1`, `usage.prompt_tokens=12,total_tokens=20`.
- `gpu-owner.json`: role=`prod`, state=`held`, pid=1746457, port=30000,
  run_id=`prod-20260918T000656Z-1746209`, identity=`LOCAL-PROD-v1.2.1`, lock_generation=17,
  note=`serving`.
- lock: `{"owner":"supervise-prod-prod-20260918T000656Z-1746209","pid":1746430,"generation":17,
  "acquired":"2026-09-18T00:06:56Z"}`; probe = HELD (expected).
- `nvidia-smi`: 1746457 (300 MiB) + 1746960 `sglang::scheduler` (22198 MiB).
- supervisor.log: `[00:06:56] canonical GPU lock ACQUIRED generation=17 …`,
  `[00:09:08] COLD START … 132.0s`, `[00:09:08] === prod UP: pid=1746457 port=30000 … ===`.

### Hold re-check (STEP 7) — KILLED-AGAIN
- `HOLDCHECK_START_UTC=2026-09-18T00:09:17Z`, `HOLDCHECK_END_UTC=2026-09-18T00:11:17Z` (sleep 120).
- `pgrep -af sglang.launch_server` → only **1747952** `… --port 30160 …` (P6 sweep), **no :30000**.
- `ss -ltnp | grep 30000` → NOTHING; loopback health → `000` (connection refused).
- lock: `{"owner":"p6-cell-48-p6-mamba48-20260918T000647Z-1746326","pid":1747922,"generation":18,
  "acquired":"2026-09-18T00:10:44Z"}`.
- `gpu-owner.json`: role=`free`, state=`free`, lock_generation=17, updated `00:10:31Z`, note=`stopped`.
- `nvidia-smi` compute apps → empty at that instant (P6 server still starting).
- Prod supervisor.log tail: `[00:10:19] WARN: supervisor exiting rc=0; releasing GPU lock`.
- Prod server.console.log tail: `[2026-09-18 00:10:26] kill_process_tree called: parent_pid=1746457,
  include_parent=False, pid=1746457`.
- Competing tree provenance: `/tmp/opencode/p6-mamba-20260918/scripts/p6_supervise.sh` created
  `00:05:08Z`, `p6_run_cell.sh` `00:05:36Z`; wrapper pid 1747916 parent 1644932 (opencode) started
  `00:10:43Z`; lock gen 18 at `00:10:44Z`. Its supervisor.log:
  `[00:10:44] canonical GPU lock ACQUIRED generation=18 owner=p6-cell-48-…`, `[00:12:31] p6-cell-48 UP
  pid=1747952 port=30160 lock_gen=18`. Its artifact `agents/P6-MAMBA-CORRECTED-AND-PROD-START-20260918.md`
  (status WORKING) cites a later owner order to actually run the sweep and claims kill authorization
  "including a running production service on :30000" — this is the same anti-pattern the root
  ruling (ledger 10800-10843) forbids.
- Final (2026-09-18T00:14:33Z) state: `:30160` LISTEN pid 1747952; nothing on `:30000`;
  lock held by p6 supervisor 1747922 gen 18; `gpu-owner.json` free/stopped.

## Defects / blockers
- **Blocking**: a competing, out-of-scope sweep tree `/tmp/opencode/p6-mamba-20260918/` (`p6_run_cell.sh`
  / `p6_supervise.sh`)
  started at 00:10:43Z and killed production during the hold, then took the GPU on :30160.
  It is **not** within this dispatch's authorized kill target (`/tmp/opencode/mamba-sweep-20260918/`
  and port 30160 only; "NEVER kill anything else"), so P9 did not terminate it. This is the concrete
  blocker to "production UP and held".
- Per STEP 7, production was **not** restarted after the kill; per STEP 7 it must be left running if
  alive, but it was already dead by a third party.
- The ledger's concurrent FINAL section records an owner-ordered stop that already closed this task's
  ownership (`P9 … TERMINATED, 结果未消费`). P9 still completed its owned artifact as dispatched.

## Remaining claims / exclusions
- The named `mamba-sweep-20260918` automation is fully stopped with no self-restart mechanism; its
  evidence is intact. This is established by direct process/port/lock evidence.
- Production start + loopback/LAN/models/smoke verification is established by the block above, for the
  window 00:09:08–~00:10:19Z.
- **Not claimed**: persistent production UP; termination of `p6-mamba-20260918`; attribution to any
  "external session" (the competing tree is another sweep automation on the same host; its exact
  dispatching session was not established by this task and is left to the orchestrator).
- P9 did not touch the ledger, the prod tree/launcher/config, `/opt`, `/data` (except no writes),
  `/var/log`, git, or `3090-dev/gates/**`. No lock was acquired by P9.

## Terminal state
BLOCKED
