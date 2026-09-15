# P2/P3/Q Readiness Inventory — R65

- Task ID: `P2P3Q-READINESS-20260911-R65`
- Invocation: `ses-p2p3q-readiness-r65-20260911`
- Epoch: `2026-09-11`
- Role: `scout`
- Status: **done**
- ENTRY: `ACCEPT`
- Claim boundary: read-only readiness inventory only. This report executes no gate, runs no
  experiment, touches no remote host, and claims no acceptance. It does not modify product,
  test, gate, storage, or Git state. A listed procedure is a pointer to the already-frozen
  plan contract, not a new design and not a granted authorization.

## Resolution of the dispatch

- Dispatch is valid: role `scout`, read-only scope, no remote access, no edits. Accepted.
- `ENTRY: ACCEPT` — the requested deliverable (per-gate readiness table) is discoverable and
  decidable from local read-only artifacts.
- Report path resolved to
  `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P2P3Q-READINESS-20260911-R65.md`
  (cwd `/home/dev-codex/workspaces`, dispatch-relative `.memory/...`). The same task lineage
  (R59/R60/R61/R64) is materialized in this live `.memory` directory, so this is the correct
  durable target.
- No subagents were spawned. No IDs were created.

## Scope of inspection (search limits)

Read-only inspection of:

- Live coordination memory: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/` (R59–R64).
- Product worktree: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab562b99562f30c67540eb05344d13637`; dirty worktree:
  6 tracked modified files + untracked `.memory/`, `review/gates/`, `storage/`).
- Coordination worktree: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache`
  (branch `3090-24g-hicache`, HEAD `0a725c6385805f21138111e09bf69464ec29f1dc`).
- The two worktrees' `.memory/phase2-hicache-design/` plan/ledger/work trees, their `3090-dev/`
  scripts/tests, and targeted SGLang source under `python/sglang/srt/`.

Not inspected: remote 3060 host (`root@i-1.gpushare.com:27460`) or any other host; 3090 fleet /
s7070 / k3s; unrelated repositories; private memory outside `.memory/phase2-hicache-design`.
No experiment, import, compile, remote command, or edit was performed (this report is the only
new artifact).

## Authoritative design contract (single source for the table)

The detailed gate definitions live in the coordination worktree, not in the live `.memory`
directory:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md`
  — fixed gates/targets `:11-19`; P2-A1 `:63-71`; P2-A2 `:73-81`; P2-A3 `:83-91`;
  P2-B0 `:93-101`; P2-B1 `:103-111`; OUT-C2 `:113-121`; P3 `:123-131`; Q-FP8 `:133-141`;
  dependency/ownership `:143-150`; stop/evidence rules `:152-158`.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/plan.md`
  — approved order `:35-44`; scenario-specific TTFT gate `:59-63`.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md`
  — user decisions `:26-51` (`query_storage_hit_length` measurement-only `:45`; FP8 blocking `:46`;
  TTFT P95 scenario gate `:40-42`); R65 entry `:576-577`.

## Per-gate readiness table

Legend: **[READY]** existing vehicle suffices to start; **[PARTIAL]** some vehicle/evidence
exists but a mandatory piece is missing; **[MISSING]** no usable local vehicle.

| Gate | Required scenario (contract) | Existing evidence / vehicle (exact file:line) | Missing pieces | Minimal bounded procedure on the authorized 3060 |
|---|---|---|---|---|
| **P2-A1** lead-time | Real multi-turn agent/session workload; measure `B_enqueue → A_finished` lead, L3→L2 stage, Host-ready delay, admission delay, queue depth; no synthetic sleep / micro test (`plan.md:63-71`). | **[PARTIAL]** `sglang-3090-24g-hicache/3090-dev/cap_ratio_driver.py:1-31` — real client-load driver: N=8 agents, COLD prime + warm turns, `stream:true` true TTFT, per-req `ts/session/turn/prompt_len/ttft_s/wall_s/http/finished/device_hit/host_hit/storage_hit`. `gate2_warmctx.py` (runner copy in `.../phase2-hicache-design/work/gate2_warmctx.py`) — COLD/WARM true-TTFT precedent. Prior statement that lead/stage duration is unavailable: `.../work/HANDOFF-2026-09-10-48H-SUMMARY.md:69-72` and open decision `:86`. | No `B_enqueue`/`A_final_compute` monotonic marks; no queue-depth, stage start/finish, Host-ready, or admission-delay fields; no lead-time dataset; existing driver is the 3090 fixed-trace shape, not a 3060 agent trace. | Follow `plan.md:63-71`: new live authorization, exclusive single 3060 service/GPU/storage, run the real agent/session workload under the P1-frozen profile, emit per-request monotonic timestamps for enqueue/final-compute/stage/Host-ready/admission plus queue depth and deadline/miss classification; report distribution and edge list; do not infer lead from client wall/e2e. |
| **P2-A2** storage-query timing | Audit decode-side `query_storage_hit_length` on the task-switch critical path; per-sample enter/exit + backend / lock / syscall / future-event wait; thresholds p99<100µs ignore, 100µs–1ms observe, ≥1ms or disk-syscall/future wait candidate, ~10ms blocker (`plan.md:73-81`). | **[MISSING timing]** Caller: `python/sglang/srt/disaggregation/decode_hicache_mixin.py:84` inside `_build_decode_prefix_match` (`:61-99`). Impl: `python/sglang/srt/mem_cache/unified_radix_cache.py:5167-5210` (`_storage_hit_query` at `:5203`, group `MIN` all-reduce at `:5205`); `python/sglang/srt/mem_cache/hiradix_cache.py:1507-1541`; backend query `python/sglang/srt/managers/cache_controller.py:1293`. Read-side function notes: `.../work/p2io-tester-e7k.md:73`. | No enter/exit instrumentation on this function; no component decomposition. The only nearby histogram is a *whole* `load_back` timer (`python/sglang/srt/observability/metrics_collector.py:2236-2307`), which the contract explicitly forbids treating as isolated query time (`plan.md:78`). | Follow `plan.md:73-81`: observation-only probe (does not change API/scheduler), exclusive 3060 run, capture enter/exit boundaries and separate backend/lock/syscall/future-event attribution; if components cannot be separated, record the gap (no redesign, no new authorization inferred). |
| **P2-B0** contract | Versioned benchmark + capacity-matrix contract fixing C1/C4/C5/C6/C8, workload/window, denominators, failure handling, complete server-arg capture, and the production scorecard schema incl. `cache-induced idle` split into `restore_wait/queue_wait/compute/decode` (`plan.md:93-101`, `:16`; `:18`). | **[PARTIAL]** Schema precedent exists only as a report *about* a spec: `.../work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md:7` points to `homenet/server/gpu/3090-dev/phase2-scorecard-spec.md` — that file is **not present anywhere under `/home/dev-codex/workspaces`**. Metric-recompute precedent and `NOT MEASURABLE` list: `.../work/phase2-hicache-design-tester-scorecard-e1.md` (delta alignment `:14-19`; uncounted correctness `:138,:160`). Gate-level fixed rules already frozen in `plan.md:11-19`. | No versioned contract document; no frozen definition of the four idle/wait terms as measurable fields; `total_throughput` authoritative numerator/denominator/window unresolved (`plan.md:98,:166`). **Naming collision**: an earlier 3090 protocol used `C0–C5` as *mamba-ratio* tiers (`.../work/phase2-cap-protocol-architect-e1.md:108-115`), while `plan.md:18` uses `C1/C4/C5/C6/C8` as *concurrency* scenarios. | Follow `plan.md:93-101`: pure control-plane contract work (no runtime). Freeze scenario/metric formulas, disambiguate C-labels against the ratio-tier scheme, require complete server-arg capture per row, and block on `total_throughput` if no authoritative definition exists. |
| **P2-B1** main matrix | Execute C1/C4/C5/C6/C8 + capacity matrix under the frozen contract; per-scenario TTFT P95, wait breakdown, cache-induced idle, separated throughput fields, hit/restore/recompute, capacity/failure outcomes (`plan.md:103-111`). | **[PARTIAL]** Real 3060 decode sweep (RH OFF): `.../work/OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md:16-22` — c1=87.64, c2=24.24, c4=48.83, c6=73.06, c8=98.09 aggregate output TPS, 256 gen, short prompts, 0 HTTP failures; limits `:40-43`. R2 rerun: `.../work/OPS3060-DECODE-CONCURRENCY-SWEEP-R2-20260910.md:64-70` (NOT RUN/blocked). 3060 single-session restore: `.../work/OPS3060-HICACHE-RESTORE-R3-20260910.md:16-26` (GPU 0.230s / Host 0.391s / post-restart L3 38.301s). 3060 capacity points: `.../work/OPS3060-CONTEXT-CAPACITY-R3-20260910.md:18-23`. | No streaming-TTFT scenario runs; no L1-hit / L2-restore / RH-staged-L3 / cold-L3 workload classification; no idle/wait split; no per-row complete server-arg manifest; **c5 not measured**; `.../work/TEST3060-DECODE-CONCURRENCY-SWEEP-20260910.md:1` shows the sweep was once blocked on SSH approval. | Follow `plan.md:103-111` on the frozen profile: exclusive 3060 service/GPU/storage, run each scenario/C-row, emit per-row contract data or `not computable` (never infer zero), keep the six throughput fields separate, and derive gains only from matched completion sets; stop on health loss/OOM/zero-progress/args-hash drift. |
| **P3** soak/restart/pressure/fallback | Production qualification: soak, restart recovery, capacity pressure, fallback; full scorecard + raw run index with provenance, health, scenario P95, idle split, error/timeout/zero-progress, recovery/rollback (`plan.md:123-131`). | **[PARTIAL]** Soak vehicle (3090/p2-0-bound): `.../work/gate3_soak.sh:1-128` — 2h read-soak, locks, nvidia-smi sampler, SIGTERM cleanup; hardcodes `/root`, `/root/p2-0`, `MAX_SIZE=64G`. Restart precedent on 3060: `.../work/OPS3060-HICACHE-RESTORE-R3-20260910.md:36-41` (one real post-restart L3 resume after KV+Mamba durable ACK). Fallback: implemented only on the `3090-24g-hicache` branch — `.../work/phase2-hicache-design-coder-fallback-e1.md`, `.../work/phase2-hicache-design-tester-fallback-e1.md:15-42`, decision point `.../work/phase2-hicache-design-scout-fallback-survey.md:72-80`; flag `hicache_partial_restore_fallback` default off (hicache `server_args.py:2866`). Deterministic HOL heal unit (no GPU): `sglang-3090-24g-opt/3090-dev/test_p3_warmtree_hol.py:1-80`. | No restart driver/script; no pressure workload; no 3060 fallback vehicle — `test_partial_restore_fallback_unit.py` is absent from the `opt` (3060 product) worktree; no long soak on the frozen 3060 profile; no per-sub-run serialization provenance indexing. | Follow `plan.md:123-131`: run soak → restart → pressure → fallback as separate authorized, serialized sub-runs on the single 3060 service/GPU/storage, each with its own provenance/health/args-hash capture and declared rollback baseline; produce the production scorecard with the four idle/wait terms and per-scenario P95. Any fallback sub-run must first establish whether the fallback code exists on the frozen branch. |
| **Q-FP8** quality | Independent FP8 KV scale-factor quality: scale provenance/config, calibration/reference method, error/agreement metrics, coverage, limitations, and an independent pass/conditional/insufficient verdict (`plan.md:133-141`). | **[PARTIAL]** Frozen 3060 profile uses `kv_cache_dtype=fp8_e4m3` with `quantization_param_path: null` — `.../work/P0-C-PROFILE-FREEZE-20260911-R60.artifacts/r60_server_info.json` (and R60 md `:81`). Source warning for the default: `python/sglang/srt/server_args.py:623-635` ("KV cache scaling factors default to 1.0, which may cause accuracy issues"). Prior open decision: `.../work/HANDOFF-2026-09-10-48H-SUMMARY.md:91`. Correctness column is `NOT MEASURABLE` in `.../work/phase2-hicache-design-tester-scorecard-e1.md:138,:160`. | No confirmed scale provenance (whether any scaling JSON was supplied), no reference/calibration set, no quality/error metric, no verdict. No local FP8-KV quality harness found. | Follow `plan.md:133-141`: independent of P1/P2/P3; may prepare from P0-C. Establish exact scale source, then run an authorized calibration/quality measurement serially on the single 3060 (observation-only; never edit scale to make smoke pass). Keep the functional verdict and the FP8-quality verdict separate; absence/non-pass of Q-FP8 keeps final production quality sign-off blocked. |

### Vehicle inventory caveat (affects several gates)

Several drivers cited by the contract are **not present in either local worktree**; only copies
inside a memory `work/` directory were found:

- `gate2_warmctx.py`, `gate3_soak.sh`, `run-p2-decbm-cells.sh` — found only under
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/`.
- `gen_load.py` (invoked by `gate3_soak.sh:99`) and `phase2-scorecard-spec.md` — **not found
  anywhere under `/home/dev-codex/workspaces`**.
- `cap_ratio_driver.py`, `gate3_parked.py`, `gate3_capacity.py` exist in
  `sglang-3090-24g-hicache/3090-dev/` (and `gate3_parked.py`/`gate3_capacity.py` also in
  `sglang-3090-24g-opt/3090-dev/`), but `cap_ratio_driver.py` is absent from the `opt` worktree.
- `test_partial_restore_fallback_unit.py` exists only as compiled `__pycache__` in the hicache
  worktree and is not in the `opt` product worktree's `3090-dev/`.

## Explicitly protected constraints (verbatim-preserved)

These were re-checked against the frozen contract and must not be altered by downstream gates:

1. **`query_storage_hit_length` is measurement-only.** Do not change it at the P2-A stage
   (`plan.md:73-81`; `ledger.md:45`; `context.md` boundary).
2. **FP8 KV quality is independent and blocking for final quality sign-off.** Functional
   smoke/HTTP 200 cannot substitute (`plan.md:19,:133-141`; `ledger.md:46`; `:131`).
3. **TTFT `<1s` is a scenario-specific P95 gate only** for (a) an L1 hit, (b) an L2 restore,
   and (c) an RH-staged-to-Host-ready L3 request; **cold L3 is excluded** from the `<1s`
   requirement (`plan.md:15-16,:131`; `opt plan.md:59-63`; `ledger.md:40-42`).
4. **Single-3060 serialization**: every runtime task (P0-B, P1, P2-A1, P2-A2 live collection,
   P2-B1, OUT-C2, P3, Q-FP8 GPU collection) shares one exclusive 3060 service/GPU/storage lease
   and must run serially with a recorded serialization reason (`plan.md:149`; `:128`).
5. **No source/test/gate/storage/Git changes, no 3090/production access** under this
   authorization (`plan.md:3,:152-158`).

## Evidence anchors (high-traffic verification points)

- P2-A2 synchronous path: `decode_hicache_mixin.py:84` → `unified_radix_cache.py:5167-5210`
  → `cache_controller.py:1293`; tree variant `hiradix_cache.py:1507-1541`.
- Existing wait/state surface actually present (not a duration metric): `scheduler.py:3561-3739`
  (`hicache_restore_wait_timeout_s`, `RestoreState.WAIT_CAPACITY`, `RestoreWaitReason.HOST_ALLOC`);
  the only `queue_wait_seconds` histogram is encoder-scoped
  (`metrics_collector.py:2442-2501`), so the scorecard `restore_wait/queue_wait/compute/decode`
  split has **no current field**.
- Existing load-back timing (whole operation, not query): `metrics_collector.py:2236-2307`.
- 3060 profile freeze (feeds P2-B1 rows and Q-FP8): `P0-C-PROFILE-FREEZE-20260911-R60.md:71-100`.

## Summary

The P2-A/P2-B/P3/Q contracts are fully specified locally (`plan.md:63-141`) and map cleanly onto
readiness classes. **P2-A2 and Q-FP8 are the cleanest to start** (source anchors exist; each
needs only an observation-only probe / independent quality harness). **P2-B0 and P2-A3 are pure
control-plane** and need no 3060. **P2-A1, P2-B1, and P3 are runtime-gated**: reusable client
load mechanics and 3060 baselines exist, but the mandatory lead-time marks, scenario/idle-split
schema, restart/pressure drivers, and 3060 fallback vehicle do not. No gate is blocked by a
missing contract; the binding constraints are missing instruments plus the single-3060
serialization lease. The protected constraints above are intact and were not altered.

## Followups (for the orchestrator to dispatch as fresh tasks)

1. P2-B0 contract work can start as soon as P0-C/P1/P2-A1/P2-A2 inputs are complete
   (`plan.md:96`); it must disambiguate the C-label collision (`ratio tiers` vs `concurrency`)
   and block on `total_throughput` if undefined.
2. P2-A2 observation-only timing probe can be prepared against
   `decode_hicache_mixin.py:84` / `unified_radix_cache.py:5167-5210` without changing the API.
3. Q-FP8 scale-provenance confirmation against the frozen profile
   (`r60_server_info.json` / `server_args.py:623-635`) is independent of the functional chain.
4. P2-A1 / P2-B1 / P3 each require a fresh live authorization and the shared 3060 lease; none
   may be treated as accepting the P0 hard gate or the P1 causal chain.
5. Confirm whether any `opt`-branch driver is needed to backfill the missing local drivers
   (`gen_load.py`, `phase2-scorecard-spec.md`, `test_partial_restore_fallback_unit.py`).

## Open issues

1. **Code-revision identity**: the deployed 3060 revision cannot be proven equal to `opt` HEAD
   `4f41f5b…` (non-git checkout + no log banner; `P0-C-PROFILE-FREEZE-20260911-R60.md:102-109`).
   Any P2-B1/P3 row that binds a hash must resolve this first.
2. **C-label ambiguity**: earlier `C0–C5` meant mamba-ratio tiers
   (`phase2-cap-protocol-architect-e1.md:108-115`); the current `C1/C4/C5/C6/C8` are concurrency
   scenarios (`plan.md:18`). P2-B0 must freeze one meaning.
3. **Missing local artifacts**: `phase2-scorecard-spec.md`, `gen_load.py`, and the opt-branch
   `test_partial_restore_fallback_unit.py` were not found in the inspected scope; their
   authority/location is unknown.
4. **No idle-split metric exists**: `restore_wait/queue_wait/compute/decode` currently has no
   duration fields; `WAIT_CAPACITY` is a state, not a measured wait. This is a design gap for
   the scorecard, to be fixed by P2-B0 (not by this scout).
5. **P3 fallback availability on 3060**: the fallback patch is on the `3090-24g-hicache` branch
   only; whether it exists on the frozen 3060 branch is unverified.
6. **Q-FP8 scale source**: `quantization_param_path=null` in the frozen profile strongly
   suggests scale=1.0 defaults, but the actual calibration provenance is not confirmed.
7. This inventory is readiness evidence only and does not execute, verify, or accept any gate.
