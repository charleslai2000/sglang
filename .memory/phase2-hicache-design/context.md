# Phase 2 HiCache / RH takeover context

> **2026-09-16 BRANCH CONSOLIDATION — 先读这一段。**
>
> 本 repo 现在的 working branch 是 **`3090-24g-opt`**。原 `3060-12g-qwen35-4b` 已于
> 2026-09-16 快进合并入 `3090-24g-opt` 并从本地与 `origin` 删除；其全部 35 个 commit
> 现在都位于 `3090-24g-opt` 历史中。超集归档分支为 `3090-24g-hicache`
> @ `560f9ad525`（= opt + `3090-dev/` 的 22151 部署文档 4 files）。
>
> **下方 "Confirmed baseline" 是 2026-09-12 epoch 的冻结记录，其 `Branch` / `HEAD`
> 字段已过时**（当时 HEAD 为 `4f41f5ba`，早于 `993ef8e5` pre-v0.5.19 checkpoint）。
> 它保留作为历史证据，**不得**据此判断当前状态。
>
> 同样保持 epoch 语义、未随本次整合改写的文件（已知含过时 branch 字段，属刻意保留）：
> `plan.md`、`authority.yaml`（`run_epoch: G1-20260912`，其 digest 受 repin 纪律追踪）、
> 以及全部 `work/*2026090*` / `*2026091*` 日期化记录。
>
> 当前状态与接手入口：
> `HANDOFF-20260914-LOCAL-PROD-BASELINE-v1.md`、`WORK-INVENTORY-20260914.md`。

Updated: 2026-09-16 (branch consolidation banner) / epoch content dated 2026-09-12

## Goal

接续 `3rdparty/sglang-3090-24g-opt` 中 `.memory/phase2-hicache-design/` 的既有工作，严格区分 RH 当前验证线与 HOST_ALLOC epoch 治理线，不在未获授权时修改产品实现或运行 live 环境。用户已授权远程 3060 12G 实验实例；该实例后因主机不可达（Connection refused），用户进一步**授权改用本机 RTX 3090**（GPU 1，按 UUID 选择）作为 P0/P1/P2/P3 实验验证环境。3060 与 3090 均为实验环境、不是生产环境；生产环境未获授权。产品代码（`python/sglang/`）在本阶段不改。

## Confirmed baseline

- ~~Branch: `3060-12g-qwen35-4b`.~~（历史；现为 `3090-24g-opt`，见顶部 banner）
- ~~HEAD: `4f41f5bab562b99562f30c67540eb05344d13637`~~（历史 2026-09-12 epoch 值）
- Worktree is intentionally dirty: six tracked source/test files plus untracked `.memory/`, `review/gates/`, and `storage/` artifacts.
- Narrow RH speculative-budget retrigger gate is PASS only; it does not establish production or live-runtime acceptance.
- HOST_ALLOC epoch architecture remains blocked at G1/G2 admission: canonical Pattern Intake and accepted Novel Mechanism/design authority are absent.

## Verified latest evidence

- `.memory/phase2-hicache-design/work/SCOUT-TAKEOVER-20260911.md`
- `.memory/phase2-hicache-design/work/TEST-RH-SPEC-BUDGET-RETRIGGER-BROAD-20260911.md`
- `.memory/phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`
- `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`

## Current frontier

Verified gate status (supersedes earlier provisional counts above):

- **P0-A — VERIFIED DONE.** R28 ran all eight authorized commands on the 3060 experiment with exit 0; R29 independently verified transcript hash, command count, counts, local hashes, and scope. No product/test/gate/storage/Git change was made by this line.
- **P0-B — PASS, under storage-backed durability semantics (user ruling A′).** The complete live liveness chain is now real and frozen on the local 3090: `park -> real allocability change -> wake grant (FIFO predecessor) -> release -> accepted all-or-nothing finalize -> READY`. First achieved in R109 (7/11), then R113 (10/11; the durable leg's barrier missing) and R114 (R111 11/11). Acceptance chain (not mutated): R111 canonical reducer 11/11 but predicate 4 ruled **unsound/superseded**; R115 barrier-coverage FAIL retained as **telemetry incompleteness**, not product failure; **R116 storage-backed durability reducer PASS** on the FROZEN R114 bundle + frozen L3 evidence (target `d4cd1983…`, session `r114-c1` gen 10, build `1e3dbabc…`, prefix 27008; L3 query 27008 hits, `pc_get_v2` 27008 pages, `pc_l3_host` 27008, 8 target L3 objects on disk, finalize `kv_fetched=27008`). No further live R114/R115 workload required.
- **P0-C — 3060 profile/capacity freeze VERIFIED (R60/R61/R64/R62/R66).** The live-process/provenance bind (R68) is pending **and must be re-scoped to the 3090**, since the experiment environment pivoted. Next frontier: freeze the exact **3090** server profile/capacity semantics (R112 profile) that later measurements use.
- **P1 — VERIFIED / CLOSED (2026-09-12, user ruling Option 1).** The full live RH
  causal chain was demonstrated 4x on the fixed build (R125 run1 + R126 runs 1-3):
  `durable -> nonresident -> SPEC_BUDGET park -> release+1 -> RH wake -> HOST_ALLOC
  grant -> full KV+Mamba durable-boundary restore -> generation`, with
  `kv_fetched==D_req (27328)`, mamba 1/1, `durable-prefix recompute==0`,
  `hybrid_discard==0`. HOST_ALLOC wake-liveness fix = **VERIFIED by unit tests (18)
  + frozen real-event replay (R121 `raw.log:270076`: OLD=false -> NEW=true) + live
  regression**; NOT live-decisive exercised. Closure artifact
  `work/P1-CLOSURE-VERIFIED-20260912.md` sha256
  `9305d1b4bf764960359ea1c4ea35124aa7a79c56066a4b342067d94cb70b7e8e` freezes the
  8-predicate P1 oracle. Residual (NON-BLOCKING): no post-fix live workload made
  the new capacity-satisfied/generation-unchanged clause the deciding grant
  branch. Fix code: `python/sglang/srt/managers/scheduler.py` sha256
  `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7`.
- **P2-A — MEASURED (R129), three questions answered.** User approved
  observation-only instrumentation (env `SGLANG_P2A_TIMING_PROBE`, default OFF):
  probe patch verified (unit 14 + overhead ~13 µs/call + focused regression);
  server rebuilt/restarted with probe; **P0-C re-frozen R128**
  (`work/R128-profile/…`, real 6-producer digest `25391a5e…`). R129 collected a
  real 8-session/6-turn/59-request workload (514 s). Results (independently
  verified): **Q1 queue lead p50 1.694 s** (insufficient vs the stage);
  **Q2 L3->L2 stage 16.567 s** (n=1) with the storage query 92.6 % of it;
  **Q3 storage query p50 17.777 s / p99 22.278 s**, `backend_lookup` ~100 %,
  all `async_prefetch`. Root cause: `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE`
  defaults False -> full `os.scandir` of the 3,090,193-file L3 dir per query.
  Verdict: **architectural optimization candidate**. Residuals: Q2 n=1;
  `admission.v2` gap blocks the per-request Q1<->Q2 join. GPU released (lock
  FREE). `cache-induced idle` (#3) remains deferred to P2-B0.
- **P2-A = PASS / CLOSED (user ruling). Root cause confirmed.**
- **R130 follow-up A/B (in progress):** single live variable
  `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1` (contract
  `work/P2A-AB-METADATA-CACHE-CONTRACT-20260912.md` `7b319b1b…2bb8`). Live tester
  (`work/R130-bundle/`, GPU via flock, released on completion) + offline
  correctness coder (`work/R130-correctness/`, NO GPU: new-write-immediately-
  queryable, no-stale-hit-after-evict/TTL/GC, restart-rebuild, scandir-vs-key
  microbenchmark). Gates: Q3 -> <1 ms (ideal <100 µs), Q2 drop, no regression,
  init scan cost recorded separately. Sub-variable recorded (NOT changed):
  metadata TTL default 5.0 s. P2-B0 waits for this A/B.
- **P2-B/P3/Q — inventoried only, not executed** (R65 readiness table).

The local RTX 3090 is the authorized experiment environment (user-approved pivot). Executions still require a fresh Task ID. Results do not establish production acceptance, and execution may not bypass the P0 hard gates or the P1 causal chain. No product implementation/commit/deployment is authorized. Registered non-blocking observability follow-up: `durability_barrier`/`storage_persisted` under-report durable-but-unpromoted data, and `pc_*` L3 records lack session/build identity — either narrow the barrier semantics or add a per-build/per-prefix durable-coverage event.

Coordination note: two `.memory` roots exist (repository-root canonical vs `/home/dev-codex/workspaces/.memory/` sibling). The repository-root `3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/` is canonical; `work/INDEX-20260911.md` records the full per-report index.

## Boundary

Do not conflate RH verification with HOST_ALLOC governance. New work requires a fresh Task ID. Do not infer broader authorization from the remote 3060 authorization, a narrow PASS, or this context file. `query_storage_hit_length` remains measurement-only, and independent FP8 KV quality remains a blocker for final quality sign-off.

## GPU coordination (binding, user directive 2026-09-12)

The ONLY GPU coordination mechanism is the file lock `/mnt/data/gpu/3090.lock`
(`root:dev`, mode `660`; shared by `charles` and `dev-codex`). Other processes
also need the 3090. Acquire with
`exec 9>/mnt/data/gpu/3090.lock; flock -w 300 9` (the launch script does this).
The lock holder owns the GPU for the session; hold it ONLY for an active
experiment and RELEASE promptly when idle (stopping the server releases it).
Any subagent that runs GPU code must acquire this lock itself; no parallel GPU
work; log analysis needs no GPU. Serving the 3090 to other users is part of the
task, not optional.

## Extent L3 restoration (E0-E4, user redirect 2026-09-12)

- **E0 (read-only, COMPLETE):** `work/E0-BACKEND-IDENTITY-AUDIT-20260912.md`
  sha256 `bf126e3899078954046c605fa4e64007f889f13ff6f63e4725ff11411da7946d`.
  R129 used `HiCacheFile` because the launch argv says
  `--hicache-storage-backend file`; the 17.777 s/query is a legacy FileBackend
  full-`os.scandir` over 3,090,193 files (metadata cache default False), NOT a
  baseline. `ExtentFileBackend` (`backend_factory.py:201-205`, class
  `extent_file_backend.py:254`) is already registered and is a drop-in
  selection: full `HiCacheStorage` surface, RAM-authoritative
  `ExtentAllocator` index, generation invalidation, preallocated sparse extent
  file, batched preadv/pwritev, lazy watermark GC, no scandir anywhere.
- **Extent gaps (honest):** G1 no metadata persistence / restart rebuild (cold
  start; explicit in docstring + `test_crash_reopen_all_cold`); G2 defaults
  `extent=64 MiB`, `file_size=64 GiB`, `storage_dir=/tmp/hicache` must be set
  (R129 L3 = 133 GB); G3 `get_stats()` returns None (use `stats_snapshot()`);
  G4 one data file per rank; G5 no on-disk integrity check.
- **Gate classification:** E2 = deployment/selection (already-in-tree backend +
  config) -> EXEMPT-eligible; NOT a novel mechanism. In-scope storage corpus
  (`storage/review/gates/pattern-intake/`) does not cover the extent path;
  `storage/pattern` and `storage/testing` do not exist -> recorded corpus GAP.
  Any ExtentFileBackend code change (e.g. G1) is NON-EXEMPT and needs full
  Pattern Intake + Novel Mechanism gates first.
- **E2 frozen deployment values:** new script
  `launch-e-20260912.sh` (do NOT touch frozen `launch-r112.sh` sha
  `2259d406…8caaa3`); `--hicache-storage-backend extent`;
  `SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR="$D/l3-extent"` (NEW dir; `l3`
  preserved as R129 evidence); `FILE_SIZE=256G`, `EXTENT_SIZE=64M`,
  `MAX_SIZE=200G`, `MIN_FREE_SPACE=20G`; `launch-r112.sh`'s
  `SGLANG_HICACHE_FILE_BACKEND_*` vars are irrelevant to the extent backend.
  Log `sglang-server-e.log`; GPU via `flock /mnt/data/gpu/3090.lock`.
- **Final deliverable (3 questions):** (1) why R129 fell back to the
  3M-small-file path; (2) what ExtentFileBackend still lacks for production L3;
  (3) measured improvement of metadata query + L3 stage once extent + RAM index
  is restored (E4).

## E-phase RESULT (2026-09-12) — VERIFIED / CLOSED

- **E0** `work/E0-BACKEND-IDENTITY-AUDIT-20260912.md` `e3a610b0…e341`.
- **E1** `work/E1-EXTENT-L3-ARCHITECTURE-FREEZE-20260912.md` `156c7140…ceed`.
- **E2** `work/E2-EXTENT-DEPLOYMENT-20260912.md` `0613d99a…1c72`;
  `launch-e-20260912.sh` `d24195b9…651`; live `ExtentFileBackend`, one sparse
  file `l3-extent/hicache.data_...`.
- **E3** unit 77/77 OK `90110253…0a6e`; live v1-write->v2-query hit exercised.
- **E4** `work/E4-EXTENT-PERFORMANCE-20260912.md` `05670064…754a`:
  Q3 p50 **17.777 s -> 2.616 ms** (cold; miss path 2.392 ms, ~7,430x) and
  7.329 ms warm with 88 % L3 hits; Q2 16.567 s -> 304 ms / 445 ms; wall
  514 s -> 47.3 s / 19.1 s; 0 bad; L3 3.31 M files/133 GB -> 1 sparse file
  ~11 GB live.
- **Closure** `work/E-PHASE-CLOSURE-20260912.md` `143fb29d…` answers the 3
  questions.
- **Q1 = deployment selection** (`--hicache-storage-backend file`,
  metadata-cache default Off, `page_size=1` -> 3.31 M files, scandir/query).
  **Q2 = gaps** G1 restart-rebuild (open user decision), G2 sizing (fixed by
  E2), G3 stats None, G4 per-rank file, G5 no integrity check.
  **Q3 = measured** above.
- GPU: server stopped, lock FREE. Superseded R130 relaunched a legacy server
  mid-phase; contained with explicit-PID kills; legacy `l3` verified unmodified.

**Open decision requiring user authority: G1 ExtentFileBackend restart-rebuild
(no metadata persistence).** Any fix is a non-exempt product change; do not
proceed without explicit authorization. P2-B0 remains deferred.

## STANDING USER RULE (2026-09-12, authority): reasoning stability

User directive: stop flipping conclusions ("东倒西歪"). Binding rules for the
rest of this task:

1. **Freeze the problem definition before giving any conclusion.** For the RH
   line, the definition is fixed as:
   `提前恢复 durable prefix -> admission 前 ready -> 避免重复 prefill ->
   降低 task-switch/TTFT`.
   While that gate is open, CUDA Graph / Marlin TPS / C8 throughput are NOT
   mixed into it.
2. **Grade every claim.** Label each statement:
   - `FACT` — directly proven by existing logs / source / experiments;
   - `INFERENCE` — derived from facts;
   - `OPEN` — not yet proven;
   - `DECISION` — engineering ruling made on the evidence.
   Never present an assumption as a fact.
3. **Change a conclusion ONLY on new decisive evidence**, and write the change
   explicitly as `原结论 X; 新证据 Y; 因此修正为 Z` — never silently swap wording.

Frozen boundary (unchanged until this gate closes):

* P0/P1 = RH base correctness essentially closed.
* **Only mainline now = RH behavioral acceptance** (prove the durable prefix is
  pre-staged, admission is not followed by recompute of D, and TFTT/TTFT drops).
* The Qwen3.5-4B ~10 tok/s / CUDA Graph / 700-800 TPS question is a SEPARATE
  **Engine Performance** line and MUST NOT alter the RH correctness verdict.

## USER FORMAL RULING (2026-09-12): E-phase PASS/CLOSED -> P2-B0

- **E-phase = PASS / CLOSED.** Production L3 must be **ExtentFileBackend +
  RAM-authoritative index**. Frozen architecture: L3 = large extent/block IO +
  RAM index; legacy one-page-one-file + FS-as-DB is no longer production.
- Accepted: query 17.8 s -> 2.6 ms (~6800x); stage 16.6 s -> 304 ms (~54x);
  wall 514 s -> 47.3 s (~10.9x); 3.3 M files -> 1 sparse extent; 77/77; 33
  restores; 0 bad. R129 bottleneck = wrong L3 deployment, NOT RH.
- **Baseline = E4a.** R129 legacy figures = scalability-failure evidence only;
  excluded from production performance comparison.
- **Ruling 1:** Q3 query no longer the main blocker; do not chase 100 us now;
  fill p95/p99 later.
- **Ruling 2:** G1 restart-rebuild = production HARD GATE but does NOT block
  P2-B0. Direction: persistent compact metadata manifest/checkpoint +
  append-only delta/WAL -> restore RAM index at restart; never full-scan
  millions of objects. NON-EXEMPT product change, not yet dispatched.
- **Ruling 3:** G2 solved/non-blocking; G3 low-priority observability; G4
  (one file/rank) acceptable, do not change; G5 integrity needed AFTER G1
  (min: extent/block checksum + generation/length validation).
- **Next: P2-B0 immediately.** Measure cache-induced GPU idle; RH OFF/ON
  aggregate TPS; TTFT/TFTT; L3->L2 stage n>>2; queue lead vs ~300 ms; C1/C4/
  C5/C6/C8. `total_throughput` stays `not computable` (T4) pending a user
  definition — surfaced in writing, not substituted.

## Current U3 release-integration strategy (user decision 2026-09-13)

- Continue semantic merge of formal SGLang release tags; do not chase `upstream/main`.
- Keep correctness requirements unchanged: reconciliation contract, adversarial lifecycle tests,
  independent review, and runtime gates remain mandatory before merge/U4.
- Target no more than one formal release behind upstream.
- Per-release sequence: `new release -> dry merge -> overlap matrix -> semantic adjudication -> merge
  -> frozen regressions`.
- Long-term ownership boundary: upstream scheduler/runtime/model/tree/kernel structure; local linker
  lifecycle, RH policy, Extent L3, restart/WAL durability, and reconciliation/ownership contracts.
- Later refactor goal: reduce long-lived `scheduler.py` and `unified_radix_cache.py` forks to narrow
  adapter/interface seams after the v0.5.19 integration is complete.
- Repeatable regression corpus: storage unit, SIGKILL/reopen, KV+Mamba continuity,
  HOST_ALLOC/SPEC_BUDGET, R-HBA1 smoke, and Qwen 4B runtime smoke.

## U3 storage corpus reconcile (2026-09-13)

- Closed corpus exists at `/home/dev-codex/workspaces/nerun-dev/storage/{pattern,testing,review/gates}`;
  prior absence claims are stale.
- Fresh U3 intake artifact: `/mnt/data/nerun-dev/p3/U3-pattern-intake-reconcile-20260913/report.md`.
- Relevant lifecycle/shutdown, stale-identity, admission, publish-last, rollback, ownership-retention,
  and deterministic failure methodology: `ADAPT`; explicit no-inferred-success/pending-loss anti-patterns:
  `ADOPT`; distributed-chaos material for exact process-group acted-then-raised authority: `NOT_ADOPTED`.
- GAPs remain for Mooncake close/release authority, Python unlocked-reader publication atomicity, host
  release ACK, real fd/lock identity, distributed process-group acted-then-raised reconciliation, and
  complete U3 cross-products. Corpus is evidence only, not local PASS or design authority.

## Session handoff snapshot (2026-09-13)

- Compact handoff: `HANDOFF-20260913.md` in this directory.
- U3 latest bounded repair is staged; tester reports 20/20 attachment-model and 8/8 adversarial-model
  checks plus focused source checks PASS, all `MODEL_EVIDENCE_ONLY` where applicable.
- Independent reviewer task `U3-F2-F4-F6-F7-REVIEW-20260913` (`ses_f65a0c851ffeIEL2MFtX0yERZq`) is the
  only decisive active deliverable; expected report:
  `/mnt/data/nerun-dev/p3/U3-f2-f4-f6-f7-review-20260913/REVIEW.md`.
- Dependency-backed linker/Extent and product-runtime evidence remain BLOCKED by missing dependencies
  and external authorities. No merge commit or U4 is authorized.

## Final handoff update (2026-09-13)

- Latest independent reviewer artifact:
  `/mnt/data/nerun-dev/p3/U3-f2-f4-f6-f7-review-20260913/REVIEW.md` — **REJECT**.
- F1/F3/F5/F8 are structurally improved; F2/F4/F6/F7 remain open. Additional concrete residuals:
  legacy HiRadix host-release consumer does not acknowledge/remove successful pages and release identity
  lacks epoch/resource/release identity; all-epoch group reconciliation can poison reattach; and
  `staged_prefetch_tokens()` has undefined `device_prefix_len` plus tuple/scalar ready-horizon mismatch.
- Latest independent tester artifact:
  `/mnt/data/nerun-dev/p3/U3-f2-f4-f6-f7-test-20260913/VERIFICATION-REPORT.md` — 20/20 + 8/8 model
  checks PASS as `MODEL_EVIDENCE_ONLY`; dependency-backed/runtime BLOCKED; no U3 acceptance claim.
- All specialists are complete. Next session starts at bounded repair of the review findings; no merge
  commit or U4 is authorized.

## Durable memory-root authority (2026-09-13)

- This directory, `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/`, is the sole canonical coordination root for subsequent work on this task.
- `/home/dev-codex/workspaces/.memory/` is historical source only: it may be cited for provenance, but it is not the coordination authority and must not supersede this directory.
- This authority note records the user's current instruction; it does not alter product, test, Git, or unrelated memory state.

## Repair4/repair5/repair6 durable frontier (2026-09-13)

- Repair4 independent review was **REJECT**; its tester's 20/20 model result did not clear remaining
  RH/runtime errors.
- Repair5 fresh review was **REJECT** for F2 atomicity and cleanup/rollback/raw-fallback blockers; its
  source 20/20 tester result did not clear blocked runtime verification.
- Repair6 has only the coder source/model receipt at
  `/mnt/data/nerun-dev/p3/U3-repair6-20260913/receipt.md`; its six target paths are `MM` (staged
  baseline plus unstaged overlay), `MERGE_HEAD` is present, and unmerged count is zero. Fresh repair6
  review/test evidence has not been delivered.
- **U3 is NOT ACCEPTED.** Repair6 verification is pending/blocked. No merge or U4 is authorized; the
  broad staged merge is unaccepted. External authority blockers remain `FAILED_UNKNOWN`.
