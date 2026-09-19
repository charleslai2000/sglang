# MAMBA-F12-PARK-REGRESSION-20260918

Status: DONE

Terminal state: DONE

## Task

Terminal live verification: do the two already-completed code repairs (D1 + D2) actually
fix the Mamba L2 long-tail pin defect, verified against the REAL 42-park failure signature
on a live run?

## Scope

GPU-window authority granted to stop the port-30000 production server (M2), run a test,
and restore exactly the found state (M2). One result artifact only. No git operations, no
product-source edits, no model/tier changes, no `pkill`.

## Result

**PASS for D1 (the defect signature no longer reproduces); D2 remains unit-verified only and
is NOT independently live-observable in this run.**

Two live runs with the *same* deterministic backend-failure induction and the *same* load:

| Arm | Tree | Park events | WAIT_CAPACITY | admitted/failed | lock_release_evictable (in-run) |
| --- | --- | --- | --- | --- | --- |
| FROZEN (control) | frozen `src/python` only | **64** | 1334 | 189 / 3 (3 `TimeoutError`) | **0** |
| REPAIRED | frozen + ONLY D1/D2 | **0** | 0 | **192 / 0** | **2** (kv and mamba) |

Per-criterion:

1. **Generator advances — PASS.** Frozen stalls: first park 12:29:22, last park 12:39:09,
   load wall 937 s, TTFT max 184.06 s, 3 requests timed out, and 53 of 64 parks captured the
   same frozen mamba generation `77` (12:29:47 → 12:39:09, ~9.4 min). Repaired: 192/192
   admitted, 0 failed, wall 385 s, TTFT max 15.71 s, 0 parks, 0 `WAIT_CAPACITY`.
2. **Pins released DURING the run — PASS.** Repaired console lines 946–947 (raw
   `host_allocability_change`, `cause=lock_release_evictable`, `ts_wall_ms` 1789733666725/6)
   at 12:14:26, i.e. **6 min 16 s before** the 12:20:42 `SIGTERM`. Frozen: 0
   `lock_release_evictable` in the entire console (including teardown) ⇒ the real defect's
   "release only at shutdown" signature was reproduced by the control and removed by D1.
3. **`evictable_before` > 0 when a retry/alloc needs it — PARTIAL / NOT DIRECTLY OBSERVED.**
   The repaired arm never entered the park/retry path (0 `restore_host_alloc_wait`, 0
   `restore_host_alloc_retry_result`), so there is no retry event carrying
   `evictable_before`/`required`. What IS established is that in-run allocability changed:
   the D1 degradation path released pins and raised host evictable (kv `0 → 61`, mamba
   `0 → 1`). The literal criterion, and therefore D2's live unit correction
   (`required_aux_units` in real host slots), could not be exercised because D1 removes the
   park condition before a retry occurs.
4. **Behavior does NOT depend on shutdown to release pins — PASS.** The only two
   `lock_release_evictable` events in the repaired run are the in-run ones (12:14:26); no
   release occurred after `SIGTERM` at 12:20:42. Frozen released nothing in-run (0 events),
   and its host pool stayed pinned through teardown.

Concrete backend reason observed live: **H1 (swallowed exception) class, reproduced
deterministically** — the first L3 write raised `FileNotFoundError` from the native-writer
load. Frozen swallowed it silently (`except Exception: return False`; 0 failure logs).
D1 made it attributable (`Hybrid HiCache backup failed ... exception:FileNotFoundError`),
fatal (`HiCache storage thread backup_thread_func died`), and routed it through the existing
`storage_failure_reason -> _handle_storage_failure` in-run release
(`HiCache storage failure: ... Degrading: L3 queries/prefetches/writes are disabled`).
This is a *simulated* H1-class failure, not a re-observation of the original production
backend reason (which remains unestablished).

## Evidence

### E0. Pre-test live state captured before stopping anything
`/tmp/opencode/f12-park-regression-20260918/state/PRE-TEST-LIVE-STATE.txt`: M2 on :30000,
launcher pid 1764091 (flock holder), server pid 1764114 (`--model-path
/data/models/omnicoder-9b-gptq-int4`), scheduler pid 1764226, `gpu-owner.json` identity
`M2-OMNICODER-9B-GPTQ-INT4`, lock generation 21, `/health` HTTP 200.

### E1. Tree isolation (FACTS)
- Frozen hashes (`/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/...`):
  `unified_radix_cache.py` `5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f`,
  `hybrid_cache/hybrid_cache_controller.py`
  `4462403deb5b4975a5be95072cd344bb98a01dba78f10c40eb9aead08b843729`.
- These files' worktree HEAD blobs are byte-identical to frozen (`diff` empty), so the
  base is shared.
- `tree/` = frozen `src/python` + the two D1/D2 files:
  `unified_radix_cache.py` `4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b`,
  `hybrid_cache/hybrid_cache_controller.py`
  `d5ec3a761929087b0c3e69abb33a2f167381836e91a51dc00e75392c3fac3ee8`.
- `diff -rq` frozen `src/python` vs `tree/src/python` (excluding `__pycache__`/`.pyc`) =
  **exactly 2 differing files** (the two D1/D2 files). All concurrent reason/reasoning-effort
  worktree edits are excluded. `tree-frozen/` is a byte-identical frozen copy (hash above).
- `_fail_backup` present only in `tree/`; the D1 `raise RuntimeError(...)` present only in
  `tree/`.

### E2. Backend-failure induction (same in both arms, real product path)
Both servers launched the captured production argv with
`SGLANG_L3_NATIVE_WRITE_PATH=1` plus
`SGLANG_L3_NATIVE_WRITE_PATH_WORKSPACE=/tmp/opencode/f12-park-regression-20260918/probe/NO-SUCH-RUST-WORKSPACE`.
No product file was monkeypatched; only env differs from prod. Repaired raw traceback
(console line 893):
```
Hybrid HiCache backup failed (operation=8 node=19): exception:FileNotFoundError: Rust workspace for sglang.srt.rust_extensions._l3wal was not found at /tmp/opencode/f12-park-regression-20260918/probe/NO-SUCH-RUST-WORKSPACE
...
FileNotFoundError: Rust workspace ... was not found ...
```
Frozen console: `Hybrid HiCache backup failed` count = 0, `HiCache storage failure` count = 0,
`storage thread ... died` count = 0 (silent swallow — the H1 root-cause class).

### E3. Repaired in-run release (raw)
```
line 931 [2026-09-18 12:14:26] HiCache storage failure: backup_thread_func: RuntimeError: backup did not commit: exception:FileNotFoundError: ...
line 946 [2026-09-18 12:14:26] [HAE] {"evt":"host_allocability_change","cause":"lock_release_evictable","pool":"kv",   "generation_before":0,"generation_after":1,"evictable_before":0,"evictable_after":61,"returned_units":0,"telemetry_mutation_count":1,"ts_wall_ms":1789733666725}
line 947 [2026-09-18 12:14:26] [HAE] {"evt":"host_allocability_change","cause":"lock_release_evictable","pool":"mamba","generation_before":3,"generation_after":4,"evictable_before":0,"evictable_after":1, "returned_units":0,"telemetry_mutation_count":1,"ts_wall_ms":1789733666726}
```
`SIGTERM received` is at line 4298 / 12:20:42. The release at 12:14:26 precedes it by
6 min 16 s. Whole-console repaired `lock_release_evictable` count = 2 (both in-run).

### E4. Frozen control reproduces the REAL 42-park signature
- `restore_host_alloc_retry_result` = 64; `restore_host_alloc_wait` = 64; distinct mamba
  pool state at every park: `(free_before, evictable_before, reclaimed, alloc1, alloc2) =
  (0, 0, 0, None, None)` for all 64.
- First park 12:29:22 (`failed_domains=["mamba"]`, `retry_outcome="forfeited_alloc_failed"`,
  mamba `required=7933`, `free_before=0`, `evictable_before=0`, `reclaimed=0`).
- Park counts by captured mamba generation: `{55:2, 65:1, 68:6, 73:1, 75:1, 77:53}` — the
  last 53 parks are frozen at mamba gen 77 from 12:29:47 to 12:39:09.
- `hicache_backup_tokens_total{mamba}` reached and stayed 142 (pool size) for 124 samples;
  `hicache_dropped_tokens_total{mamba,host_pressure}` climbed to 39.
- Whole-console frozen `lock_release_evictable` = **0** (pins never released in-run, not even
  at teardown).
- Frozen load outcome: 189/192 admitted, 3 `TimeoutError: timed out`, wall 937.4 s, TTFT
  max 184.06 s.

### E5. Repaired outcome (raw load summary, verbatim fields)
```
"admitted_ok": 192, "failed": 0, "errors": [],
"wall_s": 385.371, "ttft_max": 15.7103,
"mamba_available_min": 0.0, "mamba_host_usable": 142.0
```
`restore_host_alloc_retry_result`/`wait`/`wake_decision` = 0; `WAIT_CAPACITY` = 0;
`hicache_backup_tokens_total{mamba}` reached 142 then continued; `extent_write` = 0 (L3 was
never usable in either arm — the very first write failed).

### Harness used (exact paths)
- `/tmp/opencode/f12-park-regression-20260918/f12_supervise.sh` (launch, adapted from
  `p6_supervise.sh`, same production argv).
- `/tmp/opencode/f12-park-regression-20260918/f12_run.sh` (smoke + load + in-run metrics
  sampler + identity-checked stop).
- `/tmp/opencode/f12-park-regression-20260918/p6_load.py` (copied from
  `/tmp/opencode/p6-mamba-20260918/scripts/p6_load.py`; C8, 24 rounds, 8192 prefix tokens,
  prefix pool 256, max_tokens 48, timeout 240 s, whole-load `timeout 1500`).
- Logs: `/tmp/opencode/f12-park-regression-20260918/logs/{repaired,frozen}-f12-*-1802823/`.
- L3 namespaces (fresh, unique, never cleared): `/data/l3/f12-repaired-20260918T120901Z-1802823`,
  `/data/l3/f12-frozen-20260918T120901Z-1802823`.

## Defects / blockers

1. **Criterion 3 is not literally observable.** After D1 correctly degrades L3 on the first
   failed backup, the repaired run never reaches the mamba host exhaustion that produces a
   `restore_host_alloc_wait`/`retry_result`, so no event carries `evictable_before` or the
   `required` slot value. The "allocability actually changes" property is shown only by the
   in-run release event (`mamba evictable 0 → 1`, `kv 0 → 61`), not by a satisfied retry.
2. **D2 is not independently live-verified.** Since no park occurs in the repaired arm, the
   D2 unit correction (real host-slot demand vs prefix tokens) is not exercised live. This
   is structural while D1 is fixed and is not a regression; D2 remains supported only by its
   canonical unit tests (23 passed per its artifact).
3. **The backend reason is a simulated H1-class one.** The induced `FileNotFoundError`
   (native-writer workspace) is an H1 "swallowed exception" shape, so it validates D1's
   reason-agnostic handling but does **not** re-observe the original production backend
   failure reason, which remains unestablished.

## Remaining claims / exclusions

- **Established (FACTS):** frozen reproduces the real park signature live (64 parks, mamba
  host full at 142, `free_before=evictable_before=reclaimed=0` every park, mamba generation
  frozen at 77 for 53 parks, 0 in-run releases, 3 request timeouts). Under the identical
  induction, D1 makes the backend failure attributable + fatal, routes it through the
  existing `storage_failure_reason -> _handle_storage_failure` path, releases pins in-run
  (mamba host evictable `0 → 1`, kv `0 → 61`) 6 min 16 s before shutdown, and the generator
  completes 192/192 with 0 parks. The `tree` binary contains ONLY D1/D2.
- **Could NOT establish:** the literal criterion-3 retry event; D2's live unit behavior; and
  the original production backend-failure reason (H1/H2/H3).
- **Not claimed:** that D1/D2 fix unrelated defects; that L3 works after degradation (it is
  intentionally disabled for the run); that capacity or split-ratio changes help; that the
  production 42-park incident is re-created exactly (the induction is a clean H1-class
  surrogate at the same seam).
- **Excluded:** no product-source edit; no git operation; no model/tier change; no ledger
  write; no `pkill`; only one `.memory` file (this artifact).

## Restored-state record (PIDs + health)

Found (pre-test): launcher 1764091, server 1764114, scheduler 1764226, identity
`M2-OMNICODER-9B-GPTQ-INT4`, lock generation 21, `/health` HTTP 200.

Restored (same model/identity/port, fresh run id/generation — process identity necessarily
changes because the process was restarted):
- launcher (flock holder): **pid 1808175** — `bash /tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh`
- server: **pid 1808198** — `python -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 ... --port 30000`
- scheduler: **pid 1808321** (`sglang::scheduler`)
- run_id `m2-cutover-20260918T124318Z-1808175`; gpu-owner.json lock_generation 24
- **loopback `/health` = HTTP 200**; `/v1/models` = `/data/models/omnicoder-9b-gptq-int4`;
  functional chat smoke = HTTP 200
- full record: `/tmp/opencode/f12-park-regression-20260918/state/RESTORED-LIVE-STATE.txt`

## Terminal state: DONE

D1 live-verified against the real park signature (criteria 1, 2, 4 PASS; criterion 3
PARTIAL/NOT DIRECTLY OBSERVED); D2 remains unit-verified only. Host restored to M2 and
healthy (`/health` HTTP 200).
