# P1-PROD-RESTORE-20260918

- **Status:** BLOCKED (terminal)
- **Role:** devops-executor
- **Invoked:** 2026-09-17T23:36Z (UTC)

## Task

URGENT service restore. Bring production UP on `:30000` using the scaffold's
identity-checked lifecycle at `/tmp/opencode/prod-service-20260917/bin/start.sh prod`,
then verify health and LAN reachability. Premise supplied: production DOWN, port
30000 free, canonical lock free, GPU clean, `state/gpu-owner.json` = free/stopped,
all old prod PIDs gone.

## Scope

- Execute the already-defined procedure `bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`.
- Read-only pre-check of the supplied preconditions.
- If a **leftover MEASUREMENT server from a dead experiment** existed, stop it by
  identity-checked process-group means (step 2b).
- No file edits under `/opt`, `/data`, `/var/log`, repo; no git mutation; no pkill/killall;
  no lock acquisition; no manual launch unless start.sh is broken.
- Own only this artifact.

## Result

**NOT-UP.** Production was **not started**. `start.sh prod` was **never invoked** because
the mandatory step-1 pre-check failed: the GPU is **actively held** by a live mamba-sweep
measurement cell (not a dead experiment), port 30160 is bound, and the canonical GPU lock
is held at generation 10. The task's own instruction for this condition is: *"If any
condition is NOT satisfied ... STOP and report BLOCKED with raw evidence - do NOT force
anything."*

- New prod pid: **none** (nothing launched).
- LAN HTTP code on `:30000`: **N/A** (nothing bound on 30000).
- Smoke result: **N/A** (no production service).

Step 2 (stop a leftover MEASUREMENT server) **also correctly not executed**: the harness
run is not a dead experiment. It is live and mid-load, owned by an active process tree
(`run_cell.sh 56 ...`), with a `load.py` client in flight. Stopping it would interrupt
active measurement work, which is outside this invocation's authority ("production has
priority over any experiment" only applies to a *dead experiment*, per the task text).

## Evidence

### Step 1 — PRE-CHECK (raw)

`pgrep -af 'sglang.launch_server'`:
```
1730458 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30160 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 56 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-56-sweep2-mamba56-20260917T231910Z-1727975 --disable-prefill-cuda-graph
```

`pgrep -af 'supervise.sh'`:
```
1730428 bash /tmp/opencode/mamba-sweep-20260918/phase2/cell_supervise.sh 56 sweep2-mamba56-20260917T231910Z-1727975 /data/l3/sweep2-mamba56-20260917T231910Z-1727975 /tmp/opencode/mamba-sweep-20260918/phase2/logs/cell-56-sweep2-mamba56-20260917T231910Z-1727975 30160
```

`ss -ltnp | grep -E '30000|30160'`:
```
LISTEN 0      2048         0.0.0.0:30160      0.0.0.0:*    users:(("python",pid=1730458,fd=68))
```
(30000 NOT bound.)

`cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json`:
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
  "lock_generation": 7,
  "updated_at_utc": "2026-09-17T23:06:37Z",
  "note": "stopped"
}
```

`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`:
```
1730458, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1730557, sglang::scheduler, 23010 MiB
```
`nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader`:
```
23385 MiB, 100 %
```

`cat /tmp/opencode/gpu-3090.lock`:
```json
{"owner": "sweep-cell-56-sweep2-mamba56-20260917T231910Z-1727975", "pid": 1730428, "generation": 10, "acquired": "2026-09-17T23:30:57Z"}
```

### Process tree / liveness (identifies it as ACTIVE, not dead)

```
1730425       1 bash run_cell.sh 56 sweep2-mamba56-20260917T231910Z-1727975 /data/l3/sweep2-mamba56-20260917T231910Z-1727975 30160 16   (started 23:30:56, parent=init)
1730428 1730425 bash /tmp/opencode/mamba-sweep-20260918/phase2/cell_supervise.sh 56 ... 30160
1730458 1730428 python -u -m sglang.launch_server ... --port 30160 ...
1731044 Sl  /opt/sglang/.../python /tmp/opencode/mamba-sweep-20260918/phase2/load.py --base http://127.0.0.1:30160 ...   (STILL LIVE, elapsed 04:06 at check)
```

Cell supervisor log (`.../cell-56-.../supervisor.log`):
```
[23:30:57] canonical GPU lock ACQUIRED generation=10 owner=sweep-cell-56-sweep2-mamba56-20260917T231910Z-1727975 pid=1730428
[23:30:57] cell-56 launching on port 30160 (run_id=... l3=/data/l3/...)
[23:32:48] cell-56 UP pid=1730458 port=30160 lock_gen=10
```

`logs-cell-56b.out` shows the cell progressed launch -> ready -> smoke (HTTP 200) -> `--- load 23:32:49Z ---`, i.e. the load phase is in progress. `curl 127.0.0.1:30160/health` returned `200`.

### Why start.sh was not run

`bin/start.sh` step 2 (`gpu_material_holder`, `common.sh:252`) refuses when a material
compute holder (>=2 GiB) exists and "never signals it" (`start.sh:44-48`). With 23 GiB
held, `start.sh prod` would have died at step 2 by design. Running it would only have
produced a refusal.

## Defects / blockers

1. **False preconditions.** The dispatch asserted production DOWN, GPU clean (1 MiB / 0%
   util), lock FREE, no `launch_server`. Actual state at 23:36:27Z: `launch_server` pid
   1730458 on :30160, GPU 23385 MiB / 100%, canonical lock held generation=10. The
   dispatch's "verified read-only minutes ago" snapshot was already stale/wrong (a sweep
   cell started at 23:30:57Z and reached UP at 23:32:48Z).
2. **Stale owner file.** `state/gpu-owner.json` still says `state: free` / `note: stopped`
   with `lock_generation: 7`, but the live lock is generation 10 owned by the sweep. The
   owner file is not tracking the current holder; it cannot be treated as authoritative.
3. **Active (not dead) experiment.** Step 2b authorizes stopping a *dead* experiment's
   leftover server. This harness is live (supervisor + `load.py` in flight). Terminating
   it would halt active measurement work and release lock gen 10 — a material action
   outside this invocation's authority.
4. **Consequence:** production cannot start without either (a) the sweep cell completing
   and cleaning up, or (b) a fresh explicit authorization to stop the live sweep. The
   task explicitly forbids forcing.

## Remaining claims / exclusions

- No production service was started; port 30000 remains free; nothing was signaled or
  killed; no lock was acquired; no files under `/opt`, `/data`, `/var/log`, repo were
  modified; no git operations performed.
- The supplied `state/gpu-owner.json` reading is not evidence of GPU availability in the
  presence of the live lock; it is stale relative to lock generation 10.
- Whether the sweep cell is expected to finish soon is not determined from this
  read-only invocation; it is reported for orchestrator scheduling.
- The scaffold's lifecycle was inspected but not exercised.

## Terminal state: BLOCKED

Smallest condition required to proceed: the GPU-holding mamba-sweep cell
(supervisor pid 1730428 / server pid 1730458, lock generation 10) must be allowed to
complete its identity-checked teardown, **or** a fresh dispatch must explicitly authorize
stopping that *live* cell. After either, re-run the step-1 pre-check (expect no
`launch_server`, port 30000 free, lock free, GPU clear) before invoking
`bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`.
