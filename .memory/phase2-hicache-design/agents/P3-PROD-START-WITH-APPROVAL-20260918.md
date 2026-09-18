# P3-PROD-START-WITH-APPROVAL-20260918

Status: BLOCKED

## Task
Abort this project's own mamba-sweep cell, release GPU + canonical lock, start the frozen
production tree on :30000 via identity-checked `start.sh prod`, and verify health/models/LAN/smoke.

## Scope
One production start for the existing frozen tree. No tree/config/launcher changes. No v1.2.2 switch.

## Result
- **Approval located: YES** — section heading `### 2026-09-18 — ⚠⚠ 控制面碰撞：另一会话写入的「激活 #5」阻断了 owner 的直接命令；**记录 owner 明确授权（可引用）**`,
  approval id **`OWNER-APPROVAL-20260918-PROD-START`** (ledger line 9520). Scope matches dispatch exactly.
- **Sweep aborted: YES** — cell-64 tree stopped via identity-checked TERM (load.py), TERM
  (cell_supervise.sh + run_cell.sh), then TERM to the launch_server process group. Canonical lock released.
- **Production started and verified: YES, but NOT left running.** New pid **1734168**
  (supervisor pid 1734141), run_id **prod-20260917T234749Z-1733936**, lock_generation 12, cold_start 131.9 s.
  It answered `/health` 200, `/v1/models` 200, LAN `192.168.20.250:30000/health` 200, and a smoke
  completion 200. Then, ~13 s after ready, an **external competing session** terminated it (SIGTERM at
  23:50:14) and launched a fresh sweep cell that re-acquired the canonical lock.
- **Production UP at terminal write: NO** — down; GPU/lock now held by a new sweep (generation 13).
- **LAN HTTP code (while up): 200.**
- **Smoke (while up): HTTP 200**, model `/data/models/qwen35-9b-w4a16`, completion_tokens=16.

## Evidence

### Binding approval (quoted)
File: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md`
- Section heading: `### 2026-09-18 — ⚠⚠ 控制面碰撞：另一会话写入的「激活 #5」阻断了 owner 的直接命令；**记录 owner 明确授权（可引用）**`
- Approval ID: `OWNER-APPROVAL-20260918-PROD-START` (line 9520)
- Verbatim owner words recorded there:
  `"你妈逼之前的几个问题改好了没有，状态清单给我拉出来"`; `"w我让你把深产服务推上去，卧槽！"`;
  `"给老子马上改呀"`; `"老子停下来是为了让你修缺陷"`
- Granted: (a) 立即启动生产服务 `:30000`; (b) 中止本线自己的 mamba sweep（含其活跃 cell），释放 GPU 与
  canonical lock; (c) identity-checked `start.sh prod`（禁 pkill）; (d) 验证 `:30000` health/models +
  LAN `192.168.20.250:30000` + inference smoke.
- Scope: 仅上一次生产启动（含必要的中止 sweep）。不改树/配置/launcher；本次不切 v1.2.2.
- Match: dispatch scope identical to (a)–(d). No broader authority claimed.

### Fresh re-identification before teardown
- `run_cell.sh 64` pid=1732497 pgid=1732496; `cell_supervise.sh 64` pid=1732501 pgid=1732501;
  `launch_server --port 30160 --max-mamba-cache-size 64` pid=1732531 pgid=1732531;
  `load.py --base http://127.0.0.1:30160 --label cell-64` pid=1733164.
- `ss`: only 30160 bound; **ZERO launch_server on :30000**.
- lock: generation 11, owner `sweep-cell-64-...`.
- `nvidia-smi`: 1732531 (300 MiB) + 1732640 sglang::scheduler (23180 MiB).
- All four PIDs confirmed SWEEP by cmdline (`mamba-sweep-20260918/` and/or `--port 30160`).

### Sweep evidence inventory (read-only; NOT moved/edited/deleted)
`/tmp/opencode/mamba-sweep-20260918/phase2/logs/`:
- Completed: `cell-48-sweep-mamba48-...` (gen8, 96/96 ok), `cell-48-sweep2-mamba48-...` (gen9, 128/128 ok),
  `cell-56-sweep2-mamba56-...` (gen10, 128/128 ok).
- Incomplete: `cell-64-sweep2-mamba64-...` (gen11) — `load-summary.txt` 0 B; `logs-cell-64b.out` ends at
  `--- load 2026-09-17T23:44:06Z ---`.

### Teardown sequence and effect
1. TERM `load.py` pid=1733164 (identity OK) → exited ~4 s.
   (A first attempt used an over-strict pattern and refused; no signal was sent on the refused attempt.)
2. TERM `cell_supervise.sh` pid=1732501 + `run_cell.sh` pid=1732497 (identity OK) → both exited ~4 s;
   `cleanup` EXIT trap ran.
3. `kill -TERM -- -1732531` (pgid==pid, launch_server, identity OK) → server exited ~4 s. No KILL needed.
   No `pkill`/`killall` used anywhere.

### Clean-state verification (post-teardown, pre-start)
- `pgrep sglang.launch_server` none; `ss` no 30000/30160; flock probe `{"locked": false}` (FREE);
  `nvidia-smi --query-compute-apps` empty; `grep -i gpu-3090 /proc/locks` no entry.

### start.sh output (raw)
```
[23:47:30] === start role=prod port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate ===
[23:47:30] preflight: tree=/opt/sglang/local-prod-v1.2.1-candidate
[23:47:30] P2 manifest digest OK: 5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950
[23:47:30] P3 launcher sha OK: 4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5
[23:47:30] P4 launcher enforces the source-identity gate
[23:47:30] P5 launcher enforces the per-run L3 namespace gate
[23:47:40] P6 sglang.__file__ OK: /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/__init__.py
[23:47:49] P7 shared production L3 store present and MUST NOT be cleared: /data/l3/local-prod-v1.1
[23:47:49] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate
[23:47:49] port 30000 free
[23:47:49] L3 namespace (unique, never cleared): /data/l3/prod-20260917T234749Z-1733936
[23:47:49] supervisor pid=1734141 (holds the canonical GPU lock for the server lifetime)
[23:50:01] === prod UP ===
role=prod
pid=1734168
supervisor_pid=1734141
port=30000
tree=/opt/sglang/local-prod-v1.2.1-candidate
run_id=prod-20260917T234749Z-1733936
namespace=/data/l3/prod-20260917T234749Z-1733936
lock_generation=12
cold_start_s=131.9
started_at_utc=2026-09-17T23:50:01Z
START_EXIT=0
```

### Production verification while UP
- `pgrep`: pid=1734168 launch_server `--port 30000 --max-mamba-cache-size 48` (frozen launcher).
- `ss`: `LISTEN 0 2048 0.0.0.0:30000 ... pid=1734168`.
- `curl 127.0.0.1:30000/health` → `200`.
- `curl 127.0.0.1:30000/v1/models` →
  `{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16","object":"model","created":1789689004,"owned_by":"sglang","root":"/data/models/qwen35-9b-w4a16","parent":null,"max_model_len":131072}]}`
- `curl 192.168.20.250:30000/health` → `200`.
- Smoke (ONE request): HTTP 200; `{"id":"93b7629d...","object":"chat.completion",...,"usage":{"prompt_tokens":12,"total_tokens":28,"completion_tokens":16,...,"reasoning_tokens":16},...}`.
- `state/gpu-owner.json` at 23:50:01: role=prod, state=held, pid=1734168, port=30000, lock_generation=12, note=serving.
- lock at 23:47:49: generation 12 owner `supervise-prod-prod-20260917T234749Z-1733936`.

### Root cause of the terminal BLOCKED state (external competing session)
Timeline (from server.console.log, supervisor.log, gpu-owner.json mtimes, and sweep3 logs):
- `23:50:01` prod ready; all verification requests succeeded through `23:50:07`.
- `23:50:14` server.console.log: `SIGTERM received. signum=None frame=None. Draining requests and
  shutting down...`; supervisor.log: `[23:50:14] WARN: supervisor exiting rc=0; releasing GPU lock`.
- `23:50:26` `state/gpu-owner.json` note changed to **`stopped`** — the signature written by
  `bin/stop.sh` via `state_write_free "stopped"` (the supervisor's own trap writes `supervisor-exit`).
  This executor did NOT run `stop.sh`; this is an external actor using the scaffold's own identity-checked stop.
- `23:50:31` a new sweep cell was launched by another shell:
  `cd /tmp/opencode/mamba-sweep-20260918/phase2; RID=sweep3-...; setsid nohup bash run_cell.sh 64 ...`.
- `23:50:32` sweep3 supervisor.log: `canonical GPU lock ACQUIRED generation=13 owner=sweep-cell-64-sweep3-...`.
- Concurrent shell processes and SSH sessions from `192.168.1.203` are visible in `journalctl` around
  `23:49`–`23:50`; the dispatch itself warned the ledger is being concurrently appended by another session.

Terminal state now (raw):
- `pgrep`: `run_cell.sh 64 sweep3-...` (1737066), `cell_supervise.sh 64 sweep3-...` (1737070),
  `launch_server --port 30160 --max-mamba-cache-size 64 ... sweep3` (1737100).
- lock: `{"owner":"sweep-cell-64-sweep3-mamba64-20260917T235029Z-1737059","pid":1737070,"generation":13,...}`.
- `gpu-owner.json`: role=free, state=free, note=stopped. `ss`: no :30000/:30160 listener (sweep3 was still loading).

## Defects / blockers
**BLOCKER (control-plane collision).** The one authorized production start SUCCEEDED and was fully
verified, but an independent concurrent session terminated it within ~13 s (via the scaffold's own
identity-checked `stop.sh`, evidenced by gpu-owner note `stopped` at 23:50:26) and immediately
re-launched the mamba sweep (sweep3), which re-acquired the canonical lock (generation 13) and the GPU.
- The dispatch's acceptance condition (`:30000` up + LAN 200) held at 23:50:01–23:50:14 but does NOT hold at terminal write.
- Re-running production now would be a SECOND production start and would require terminating the
  sweep3 cell that the competing session just launched — a racing, ambiguous action outside this
  single-start authorization. Per the executor contract I stopped rather than broaden scope.
- **Smallest condition to proceed:** serialize the concurrent sessions (or confirm the competing
  session will not re-take the GPU), then dispatch a fresh single production start.

## Remaining claims / exclusions
- Teardown of the original cell-64 was completed and its on-disk evidence preserved untouched.
- No tree/config/launcher files were changed; no v1.2.2 switch; no git mutation; no pkill/killall.
- This executor did not acquire the lock, did not run `stop.sh`, and did not launch sweep3.
- The verified UP interval and its HTTP 200 evidence are real but were superseded by the external stop.
- The two concurrently-written control statements in `ledger.md` remain an unresolved structural risk
  for any future start/stop action; it is not this executor's authority to reconcile them.

## Terminal state
BLOCKED
