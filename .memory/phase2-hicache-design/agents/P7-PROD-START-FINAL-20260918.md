# P7-PROD-START-FINAL-20260918 — Production start + hold

STATUS: BLOCKED

## Task
Start production (`:30000`) once under `OWNER-APPROVAL-20260918-PROD-START`, verify loopback +
LAN + one inference smoke, then hold-check for ~5 minutes and classify UP-PERSISTENT vs
KILLED-AGAIN. Leave production running. Do not kill or interfere with the competing sweep
session; no sweep, benchmark, load test, repo/git mutation, or lock acquisition by this agent.

## Scope
- Read/observe only, plus at most one `bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`.
- Witnesses: `/tmp/opencode/gpu-3090.lock`, `/tmp/opencode/prod-service-20260917/state/gpu-owner.json`.
- Owns ONLY this artifact. Task ID `P7-PROD-START-FINAL-20260918`, role `devops-executor`.

## Result
**BLOCKED — production was NOT started.** The promised clean window (reported free ~23:59:37) had
already closed before this invocation's first check: the competing session's `sweep5` cell 48
acquired the canonical GPU lock at `00:00:09Z` (generation 16) and, within ~2 minutes, brought up
its own server on `:30160` and began a sustained load run. It did not self-stop within the ~4-minute
bounded wait.

- Production `:30000`: **DOWN** (no listener; `curl` exit 7).
- New pid + run id: **none** (no `start.sh` executed).
- LAN HTTP code: **none** (no service to probe).
- Smoke: **not attempted**.
- Classification: **N/A / NOT STARTED** (neither UP-PERSISTENT nor KILLED-AGAIN — never started).

Stopping before `start.sh` was the correct fail-closed action, not an omission:
1. Procedure: "If the GPU is held by the competitor's sweep: do NOT kill it. Wait ... If it does
   not free within that bound, report BLOCKED with the evidence ... do NOT start a fight."
2. `start.sh` itself would have refused: `common.sh::gpu_material_holder()` treats any compute app
   `>= 2 GiB` as a material holder; the sweep server held ~22.6 GB. `start.sh` would `die`.
3. Launching anyway would have raced the competitor for the same lock/GPU, exactly the repeated
   kill cycle this task exists to avoid.

## Evidence

### Authorization (read and quoted)
- Approval id **`OWNER-APPROVAL-20260918-PROD-START`**, ledger
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md`
  **line 9520**; scope documented lines 9520-9535 (start `:30000`, identity-checked `start.sh prod`,
  no tree/config/launcher changes).
- Owner ownership ruling, ledger line 9599:
  > "你在负责这个 30000，GPU 控制权我负责。另外一个会话负责推进其他部分内容。"
  (This line owns `:30000` to this line; GPU authorization belongs to the owner.)
- Owner's sanctioned action, line 9609: "立刻**恢复并保持** `:30000` UP（引用
  `OWNER-APPROVAL-20260918-PROD-START`）."
- Ledger is concurrently appended by another session, as the dispatch stated; the approval id and
  owner ruling remain present and are quoted above.

### Window-free check — first check `00:00:20Z` (window already closed)
Raw `pgrep -af 'run_cell.sh|cell_supervise.sh|sglang.launch_server|load.py|supervise.sh'`:
```
1743336 /bin/bash -c cd /tmp/opencode/mamba-sweep-20260918/phase2 ... bash run_cell.sh 48 ... 30160 16 ...
1743340 bash run_cell.sh 48 sweep5-mamba48-20260918T000006Z-1743252 /data/l3/sweep5-... 30160 16
1743344 bash /tmp/opencode/mamba-sweep-20260918/phase2/cell_supervise.sh 48 sweep5-... 30160
1743374 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30160 ... --max-mamba-cache-size 48 ... --enable-hierarchical-cache --enable-ready-horizon ...
```
`ss -ltnp | grep -E '30000|30160'`: `NO LISTENERS` (at 00:00:20).
`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`: empty
(their server had not yet allocated GPU memory).
`/tmp/opencode/gpu-3090.lock`:
```json
{"owner": "sweep-cell-48-sweep5-mamba48-20260918T000006Z-1743252", "pid": 1743344, "generation": 16, "acquired": "2026-09-18T00:00:09Z"}
```
`/tmp/opencode/prod-service-20260917/state/gpu-owner.json` (stale, supervisor-exit):
```json
{"gpu":"GPU-2e3ed202-...","role":"free","state":"free","pid":null,"lock_generation":14,"updated_at_utc":"2026-09-17T23:56:29Z","note":"supervisor-exit"}
```
Interpretation: the free window reported at ~23:59:37 was consumed by the competitor at
`00:00:09Z`, ~11 s before this agent's first check.

### Bounded wait for self-stop (no interference, read-only)
Checks every ~25 s from `00:01:05Z`; sweep proc count / GPU MiB / listeners:

| time (UTC) | procs | GPU MiB | :30000/:30160 listeners | lock |
|---|---|---|---|---|
| 00:01:05 | 4 | 320 | 0 | gen16 sweep5 cell48 |
| 00:01:30 | 4 | 22140 | 0 | gen16 sweep5 cell48 |
| 00:01:55 | 4 | 22472 | 1 | gen16 sweep5 cell48 |
| 00:02:20 | 4 | 22906 | 1 | gen16 sweep5 cell48 |
| 00:02:45 | 4 | 22910 | 1 | gen16 sweep5 cell48 |
| 00:03:10 | 4 | 22910 | 1 | gen16 sweep5 cell48 |
| 00:03:35 | 4 | 22912 | 1 | gen16 sweep5 cell48 |
| 00:04:01 | 4 | 22914 | 1 | gen16 sweep5 cell48 |
| 00:04:26 | 4 | 22914 | 1 | gen16 sweep5 cell48 |
| 00:04:51 | 4 | 22918 | 1 | gen16 sweep5 cell48 |

Bound exhausted (~4 min): sweep5 cell 48 never self-stopped.

### Final state check `00:05:26Z`
- `pgrep`: same 4 sweep processes (run_cell.sh 48 / cell_supervise.sh / launch_server pid 1743374).
- `ss -ltnp`: `LISTEN 0 2048 0.0.0.0:30160 ... users:(("python",pid=1743374,fd=68))` — **no `:30000`**.
- `nvidia-smi --query-compute-apps`: `1743374, .../python, 300 MiB` + `1743490, sglang::scheduler, 22618 MiB`.
- `curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health` -> `curl: (7) ... Couldn't connect to server` / `000`.
- Lock: still generation 16, acquired `00:00:09Z` by the competitor.
- Competitor cell 48 progress (read-only, its own logs): `supervisor.log` shows
  `[00:00:09] canonical GPU lock ACQUIRED generation=16` ... `[00:02:00] cell-48 UP pid=1743374
  port=30160 lock_gen=16`; `logs-cell-48-sweep5.out` shows `smoke_http=200` and a `load` phase
  started `00:02:00Z`; `server.console.log` at `00:05:21` shows active prefill/restore traffic
  (`restore_state ... WAIT_CAPACITY reason=FRONTIER`, `#running-req: 2, #queue-req: 3`).

### start.sh output
**None — intentionally not invoked.** Invoking it would have either died on the material-holder
guard or raced the competitor's lock; both are outside the authorized procedure for an occupied
window.

### Lock generation history observed in this invocation
`generation 16` at `00:00:09Z` (competitor `sweep-cell-48-sweep5-...`, pid 1743344) — unchanged
through the end of this task at `00:05:26Z`. No generation change (no turnover to us).

## Defects / blockers
- **Window lost before start.** The clean window described in the dispatch (~23:59:37 free) closed
  at `00:00:09Z` when the competitor's sweep5 cell 48 took the canonical lock and GPU. This agent
  received the task after that point; first observation was `00:00:20Z`.
- **Competitor did not self-stop within the bounded ~4 minutes.** It progressed from lock
  acquisition to serving to a sustained load run, and shows no sign of stopping.
- **This is the same structural race already documented by prior attempts** (`P4` KILLED-AGAIN,
  ledger lines 9711-9748): the competing sweep loop repeatedly takes the card; production loses.
- No product/config/launcher/tree defect is implicated. No repo/git/lock action was taken by this
  agent; no competing process was signalled or interfered with.

## Remaining claims / exclusions
- **No claim** that production is up, persistent, or verified. `:30000` is DOWN.
- **No claim** about LAN reachability, inference, or hold behavior — none could be exercised.
- **Excluded by dispatch and honored:** no pkill/killall; no sweep/benchmark/load test; no edits
  under `/opt`, `/data`, `/var/log`, or the repo; no git mutation; no lock acquisition; no touching
  `3090-dev/gates/**`; no interference with the competitor's processes (observe only).
- The `gpu-owner.json` "free" record is stale (`lock_generation 14`, `updated_at 23:56:29Z`); it
  does **not** reflect the competitor's generation-16 lock. Authority for "who holds the GPU" in
  this window is the canonical lock file, not that state file.

## Terminal state
**BLOCKED**

### Smallest condition required to proceed (for orchestrator decision)
A genuinely free GPU+lock window that remains free for the full cold start (~132 s) and hold
interval, **or** owner/user arbitration to suspend the competing sweep loop during a bounded
production-start window. Per the dispatch, this agent does **not** start a fight and does **not**
kill the competitor; a fresh dispatch on a confirmed-free window is required. If a future window
opens, the procedure is unchanged: run exactly one `start.sh prod` (no second attempt after a
kill), verify, and hold-check.
