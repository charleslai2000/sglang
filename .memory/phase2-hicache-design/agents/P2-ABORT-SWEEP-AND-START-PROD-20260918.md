# P2-ABORT-SWEEP-AND-START-PROD-20260918

- **Status:** BLOCKED (terminal)
- **Role:** devops-executor
- **Invoked:** 2026-09-17T23:38Z (UTC)
- **Finalized:** 2026-09-17T23:46Z (UTC)

## Task

URGENT dispatch to (1) terminate the live `mamba-sweep-20260918` measurement cell that holds
the GPU + canonical lock, and then (2) start production on `:30000` via
`bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`, with a specified verification
block. The dispatch asserts: *"The OWNER has demanded production be brought up immediately …
the orchestrator is explicitly authorizing you to TERMINATE the live sweep cell … This
overrides any earlier 'do not stop a live experiment' caution. Do not report this as a
blocker - ACT."*

## Scope

- Validate authorization, target, procedure, and rollback before any destructive action.
- Read-only re-identification of the sweep tree and current GPU/lock/port state.
- If valid: terminate the identified sweep process group (TERM→bounded wait→KILL, never
  `pkill`/`killall`), release the canonical lock, start production via the scaffold's
  identity-checked `start.sh`, and verify health/LAN/smoke.
- Constraints: no evidence edits/deletes; no edits under `/opt`, `/data`, `/var/log`, repo;
  no git mutation; no manual lock acquisition; no touching `3090-dev/gates/**`.
- Own only this artifact.

## Result

**BLOCKED — nothing was terminated, nothing was started.** The dispatch's authorization
premise does not hold against the project's own durable, binding owner control, so both
requested actions are outside this invocation's authority. Per the operating rule to stop
before an unauthorized or ambiguous action, I performed **no** teardown and **no** start.

- **Sweep aborted?** **No.** The live sweep is untouched (cells 48/48b/56b complete on disk;
  **cell-64 is live and mid-load**).
- **Production UP?** **No.** Port 30000 remains unbound.
- **New prod pid:** **none** (never launched).
- **LAN HTTP code:** **N/A** (nothing bound on 30000).
- **Smoke result:** **N/A** (no production service).

The concrete authorization defect:

1. The dispatch claims an immediate owner demand plus "orchestrator is explicitly
   authorizing" the termination and start. It cites **no** owner-approval record
   (no ledger activation, timestamp, or approval id).
2. The project's latest binding owner directive — `.memory/phase2-hicache-design/ledger.md`
   **activation #5, lines 9920–9949** — states, verbatim: **"停生产环境（`:30000`）必须经过
   owner 批准。未获批准，不得停/启/重启/信号生产。"** and CONTROL item 1 adds that **any
   停、启、重启、kill/signal、rebind, config, `--served-model-name`, host/port** change
   **"必须先取得 owner 对该具体动作的明确批准"**; item 2 requires that a dispatch that makes
   production stop/start a precondition **cite that approval**; item 5 says this control
   **overrides all earlier conflicting "mechanism" statements in the ledger, including ones
   this orchestrator wrote earlier**, and **"owner 明令 > orchestrator 推断."**
3. This dispatch rests on the orchestrator's own earlier ruling (ledger line 9382,
   "生产优先 ⇒ 中止 sweep") — exactly the class of orchestrator inference that owner control
   #5 was created to override. The dispatch repeats the pattern that activation #5 forbids.
4. The latest durable frontier (activation #8, ledger lines 10178–10204) records the M line /
   sweep as **AUTHORITY_BLOCKED**, pending an **owner** decision, and explicitly says production
   must not be moved without owner approval. No newer owner approval exists in the ledger or on
   disk for aborting the sweep or starting production (grep for this task id / new approvals →
   no matches).

Because the dispatch is an assertion of authority that the durable authority record does not
grant, and because executing it is destructive (a live, owner-window-authorized experiment)
and production-state-changing, I stopped rather than act. This is a genuine authorization
boundary, not a stale-premise report.

## Evidence

### E1 — Re-identification of the sweep tree and current state (read-only)

At 2026-09-17T23:45Z:

`pgrep -af 'run_cell.sh|cell_supervise.sh|sglang.launch_server|load.py'`:
```
1732497 bash run_cell.sh 64 sweep2-mamba64-20260917T231910Z-1727975 /data/l3/sweep2-mamba64-20260917T231910Z-1727975 30160 16
1732501 bash /tmp/opencode/mamba-sweep-20260918/phase2/cell_supervise.sh 64 sweep2-mamba64-20260917T231910Z-1727975 /data/l3/sweep2-mamba64-20260917T231910Z-1727975 /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-64-sweep2-mamba64-20260917T231910Z-1727975 30160
1732531 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30160 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 64 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-64-sweep2-mamba64-20260917T231910Z-1727975 --disable-prefill-cuda-graph
1733164 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python /tmp/opencode/mamba-sweep-20260918/phase2/load.py --base http://127.0.0.1:30160 --model /data/models/qwen35-9b-w4a16 --label cell-64 --concurrency 8 --rounds 16 --prefix-tokens 16384 --prefix-pool 64 --tail-tokens 256 --max-tokens 256 --timeout 900 --outdir /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-64-sweep2-mamba64-20260917T231910Z-1727975
```
- Note: **the dispatch's PIDs are stale.** The syscall tree has advanced cell 56 → cell 64
  (cell-56 completed at 23:40:14Z; cell-64 launched 23:42:17Z). PIDs changed from the
  dispatch's `~1730425/1730428/1730458/1731044` to `1732497/1732501/1732531/1733164`.

`ss -ltnp | grep -E '30000|30160'`:
```
LISTEN 0      2048         0.0.0.0:30160      0.0.0.0:*    users:(("python",pid=1732531,fd=68))
```
(30000 NOT bound.)

`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`:
```
1732531, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1732640, sglang::scheduler, 23174 MiB
```
`nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader`:
```
23547 MiB, 578 MiB, 100 %
```

`cat /tmp/opencode/gpu-3090.lock`:
```json
{"owner": "sweep-cell-64-sweep2-mamba64-20260917T231910Z-1727975", "pid": 1732501, "generation": 11, "acquired": "2026-09-17T23:42:17Z"}
```

`cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json`:
```json
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "free", "state": "free", "pid": null, "port": null,
  "run_id": "", "l3_namespace": "", "tree": "", "identity": "",
  "lock_generation": 7, "updated_at_utc": "2026-09-17T23:06:37Z", "note": "stopped"
}
```
(The owner file is stale relative to lock generation 11; also noted by prior `P1-PROD-RESTORE`.)

Identity confirmation: exactly **1** `sglang.launch_server` process, and its cmdline contains
`--port 30160` plus the `mamba-sweep-20260918` metrics dir; **0** `launch_server` processes
reference `--port 30000`. The tree is unambiguously the sweep, not production.

### E2 — Non-mutating canonical-lock probe (read-only)

```python
fd=os.open('/tmp/opencode/gpu-3090.lock', os.O_RDONLY)
fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
```
```
LOCK PROBE: HELD (busy): [Errno 11] Resource temporarily unavailable
```
→ Lock is genuinely held (by the live sweep, lock generation 11). No write occurred; fd closed.

### E3 — Sweep evidence inventory on disk (read-only; nothing moved/edited/deleted)

Per-cell outputs under `/tmp/opencode/mamba-sweep-20260918/phase2/logs/`:

| Cell dir | cell-48.json | load-summary | server.console.log | request-metrics | smoke.json | supervisor.log | status |
|---|---|---|---|---|---|---|---|
| `cell-48-sweep-mamba48-…1726566` | 30651 | 596 | 554365 | 9900611 | 544 | 450 | **completed** |
| `cell-48-sweep2-mamba48-…1727975` | 122360 | 604 | 3422185 | 13189361 | 544 | 453 | **completed** |
| `cell-56-sweep2-mamba56-…1727975` | 107377 | 608 | 3343070 | 13189111 | 544 | 455 | **completed** |
| `cell-64-sweep2-mamba64-…1727975` | (absent) | 0 | 860567 | 2478370 | 544 | 326 | **LIVE (mid-load)** |

`logs-cell-*.out` confirm the completed cells tore down cleanly:
```
--- cell 48 stopped 2026-09-17T23:16:59Z ---
--- cell 48 stopped 2026-09-17T23:30:05Z ---
--- cell 56 stopped 2026-09-17T23:40:14Z ---
--- cell 64 launch 2026-09-17T23:42:17Z ---
```
`state/`: cell-48, cell-56 complete; **cell-64.ready is 0 bytes** (still starting/loading).
Full inventory sizes were captured and are intentionally left in place.

### E4 — Why the authorization fails (binding record)

`.memory/phase2-hicache-design/ledger.md`, **activation #5, lines 9920–9949** (verbatim excerpt):
```
### 2026-09-18 — 激活 #5：⚠ OWNER 明令（最高优先级，覆盖一切既有"机制"）
> 停生产环境（:30000）必须经过 owner 批准。未获批准，不得停/启/重启/信号生产。
CONTROL — 新增硬约束（立即生效，不得由 orchestrator 放宽）
1. 生产 :30000 为 owner 所有。任何停、启、重启、kill/signal、改绑、改配置、改
   --served-model-name、改 host/port 的动作，必须先取得 owner 对该具体动作的明确批准。
   "有界窗口"、"会恢复"、"服务自带脚本"均不构成豁免。
2. 禁止把"停生产"作为任何子任务（含 tester/devops-executor）的前置步骤写入派单；
   除非 owner 逐次批准该次停启，并在派单中引用该批准。
5. 本条覆盖此前本 ledger 内任何与之冲突的"机制"表述（含本 orchestrator 早前写入的段）。
   owner 明令 > orchestrator 推断。
```

Earlier context that the dispatch leans on, and why it is superseded:
- `ledger.md:9354` — owner (earlier) said bring production up immediately.
- `ledger.md:9382` — orchestrator ruling "生产优先 ⇒ 中止 sweep" (the dispatch's basis).
- `ledger.md:9920–9949` — **later** owner control explicitly overrides prior orchestrator
  "mechanism" statements and requires cited owner approval for any production start.
- `ledger.md:10178–10204` (latest, activation #8) — M line/sweep recorded
  **AUTHORITY_BLOCKED**, awaiting an owner decision; production must not be moved without
  owner approval. Its ESCALATION asks the owner precisely whether to approve a bounded
  production window.

No owner approval for this action exists durably: `grep -rn 'P2-ABORT-SWEEP'` across
`.memory/**` and `/tmp/opencode` → **no matches**; no post-#8 owner approval entry.

### E5 — Safety of the declined actions

- Terminating cell-64 would destroy the third and final data point of the owner-authorized
  single-window sweep (ledger `8878`: "立即执行 Mamba sweep 48/56/64 … 不再就此事回头问
  owner"), while `state/cell-64.ready` is still empty and load is in flight — an irreversible
  loss of in-flight measurement.
- Starting production is a production *start* action expressly enumerated in control item 1
  and requires cited owner approval; none is present.

## Defects / blockers

1. **Invalid/uncited authorization (primary blocker).** The dispatch asserts owner demand +
   orchestrator authorization but cites no owner-approval record. Binding owner control
   (ledger #5) requires explicit, cited owner approval for any production start, and forbids
   orchestrator inference from relaxing it. The dispatch's own escape clause ("Do not report
   this as a blocker - ACT") attempts to preempt exactly that boundary and cannot override the
   project's authority record.
2. **Stale premises.** The dispatch's PIDs belong to sweep cell-56; by execution time the tree
   had advanced to **cell-64** (gen-11 lock). The dispatch's state snapshot was already stale.
3. **Destructive + production-state change.** The requested teardown is irreversible against a
   live, owner-window-authorized experiment; the start is a governed production action.
4. **Control-truth damage (known, ongoing).** The ledger is being concurrently appended by a
   second session, and per activation #4 the record has contained misattributed "external"
   artifacts. Treating an uncited dispatch assertion as authority is unsafe here.

## Remaining claims / exclusions

- No sweep process was signaled, stopped, or killed; the sweep remains live.
- No production service was started; port 30000 remains free; no lock was acquired.
- No file under `/opt`, `/data`, `/var/log`, the repo, or `3090-dev/gates/**` was modified;
  no sweep evidence was moved/edited/deleted; no git operation was performed.
- The canonical lock was probed read-only only (O_RDONLY + LOCK_NB, released; nothing written).
- The dispatch's stated *facts* are partly stale (PIDs) but its `:30000`-down and
  sweep-holds-GPU premises are currently true; only its **authority** is rejected.
- This artifact is my own; it does not decide the sweep's scientific result or the owner's
  scheduling choice.

## Terminal state: BLOCKED

**Smallest condition required to proceed:** the orchestrator must supply the **owner's
explicit, specific approval** (per binding control #5) to (a) start production on `:30000`
and (b) preemptively terminate the live sweep — cited by durable record (ledger activation +
timestamp/approval id) **in the dispatch itself**. Absent that citation, the correct action is
to await the owner decision the ledger's latest ESCALATION already requests.

Owned artifact: `.memory/phase2-hicache-design/agents/P2-ABORT-SWEEP-AND-START-PROD-20260918.md`
