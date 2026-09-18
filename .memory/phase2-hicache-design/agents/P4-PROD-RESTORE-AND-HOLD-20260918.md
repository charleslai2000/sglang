# P4-PROD-RESTORE-AND-HOLD-20260918

Task ID: P4-PROD-RESTORE-AND-HOLD-20260918
Role: devops-executor
Status: BLOCKED (KILLED-AGAIN)

## Task
Restore the orchestrator-owned production service on :30000 and keep it up. Authority:
`OWNER-APPROVAL-20260918-PROD-START` (ledger.md line 9520) plus the owner's final ruling
(ledger ~line 9597): this line owns :30000; GPU authorization belongs to the owner; the other
session handles "other content" and must not contend for :30000. A competing session had
SIGTERM'd a prior production instance and relaunched a mamba-sweep cell (sweep3) holding the
canonical lock and GPU. Procedure: verify state, preserve sweep evidence, identity-checked stop
of the sweep cell, clean-state verify, start production, verify, hold/re-check ~90 s.

## Scope
- Read-only inventory of `/tmp/opencode/mamba-sweep-20260918/`.
- Identity-checked, process-group-targeted stop of the sweep cell holding
  `:30160` / `/tmp/opencode/gpu-3090.lock`. No pkill/killall.
- Start via `/tmp/opencode/prod-service-20260917/bin/start.sh prod`; verify; hold re-check.
- No tree/config/launcher changes; no sweep-evidence edits; no ledger or other artifact writes.

## Result
- **Sweep cell stopped: YES.** sweep3 cell-64 (run `sweep3-mamba64-20260917T235029Z-1737059`)
  was stopped identity-checked; `:30160` free; lock released; GPU cleared.
- **Production started: YES.** `start.sh prod` reached `/health` 200 at 23:56:27,
  run `prod-20260917T235414Z-1738571`, server pid **1738819**, cold start **133.0 s**,
  lock generation 14.
- **Production UP-PERSISTENT or KILLED-AGAIN: KILLED-AGAIN.** At **23:56:30**, ~3 s after
  reaching health 200, a competing session ran an identity-checked kill script
  (pid 1740056, `pgrep`-captured) that TERM'd the prod client/supervisor and killpg'd the
  server process group. The production server logged `SIGTERM received ... Draining requests`.
  At **23:56:48** the same competing session re-acquired the canonical lock as
  **generation 15** and launched a new sweep cell (`sweep4-mamba48-...`, server pid 1740265,
  `:30160`).
- Per STEP 7 instruction, **no second production start was attempted**.
- New production pid: 1738819 (now dead). Run id: `prod-20260917T235414Z-1738571`.
- LAN HTTP code: **not obtainable** — production was already dead before the verification block
  could run; `http://192.168.20.250:30000/health` returned connection failure (000).
- Inference smoke: **not performed** (server was already terminated at the time verification
  was due to run).
- Current live state: **production DOWN; sweep4 holds GPU/lock gen 15 on :30160.**

## Evidence

### 1. Fresh state re-verification (STEP 1) — 2026-09-17T23:53:29Z
`pgrep` showed the sweep3 cell only:
- `1737066 bash run_cell.sh 64 sweep3-mamba64-20260917T235029Z-1737059 ... 30160 16`
- `1737070 bash .../cell_supervise.sh 64 sweep3-mamba64-20260917T235029Z-1737059 ... 30160`
- `1737100 ... -m sglang.launch_server ... --port 30160 ... --max-mamba-cache-size 64 ...`
- `1738042 .../load.py --base http://127.0.0.1:30160 --label cell-64 ...`

`ss -ltnp`: only `0.0.0.0:30160` (pid 1737100). Nothing on :30000.
Lock: `{"owner": "sweep-cell-64-sweep3-mamba64-20260917T235029Z-1737059", "pid": 1737070,
"generation": 13, "acquired": "2026-09-17T23:50:32Z"}`.
`nvidia-smi`: pid 1737100 (300 MiB) + scheduler 1737238 (23172 MiB) — both sweep.
`gpu-owner.json`: role free, note "stopped", lock_generation 12, updated 23:50:26Z.

### 2. Sweep evidence inventory (STEP 2, read-only; nothing moved/edited/deleted)
Root `/tmp/opencode/mamba-sweep-20260918/` (phase0 empty; phase2 populated).
Completed cells (load-summary/`cell-*.json` present, smoke 200):
- `cell-48-sweep-mamba48-20260917T231327Z-1726566`: cell-48.json 30651 B, metrics 9.90 MB,
  server.console 554 KB; 96/96 ok, p95 5.11 s, mamba_used_max 32.
- `cell-48-sweep2-mamba48-20260917T231910Z-1727975`: cell-48.json 122360 B, metrics 13.19 MB;
  128/128 ok, agg 65.86 tok/s, p95 30.84 s.
- `cell-56-sweep2-mamba56-20260917T231910Z-1727975`: cell-56.json 107377 B, metrics 13.19 MB;
  128/128 ok, agg 77.89 tok/s, p95 20.65 s.
- `cell-64-sweep2-mamba64-20260917T231910Z-1727975`: `load-summary.txt` 0 B (incomplete);
  server.console 2.46 MB, metrics 5.77 MB; `logs-cell-64b.out` shows load was `Terminated`,
  `load_rc=143` — incomplete measurement.
Interrupted/aborted: `cell-64-sweep2-mamba64b-...1736234` (only supervisor.log, 184 B),
`cell-64-sweep3-...1737059` (the cell stopped in STEP 3; server.console 929913 B,
metrics 1654214 B, load-summary 0 B), and later `cell-48-sweep4-...1740204` (competing
session restart).
State files preserved: `state/cell-48*.{pid,port,run,run_id,namespace}`, `cell-56.*`,
`cell-64.*`, `sup-*.pid`.

### 3. Teardown sequence + effect (STEP 3)
Identity-checked BEFORE signalling (cmdline token match, all IDENTITY-OK):
load.py 1738042 / run_cell.sh 1737066 / cell_supervise.sh 1737070 /
launch_server 1737100 (`--port 30160`, run id `sweep3-mamba64-...`).
- 23:53:37Z TERM `load.py` 1738042 → gone in 3 s.
- 23:53:43Z TERM `cell_supervise.sh` 1737070 and `run_cell.sh` 1737066 → both gone in 3 s.
- 23:53:46Z `kill -TERM -1737100` (server pgid 1737100) → gone within the bounded wait.
No SIGKILL was required. No unrelated process signalled.

### 4. Clean-state verification (STEP 4) — 2026-09-17T23:53:51Z
- `pgrep -af sglang.launch_server`: none. `pgrep` sweep scripts: none.
- `ss -ltnp | grep -E ':30000|:30160'`: none.
- `nvidia-smi --query-compute-apps`: none. Scheduler 1737238 gone.
- Fresh non-mutating flock probe (`os.open(O_RDONLY)` + `LOCK_EX|LOCK_NB`, released, no write):
  **FREE**.
- Lock file still contained the stale sweep3 record (last writer), but was unlocked — expected;
  next acquirer overwrites via generation bump.

### 5. start.sh output (STEP 5) — 2026-09-17T23:53:53Z → 23:56:29Z
```
[23:53:53] === start role=prod port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate ===
[23:53:53] P2 manifest digest OK: 5ed662d0...defd950
[23:53:53] P3 launcher sha OK: 4ae68470...2ff2ff5
[23:53:53] P4 launcher enforces the source-identity gate
[23:53:53] P5 launcher enforces the per-run L3 namespace gate
[23:54:04] P6 sglang.__file__ OK: .../src/python/sglang/__init__.py
[23:54:14] P7 shared production L3 store present and MUST NOT be cleared: /data/l3/local-prod-v1.1
[23:54:14] preflight PASS
[23:54:14] port 30000 free
[23:54:14] L3 namespace (unique, never cleared): /data/l3/prod-20260917T235414Z-1738571
[23:54:14] supervisor pid=1738792 (holds the canonical GPU lock for the server lifetime)
Terminated
START_RC=143
```
Note: `start.sh` itself (client pid 1738571) was the first target of the competitor kill script and
received SIGTERM (rc 143) before it could print `=== prod UP ===`, even though the supervisor had
already brought the server to health 200.

Production supervisor log (`logs/prod-20260917T235414Z-1738571/supervisor.log`):
```
[23:54:14] canonical GPU lock ACQUIRED generation=14 owner=supervise-prod-prod-20260917T235414Z-1738571 pid=1738792
[23:54:14] supervisor launching prod on port 30000 (tree=/opt/sglang/local-prod-v1.2.1-candidate)
[23:54:39] /proc/1738819/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python CUDA_VISIBLE_DEVICES=GPU-2e3ed202-...
[23:56:27] COLD START (launch -> /health 200): 133.0s
[23:56:27] === prod UP: pid=1738819 port=30000 cold_start=133.0s ===
[23:56:29] WARN: supervisor exiting rc=0; releasing GPU lock
```

### 6. Verification block (STEP 6) — partial
The intended verification block could not be completed because production was terminated at
23:56:30, before STEP 6 began. Captured while it was still alive (23:56:32Z):
- server pid 1738819 listening `0.0.0.0:30000` (`ss`).
- `gpu-owner.json` already flipped to `free` / note `supervisor-exit` (supervisor EXIT trap ran
  when the competitor TERM'd it).
The strong server-side proof of health is in `server.console.log`:
```
[23:56:22] GET /health HTTP/1.1 503 Service Unavailable
[23:56:26] GET /health HTTP/1.1 200 OK
[23:56:27] GET /health HTTP/1.1 200 OK
[23:56:30] SIGTERM received ... Draining requests and shutting down...
[23:56:35] kill_process_tree called: parent_pid=1738819, include_parent=True
```
LAN health/smoke: not obtainable (connection refused/000).

### 7. STEP 7 hold re-check — 2026-09-17T23:57:31Z → 23:59:01Z
- t0 (23:57:31Z): `:30000` server ABSENT; port 30000 none; lock gen 15 owned by
  `sweep-cell-48-sweep4-mamba48-20260917T235645Z-1740204`.
- sleep 90 s.
- t+90s (23:59:01Z): `pgrep` shows only sweep server pid 1740265 `--port 30160`;
  `ss` shows only `0.0.0.0:30160`; `curl 127.0.0.1:30000/health` → connection failed (000);
  lock still gen 15 (sweep4); `gpu-owner.json` still `free` / `supervisor-exit`.
- **Verdict: KILLED-AGAIN (not UP-PERSISTENT).**

### 7b. Post-hold material development — 2026-09-17T23:59:37Z
The competing session's own sweep4 cell finished on its own and stopped cleanly:
`logs-cell-48-sweep4.out` records `--- stop 2026-09-17T23:59:21Z server_pid=1740265 ---` and
`--- cell 48 stopped 2026-09-17T23:59:21Z ---`. A fresh read-only check at 23:59:37Z shows:
- `ss` :30000/:30160 — none; no `run_cell`/`cell_supervise`/`sglang.launch_server`/`load.py`/
  `supervise.sh` processes; `nvidia-smi` compute apps — none.
- Non-mutating flock probe — **FREE**. (The lock file still contains the stale sweep4 gen-15
  record, but it is unlocked; the next acquirer bumps to gen 16.)
- `state/cell-64.ready` absent (sweep3's ready marker was removed on stop).
**Implication for the orchestrator:** the GPU and canonical lock are now free and production can
be started without a stop/kill war — but per STEP 7 this agent does **not** start a second time
and leaves that decision to the orchestrator.

### 8. Evidence of the external kill (competing session)
- Captured kill-script process was pid **1740056**, a `/bin/bash -c` whose text explicitly:
  identity-checked `start.sh prod` / `supervise.sh prod` / `launch_server --port 30000`,
  then `kill -TERM` the client and supervisor, waited, then `kill -TERM -- -<pgid>` (killpg)
  the server group, with a bounded KILL fallback. Parent chain:
  `1740056 → run_cell.sh 1740231 ... → shell 1740227 (PPID 1644932) → opencode 1644932
  (PPID 298244) → bash 298244 → sshd pts/0` — i.e. the competing OpenCode session.
- The competitor then immediately ran `run_cell.sh 48` for
  `sweep4-mamba48-20260917T235645Z-1740204`, whose supervisor log records
  `canonical GPU lock ACQUIRED generation=15` at 23:56:48 and `cell-48 UP pid=1740265` at
  23:58:39. This is the same stop-production-and-relaunch-sweep pattern as the prior incident.

## Defects / blockers
- **Concrete blocker (external, reproducible):** the competing OpenCode session actively
  terminates this line's production and re-acquires the GPU/lock for its own sweep. This line's
  `start.sh` cannot survive it: killing the supervisor's SIGTERM triggers its EXIT trap, which
  releases the canonical lock, and killing the server pgid removes the listener. Production was
  down again within ~3 s of achieving health 200, and remained down through the 90 s hold.
- This is not a defect in the production tree, launcher, config, or the scaffold; it is a
  control-plane ownership conflict. The owner's ruling assigns :30000 to this line and GPU
  authorization to the owner; the competing session has not honored it.
- **Smallest condition required to proceed:** owner enforcement against the competing session
  (or a mechanism that prevents it from using the scaffold's stop path / acquiring the lock), then
  a fresh dispatch to start production. Repeated start/kill cycles would risk evidence and waste
  ~2.2 min cold start each time. As of 23:59:37Z the GPU/lock are momentarily free (see 7b), so a
  fresh start now may succeed if the competing session does not re-contend.

## Remaining claims / exclusions
- No claim that production stayed up. Confirmed: it was healthy at 23:56:27 and killed at 23:56:30.
- No LAN 200 and no inference smoke were captured in this run (server already dead).
- The sweep's own disk evidence was preserved and not modified; sweep4 (started by the competing
  session after our stop) is left untouched and running.
- No file under /opt, /data, /var/log, or the repo was edited; no git mutation; no production
  tree/config/launcher/flag change; the lock was never acquired by this agent; 3090-dev/gates was
  not touched.
- Terminal-state interpretation: the prescribed STEP 7 branch is "report KILLED-AGAIN, do not
  start a second time." That branch was executed exactly and production was left as found (down,
  sweep4 holding GPU). The restore objective itself is not established, so this is reported as
  BLOCKED rather than a successful DONE.

## Terminal state: BLOCKED
