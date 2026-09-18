# P6-MAMBA-CORRECTED-AND-PROD-START-20260918

Status: WORKING
Task: Execute CORRECTED GPU mamba-sizing experiment (validate load reproduces production
`HOST_ALLOC["mamba"]` signature), measure sizes, choose smallest suppressing size, start
production on :30000 and hold.
ROLE: devops-executor
Artifact created at acceptance (WORKING).

## Task
Execute a CORRECTED GPU mamba-sizing experiment to completion, then start production on
`:30000` and hold it. This addresses the prior sweep being scientifically invalid (it
produced only `reason=FRONTIER` waits and ZERO `HOST_ALLOC`, so it never exercised the
production failure mechanism). One GPU window, sequential.

## Scope
In scope: identity-checked takeover of the GPU; derive+validate a load that reproduces the
production `HOST_ALLOC["mamba"]` signature at `--max-mamba-cache-size 48`; then measure 56
(and 64 if flat) with the SAME validated load; decide the smallest suppressing size; start
production via the scaffold `start.sh prod` and hold it.
Out of scope: source/config/tree edits; git mutation; touching `/data/l3/local-prod-v1.1`;
deleting/editing any existing evidence; pkill/killall; touching `3090-dev/gates/**`.

## Result
IN PROGRESS (WORKING stub — see terminal section).

## Evidence
### Authority (quoted approval ids)
- `OWNER-APPROVAL-20260918-PROD-START` (ledger line 9520) — owner's verbatim words recorded
  there include "w我让你把深产服务推上去，卧槽！" and "老子停下来是为了让你修缺陷"; approval
  content: (a) start production `:30000` immediately, (b) abort this line's mamba sweep to free
  GPU+lock, (c) restore via identity-checked `start.sh prod` (no pkill), (d) verify health/models
  + LAN `192.168.20.250:30000` + inference smoke.
- Ledger entry titled "⚠ OWNER 明令（第三次）：**Mamba 定档必须真跑出来**；授权本次 GPU 窗口"
  (owner's words: "Mamba 定档，让你跑，你妈逼要说几遍？") — explicit authorization of THIS GPU
  window: actually run 48/56/64 and give a sizing decision, then start production.
- Owner ruling entry: "OWNER 裁定（最终，终结一切争抢）：**本线负责 `:30000`；owner 负责 GPU 授权**"
  — this line owns `:30000`; GPU authorization is the owner's (granted for this window).

### Claim: production FAILED and scheduler-via-JSON-1.0 was BLOCKED (prior to this task)
Evidence at ACCEPTANCE:
- `ps`/`pgrep`: only the concurrent session's `launch_server --port 30160` (pid 1740265,
  `--max-mamba-cache-size 48`) and its supervisor (1740235, cell_supervise.sh), wrapper
  (1740231), and parent (1740227). **No** `launch_server --port 30000`.
- `/tmp/opencode/gpu-3090.lock` = `{"owner":"sweep-cell-48-sweep4-mamba48-20260917T235645Z-1740204","pid":1740235,"generation":15,...}`.
- `ss -ltnp`: only `0.0.0.0:30160`; nothing on `:30000`.
- `state/runs/prod.run`: last prod run `prod-20260917T235414Z-1738571`, cold start 133.0 s,
  started 23:56:27Z, then `/tmp/opencode/prod-service-20260917/logs/prod-20260917T235414Z-1738571/supervisor.log`
  shows `[23:56:29] WARN: supervisor exiting rc=0; releasing GPU lock` after
  `Subprocess detokenizer ... crashed with exit code -15` — an external SIGTERM killed prod
  (matching the ledger's recorded pattern of a competing session killing prod and restarting
  the sweep). `gpu-owner.json` state=`free`, note=`supervisor-exit`.

### GPU takeover (STEP 1)
All signals identity-checked against `/proc/<pid>/cmdline`; no pkill/killall.
- Server pid 1740265 cmdline confirmed `launch_server --port 30160` and referencing
  `/tmp/opencode/mamba-sweep-20260918/` → SIGTERM to process group `-1740265`; reaped within
  the bounded window (no KILL needed).
- Supervisor 1740235 (`cell_supervise.sh`), wrappers 1740231 (`run_cell.sh`) and 1740227 → TERM.
- POST-TAKEOVER: `pgrep -af 'launch_server|cell_supervise.sh|run_cell.sh'` (excluding the
  `bash -c` probe itself) → none; `nvidia-smi --query-compute-apps` → empty; `ss -ltnp` for
  `:30000|:30160` → ports free.
- Canonical lock fresh non-mutating probe (O_RDONLY + `LOCK_EX|LOCK_NB`, release, no write):
  **LOCK_FREE** (probe acquired then released). Lock file content still names the sweep4 owner
  (stale record; the flock is what matters).
- The concurrent session's hold-check wrapper pid 1741408 was left untouched (it is a bash
  poller, not a server/GPU holder; no authority/need to signal it).
- No sweep evidence was moved/edited/deleted; the sweep4 cell's files remain in place.

### Derived mechanism (from the frozen tree, read-only, and prod evidence)
- Production signature (42 occurrences, `/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/server.console.log`):
  `state=WAIT_CAPACITY reason=HOST_ALLOC` and `restore_host_alloc_retry_result` with
  `"failed_domains":["mamba"]`, mamba `free_before=0`, `required` 3436–3556,
  `retry_outcome="forfeited_alloc_failed"`.
- Code path (`unified_radix_cache.py` `prefetch_from_storage`): a storage restore first
  `prepare_prefetch`s stage buffers; the mamba component allocates **1 host slot**
  (`mamba_component.py:842-848`). If that alloc returns None and one reclaim pass cannot free a
  slot, the whole restore is forfeited → T3 WAIT[HOST_ALLOC]. Production had both
  `free_before=0` AND `evictable_before=0` ⇒ the mamba **host/L2** pool (~142 logical slots,
  `hicache_mamba_host_usable_tokens=142.0`) was full of slots pinned until L3 write-back acks.
- `--max-mamba-cache-size` sizes the DEVICE mamba pool; `--hicache-size 32` is split in
  proportion to device-pool bytes (`hybrid_pool_assembler._split_hicache_size`), so raising it
  also enlarges the mamba HOST pool at the KV-host pool's expense. This is the causal channel.
- Why the prior sweep did not reproduce: it used only `prefix-pool 64` at 16 384 tokens with
  `rounds=16`, and all 281 storage prefetches returned `storage_hit=0 (miss)` with
  `restore_disposition=RECOMPUTE` — no L3-hit restore ever staged, so the mamba host aux alloc
  was never attempted. Device `mamba usage` peaked at only 0.67. The corrected load must build
  distinct large-prefix mamba state (write phase) and then re-request it after L3 persist so the
  RESTORE→mamba-host-stage path actually runs under sustained pressure.

## Defects / blockers
(none yet)

## Remaining claims / exclusions
TBD

## Terminal state
WORKING
