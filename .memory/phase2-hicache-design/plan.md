# Phase 2 takeover plan

## Scope and execution boundary

This is the user-approved execution order for the RH/HiCache verification and
measurement sequence. Every subsequent execution requires a fresh Task ID.
The remote 3060 12G experimental instance is explicitly authorized for P0/P1/P2/P3
experiment verification only. It is not a production environment; the 3090 and
production environments are not authorized. This plan does not authorize
product-code, test-code, review-gate, storage, or git changes. A local or narrow
PASS is not terminal acceptance.

RH verification and HOST_ALLOC epoch governance remain separate logical goals.

## Approved execution order

1. **P0-A — dependency-complete RH regression.** Restore/use an authorized
   dependency-complete environment and run the RH regression, including the
   required blocker-horizon classification.
2. **P0-B — HOST_ALLOC liveness hard gate.** Establish the complete liveness
   path: `not allocable -> park -> real allocability change -> wake ->
   successful restore`.
3. **P0-C — freeze exact 3060 server profile and capacity semantics.** Pin the
   exact server profile and the capacity semantics that later measurements and
   acceptance use.
4. **P1 — fresh blocker A/B causal closure.** The P1 gate must be one
   identity-consistent causal chain:

   `SPEC_BUDGET park -> reservation/release epoch transition -> RH wake ->
   L3->L2 stage -> Host-ready -> admission -> L2->L1 restore -> generation`.

   Verify `cached_tokens > 0`, `recompute(full-prefix) = 0`, and
   `hybrid_discard = 0`. Identity must remain consistent at least across
   `RID/session/node/build/generation`.
5. **P2-A — lead-time and storage-query measurement.** Measure lead time and
   storage-query behavior. `query_storage_hit_length` is measurement-only at
   this stage; do not change it.
6. **P2-B — scorecard and capacity matrix.** Run C1/C4/C5/C6/C8 and the
   capacity matrix. The scorecard must add cache-induced idle and split time
   into `restore_wait`, `queue_wait`, `compute`, and `decode`.
7. **P3 — soak/restart/pressure/fallback.** Verify the defined behavior under
   soak, restart, pressure, and fallback conditions.
8. **Independent Q — FP8 KV quality.** Treat FP8 KV quality as an independent
   line; it blocks the final production quality sign-off.

## Remote experiment authorization

- P0/P1/P2/P3 executions may use the explicitly authorized remote 3060 12G
  experimental instance.
- Every execution still requires a fresh Task ID.
- The remote instance is experimental, not production. Its results do not by
  themselves establish production acceptance.
- No execution may bypass the P0 hard gate or the identity-consistent P1 causal
  chain before later results are treated as acceptance evidence. Those prerequisites
  are now CLOSED under the user-ratified A′/Option 1 decisions; this is a historical
  ordering constraint, not an active blocker.
- This authorization does not extend to the 3090 or any production environment.

## Acceptance semantics

During the current correctness phase, `TTFT <1s` is an optimization target,
not a production gate. The final production gate is scenario-specific: P95
must be below 1 second for (a) an L1 hit, (b) an L2 restore, and (c) an L3
request already staged by RH to Host-ready. Cold L3 is excluded from this
TTFT gate.

The P0-B liveness condition was a hard gate, not an observational metric, and is
now CLOSED under A′. The P1 causal chain and its identity/semantic checks are also
CLOSED / VERIFIED; later scorecard work proceeds under its own contract.

## Current state / frontier

- `done`: P0-A dependency-complete RH regression is **VERIFIED DONE** (R28 clean
  3060 run, all eight commands exit 0; R29 independent verification of transcript
  hash, command count, counts, and scope).
- `done`: P0-C exact 3060 profile/capacity freeze is **VERIFIED** (R60 freeze;
  R61 independent review), with the documentation-only amendment R64 and residual
  closures R62 and R66; the provenance/live-process bind R68 is pending. P0-C does
  not reopen P0-B. **Re-scope note (2026-09-11):** the experiment
  environment pivoted (3060 unreachable -> user-authorized local RTX 3090), so the
  live profile/capacity freeze that later measurements use must be re-established
  for the **3090** (working profile already documented in R112). This is the next
  frontier after P0-B closure.
- `done`: P0-B HOST_ALLOC hard gate is **CLOSED / PASS under user-ratified A′
  storage-backed durability semantics**. R111 predicate 4 was superseded as unsound;
  R115 barrier coverage remains a recorded non-blocking telemetry incompleteness, not
  a product blocker. R116 storage-backed durability passed on the frozen bundle and
  was explicitly ratified in `ledger.md` (2026-09-11).
- **Historical pre-A′ gate (closed/superseded):** the former R111+R115
  `durable_frontier_coverage` requirement is retained as historical context only.
  It must not be used to reopen P0-B after the user's A′ ruling.

- **SUPERSEDED by user ruling A′ (2026-09-11):** the layered barrier-coverage
  requirement above is replaced. R111 predicate 4 is ruled unsound (matching only
  `session_generation`); R115's FAIL is retained as evidence of **telemetry
  incompleteness**, not product failure. P0-B durable semantics are now proven by
  the target prefix's REAL durable storage coverage + actual restore, joined on
  full identity. Acceptance = `R116 storage-backed durability reducer` exit 0 on
  the FROZEN R114 bundle + frozen L3 evidence. No live rerun; the old gates are not
  mutated to force PASS.
- P0-B current status: **CLOSED / PASS under storage-backed durability semantics**;
  R111 predicate 4 superseded/insufficient; R115 barrier coverage NOT VERIFIED
  (recorded as a non-blocking telemetry gap); no further live R114/R115 workload is
  required.
- P1 status: **CLOSED / VERIFIED** under the user's Option 1 ruling (ledger
  2026-09-12). P2-A/RH correctness closure is also recorded; P3 is the next
  production mainline and is not gated by the old P0-B wording.
- Current narrow RH speculative-budget retrigger evidence is PASS only; it does
  not establish production or live-runtime acceptance.

## Current frontier — P3 production stability qualification

P0-B (A′ storage-backed durability) and P1/RH behavioral correctness are CLOSED.
G1 restart-rebuild core is CLOSED / PASS; its GPU oracle is BLOCKED / NOT RUN only
because the gated checkpoint is inaccessible and host RAM is below the documented
threshold. Do not reopen any of these closures without new decisive evidence.

P3 is the next mainline and must be evaluated as production stability, not as a
repeat of G1 or the already-closed P0/P1 mechanisms:

`long soak -> repeated restart -> pressure -> eviction/restore -> fallback ->
corruption/crash handling -> no liveness loss`.

P3 acceptance must use separate serialized soak, restart, pressure, and fallback
sub-runs with provenance/health/argv or args-hash capture, explicit rollback, and
the production scorecard (scenario P95, restore/queue/compute/decode split,
cache-induced idle, error/timeout/zero-progress, recovery). Fallback availability
on the selected branch/environment must be established before its sub-run. This
frontier does not reopen P0-B or require another G1 experiment.

### P3 execution order — user-ratified 2026-09-13

P3 is **NOT READY**, not product FAIL. The deficit is acceptance vehicle
infrastructure; P0-B, P1/RH, and G1 remain CLOSED and must not be reopened absent
new decisive product evidence. The approved bounded order is:

1. **Common P3 harness substrate:** one shared substrate for GPU `flock`, exact PID
   ownership, source/profile/argv/hash provenance, health gates, timeout/
   zero-progress/health-loss fail-fast, artifact namespaces, cleanup/rollback, and
   prohibition of `pkill -f`.
2. **Restart vehicle:** start -> seed durable KV+Mamba -> exact-PID SIGKILL ->
   restart -> rebuild index -> restore -> identity/byte equivalence.
3. **Pressure/eviction wrapper:** reuse existing `gate3_capacity.py` and
   `gate3_parked.py`; add only wrapper/oracle behavior for eviction, HOST_ALLOC,
   L1/L2/L3 restore, starvation, zero-progress, and corruption detection.
4. **Crash/corruption/liveness vehicle:** torn active WAL repair, committed
   corruption fail-closed, stale-generation no resurrection, process crash/recover,
   and no permanently parked request.
5. **Fallback capability decision:** audit whether partial-restore fallback belongs
   to the frozen production contract. Do not implement it as part of P3. A contract
   gap requires a separate authority/design gate; an out-of-contract experiment is
   not added.
6. **Long soak last:** only after the short-cycle vehicles pass, run the 12–24 hour
   soak with the same substrate.

Authorized scope now includes the narrow GROUP_COMMIT replay temporal-barrier fix and
its adversarial storage tests, as explicitly ratified on 2026-09-13. It excludes the
fallback capability, scheduler/HiCache redesign, and unrelated storage changes. Any
live test product defect must return to authority review rather than being fixed by a
vehicle implementation.

### P3 readiness status (2026-09-13)

P3 is **PARTIAL / NOT READY**, for vehicle reasons only:

- pressure/eviction workload assets exist in `3090-dev/` (`gate3_capacity.py`,
  `gate3_parked.py`), but no P3 wrapper provides frozen-profile binding,
  provenance/args-hash capture, rollback, health-loss, timeout, or zero-progress
  termination;
- no current-branch long-soak driver was found;
- no current-branch repeated-restart driver with exact PID/health/provenance and
  post-restart extent/G1 assertions was found;
- `hicache_partial_restore_fallback` and its test are absent from this `opt`
  branch; evidence in the other worktree is not transferable;
- no current-branch corruption/crash/no-liveness-loss P3 vehicle was found.

No P3 runtime acceptance sub-run is authorized by this readiness state. These are
P3 vehicle/capability gaps, not reopened P0-B, P1, or G1 blockers.

## Evidence baseline

- Branch: `3060-12g-qwen35-4b`.
- HEAD: `4f41f5bab562b99562f30c67540eb05344d13637`.
- Broad local verification is blocked because `pytest` is absent and stdlib
  fallback collection lacks `orjson`; the prior six-failure classification is
  not freshly reproduced in the takeover environment.
- Relevant evidence: `work/SCOUT-TAKEOVER-20260911.md`,
  `work/TEST-RH-SPEC-BUDGET-RETRIGGER-BROAD-20260911.md`,
  `work/ARCH-20260909-HOST-ALLOC-EPOCH.md`, and
  `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`.

## R124 frontier — HOST_ALLOC wake-liveness fix, rebuild, re-freeze, replay (user-authorized 2026-09-12)

User authorization verbatim: "apply minimal HOST_ALLOC wake-liveness fix, rebuild/
restart the 3090 server, re-freeze P0-C against the new source build, then rerun
the R121-faithful P1 acceptance. No profile change, no workload redesign, no
additional product changes unless the replay exposes a new independent failure."

Frozen execution order:
1. source minimal fix + unit tests PASS (in progress: coder `ses_f6e76e7f…` adding
   protection-#3c/#3d coverage + focused regression);
2. dependency-complete focused regression (host-alloc + lineage + scheduler feed +
   drain reentry + ready-horizon + prefetch budget split + storage regression);
3. restart the 3090 server to load the new code;
4. re-freeze P0-C (new profile freeze; source_build/profile_id/run_id/process ids
   change) — R117 stays immutable, a NEW freeze dir is created;
5. R121-faithful live replay;
6. check `feasible -> wake -> FULL durable restore`.

Restart procedure (verified facts):
- Server PID 48746 = the bash launch script after `exec` into
  `python -B -m sglang.launch_server`; child scheduler 48806; cwd
  `/home/dev-codex/workspaces`; stdout/stderr -> `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log`;
  it holds `/mnt/data/gpu/3090.lock` on fd 9.
- Relaunch MUST reuse `/mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh`
  (so `launch_script_sha256` and the frozen profile are unchanged).
- **MUST NOT overwrite `sglang-server-r112.log`** — R117/R121/R122/R123 evidence
  cites its line numbers. Redirect the new server to a NEW log
  (`sglang-server-r124.log`).
- After restart: confirm `/health` 200, capture new PIDs, argv, provenance markers
  (`process_id`, `run_id`, `profile_id`, `source_build`,
  `deployment_manifest_digest`) from the live process/log, and the L3 stats; then
  write the new freeze.

P0-B is NOT redone: the diff touches only scheduling wake eligibility, not
durability/storage semantics. R114/R116 remain the P0-B closure evidence under the
previous build; the new freeze records that its R114 cross-check binds the OLD
source_build (documented, not weakened).

P1 final gate (unchanged): FULL_DURABLE; NON_RESIDENT; SPEC_BUDGET park;
exactly-once release epoch +1; `t_feasible < deadline`; wake not blocked by an
irrelevant domain's generation; `kv_fetched == D_req`; Mamba restore complete; no
durable-prefix recompute; no hybrid discard; HTTP completed. PASS => P1 CLOSED,
no R124/R125 new recipe.

## Current todo (frontier projection; durable truth = ledger.md)

Last synced: 2026-09-13, after G1 core closure. P0-B and P1 remain CLOSED; the
next production mainline is P3 soak/restart/pressure/fallback. The G1 GPU E2E
oracle is separately BLOCKED / NOT RUN by environment prerequisites and is not a
G1 core or P0-B blocker.

- [x] R125 independent verification (report accurate; Gate 2 NON-EVIDENCE
      confirmed; nonce text defect p1->p3 confirmed).
- [x] Freeze R126 contract `work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md`
      sha256 `13ba59c06902d9e7cb2bc205ee7b9118776122e67f3eee107980ce8fdc1667b7`.
- [x] R126 independent verification: report accurate (`23ed5d48…0267e2`),
      bundle 38/38 + per-run 9/9 checksums OK. Gates 0/1/3 PASS 3/3; Gate 2
      NON-EVIDENCE 3/3. P1 = NOT_VERIFIED. No product defect (harness timing).
- [x] P1 CLOSED / VERIFIED per user ruling (Option 1). Closure artifact
      `work/P1-CLOSURE-VERIFIED-20260912.md` sha256 `9305d1b4…b7e8e`; residual
      (new clause not live-decisive) recorded as NON-BLOCKING.
- [x] P2-A scoping: R127 telemetry-coverage scout verified independently
      (`dc29b412…a4cd`). Findings: #1 PARTIAL (existing opt-in flag only), #2
      PARTIAL (no per-attempt mono issue mark), #3 NEEDS_NEW_PROBE (GPU
      timeline), #4 NEEDS_NEW_PROBE (enter/exit + component split).
- [x] P2-A authorization: user approved `Option 1 + A=3090/prefetch-side +
      B=defer #3 to P2-B0`.
- [x] P2-A measurement contract FROZEN:
      `work/P2A-MEASUREMENT-CONTRACT-20260912.md` sha256 `c0551708…1096a`.
- [x] P2-A probe patch implemented (coder) + INDEPENDENTLY VERIFIED:
      py_compile OK; new unit test 14 OK; overhead 3 OK (full emit ~13 µs/call);
      focused regression host_allocability 18 / storage_regression 0-exit /
      scheduler_feed 46 / ready_horizon 74 / prefetch_budget_split 24 all OK.
      Bound shas: probe `96d077b8…0804`, scheduler `e58ca012…b853`, radix
      `212c3a8f…067f`, hybrid `64e933f4…e4d5`.
- [x] Server restarted with the probe (`SGLANG_P2A_TIMING_PROBE=1`), NEW log
      `sglang-server-p2a.log`; parent `616394`, scheduler `617035`; health 200.
- [x] P0-C RE-FROZEN (R128):
      `work/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md` sha256
      `5673146b…0d019`; real 6-producer digest `25391a5e…851e`; `launch-r112.sh`
      unchanged; argv 59 tokens byte-identical.
- [x] P2-A collection contract FROZEN:
      `work/P2A-COLLECTION-CONTRACT-20260912.md` sha256 `1b9c2969…3b26`.
- [x] P2-A live collection (R129) DONE + INDEPENDENTLY VERIFIED. Report
      `work/P2A-LIVE-COLLECTION-20260912-R129.md` `f3e32ee5…db17a`; verification
      `work/R129-bundle/P2A-ORCHESTRATOR-VERIFICATION.md` `23a7a5fd…1b21`.
- [x] Three P2-A questions ANSWERED:
      (1) queue lead NOT sufficient in general (Q1 p50 1.694 s vs stage 16.567 s);
      (2) L3->L2 stage ~16.6 s, dominated by the storage query (92.6 %);
      (3) query YES architectural (Q3 span p50 17.777 s / p99 22.278 s vs the
      >=1 ms optimization band). Root cause: `enable_metadata_cache` default
      False -> full `os.scandir` of the 3.09M-file L3 dir per query.
- [x] **P2-A = PASS / CLOSED** (user ruling). Root cause confirmed.
- [x] GPU released after R129: server stopped, `/mnt/data/gpu/3090.lock` FREE.
- [in_progress] **R130: single-variable A/B APPROVED + dispatched**.
      Contract `work/P2A-AB-METADATA-CACHE-CONTRACT-20260912.md` `7b319b1b…2bb8`.
      Live variable: `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1`.
      - tester `ses_f6cf86793ffeMwtiAhcumMMSGg` -> `work/R130-bundle/` (GPU via
        flock, released on completion).
      - coder `ses_f6cf848cbffeONprDJbpY2IpKl` -> `work/R130-correctness/`
        (offline correctness (a)/(b)/(c) + scandir-vs-key microbenchmark; NO GPU).
      Gates: Q3 -> <1 ms (ideal <100 µs); Q2 drop; no regression; init cost
      recorded separately; correctness (new write immediately queryable, no stale
      hit after evict/GC, restart rebuild).
      Sub-variable recorded (NOT changed): metadata TTL default 5.0 s.
- [pending] On R130 results: if Q3 sub-ms but Q2 still ~10 s+ -> next cost is L3
      data transfer / scheduler / finalization. Then proceed to P2-B0 (owns
      `cache-induced idle`).
- [pending] Residual: Q2 n=1; `admission.v2` telemetry gap on the
      prefetch-restore path blocks the per-request Q1<->Q2 coverage join.

P1 final-gate note: the R126 contract's Gate 3 uses corrected durable-boundary
semantics (`kv_fetched == D_req`; external tail `requested-D_req=11` may read
PARTIAL/shortfall; `n_tokens == granted-2` accepted only with `kv_fetched ==
D_req`). This is a pre-run contract correction, NOT a retro-change to R125.

## RESOLVED user decision (2026-09-12): Option 1 accepted

The P1 acceptance decision was resolved by the user: **P1 = VERIFIED / CLOSED**
with the residual recorded as NON-BLOCKING (see closure artifact
`work/P1-CLOSURE-VERIFIED-20260912.md`). Option 2 (forced workload) and Option 3
(hold open) were NOT chosen. P1 closure is a user ruling, not a self-graded PASS.

## Current boundary: P2-A instrumentation authorization

P2-A measurement requires either new observation-only timing marks or an existing
observability flag, plus fresh live runs. The authoritative contract (plan.md
`:63-91`: P2-A1 "单独 live authorization"; P2-A2 "若已有 telemetry 不足，需要单独
profiling/live authorization；使用 observation-only probe") makes this a SEPARATE
authorization. Global rule 2 requires explicit user authorization before
introducing instrumentation. Two scope conflicts were also found:

- the contract targets a 3060 PD-disaggregation decode path, but the frozen live
  profile is `disaggregation_mode: 'null'` (the `__storage_hit_query__` sync
  discriminator is absent from the live probe log); and
- `#3 cache-induced idle` is not log-only — it needs a GPU-timeline sampler.

Presented to the user in writing (see ledger `P2-A scoping (R127)` entry). No
product code changed pending that authorization.

## P2-A rebuild / restart / re-freeze runbook (prepared; DO NOT run until the
## probe patch passes focused tests)

## GPU coordination discipline (USER DIRECTIVE 2026-09-12; binding)

- The ONLY GPU coordination mechanism is the file lock
  `/mnt/data/gpu/3090.lock` (`root:dev`, mode `660`; shared by `charles` and
  `dev-codex`). Other processes also need the 3090.
- Acquire with `exec 9>/mnt/data/gpu/3090.lock; flock -w 300 9` (the launch
  script does this). The holder is the GPU user for the whole session.
- Hold ONLY for an active experiment; RELEASE promptly when idle (stopping the
  server releases the lock). Do not keep the server up while idle.
- Every subagent dispatch that runs GPU code must be told to acquire this lock;
  no parallel GPU work outside it. Log analysis needs no GPU.
- R129 currently holds the lock via the server (PID 616394); on R129 completion,
  STOP the server to release the lock before doing the analysis.

Verified facts (read-only, 2026-09-12):
- Current server: PID 3082643 = `python -B -m sglang.launch_server` (exec'd from
  `launch-r112.sh`), parent `systemd --user` (PID 1434, detached); scheduler child
  3086752; detokenizer 3086753; holds `/mnt/data/gpu/3090.lock` on fd 9.
- Launch script UNCHANGED: `launch-r112.sh` sha256
  `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3`.
- Current env has `T38C_RUN_ID=r112-20260911T135915Z` and NO
  `SGLANG_P2A_TIMING_PROBE` (probe will default OFF).

Steps once the probe patch is verified:
1. Focused unit/regression PASS reported by the coder (no server needed).
2. Record `scheduler.py`/probe-file content shas BEFORE restart.
3. Stop ONLY PID 3082643 (+ its scheduler/detokenizer children) — targeted kill,
   never `pkill -f`. Confirm fd 9 lock released.
4. Relaunch with the probe ENABLED and a NEW log (never overwrite r112/r124):
   `SGLANG_P2A_TIMING_PROBE=1 nohup bash
    /mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh
    >/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log 2>&1 &`
   The env var is an observability toggle, not a server arg; the argv/profile
   stays byte-identical (same `launch-r112.sh`, same 59-token argv).
5. Capture new PIDs, argv, provenance markers, `/health` 200, L3 stats; write the
   P0-C re-freeze binding the new PIDs/log, the same `launch-r112.sh` sha, the
   probe-file shas, and the enabled env toggle.
6. P2-A live collection with the probe ON. Optional short probe-OFF baseline run
   for the live A/B (the no-op microbenchmark is mandatory regardless).

Re-freeze note: the probe env toggle is NOT a server-arg/profile change; record
it explicitly in the re-freeze so the P2-A attribution is unambiguous.

## Current frontier — E0-E4 extent L3 restoration (2026-09-12, user redirect)

Authoritative short-term plan; supersedes R130 (STOPPED). P2-A is
PASS/CLOSED; P1 CLOSED/VERIFIED; P2-B0 deferred until the extent work lands.

1. `done` **E0** read-only backend identity audit ->
   `work/E0-BACKEND-IDENTITY-AUDIT-20260912.md` `e3a610b0…e341`. R129 = legacy
   `HiCacheFile` full-scandir failure (arg `--hicache-storage-backend file`),
   not a capability gap.
2. `done` **E1** freeze extent + RAM-index L3 architecture; discharge
   the storage Pattern-Intake/Novel-Mechanism gate. Classification:
   deployment/selection -> EXEMPT-eligible (no ExtentFileBackend code change).
   Corpus GAP raised: `storage/pattern` + `storage/testing` absent; the
   in-scope corpus does not cover the extent path. Report
   `work/E1-EXTENT-L3-ARCHITECTURE-FREEZE-20260912.md` `156c7140…ceed`.
3. `done` **E2** minimal deployment/selection fix: new
   `/mnt/data/neuron/sglang-3090-r112-20260911/launch-e-20260912.sh` selecting
   `--hicache-storage-backend extent` with explicit
   `SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=$D/l3-extent`, `FILE_SIZE=256G`,
   `EXTENT_SIZE=64M`, `MAX_SIZE=200G`, `MIN_FREE_SPACE=20G`; log
   `sglang-server-e.log`; GPU via `flock /mnt/data/gpu/3090.lock`. Never edit
   frozen `launch-r112.sh`. Live-verified; report
   `work/E2-EXTENT-DEPLOYMENT-20260912.md` `0613d99a…1c72`.
4. `done` **E3** correctness gates: CPU-only
   `test_extent_file_backend_unit.py`; then live v1-write-then-v2-query hit,
   sidecar component-key isolation, generation invalidation, restart-cold.
   Unit 77/77 OK `90110253…0a6e`; live hit path exercised.
5. `done` **E4** performance gate: R129-equivalent workload (N=8, TURNS=6);
   measure L3 extent/object counts, index entries, query p50/p95/p99, L3->L2
   stage vs R129's 17.777 s -> measured 2.616 ms (cold) / 7.329 ms (warm, 88 %
   hits). Report `work/E4-EXTENT-PERFORMANCE-20260912.md` `05670064…754a`.
6. `done` **E-phase closure** `work/E-PHASE-CLOSURE-20260912.md` answers the 3
   questions. **Open decision: G1 restart-rebuild** (user authority).
7. `after (deferred)` resume P2-B0 (owns `cache-induced idle`).

Terminal for this phase: a written answer to the user's three questions with
E4 measured evidence; no fabricated PASS. G1 (restart rebuild) is an explicit
user decision and is NOT silently added to E2.

## Current frontier — P2-B0 (2026-09-12, user: enter immediately)

E-phase is **PASS/CLOSED**. Production L3 = **ExtentFileBackend +
RAM-authoritative index**; legacy one-file-per-page + FS-as-DB is no longer
production architecture. **Baseline = E4a (extent)**; R129 legacy figures are
permanently scalability-failure evidence, excluded from production perf
comparison.

P2-B0 (scorecard / capacity matrix) must produce:

1. **cache-induced GPU idle** — GPU idle while runnable work exists because
   cache/state is not ready. Needs a GPU busy/idle timeline (sub-5 s) plus a
   runnable-but-not-ready classifier; report duration + fraction of window and
   reconcile with the per-request terms.
2. **RH OFF/ON aggregate TPS** (`aggregate_output_tps` = sum output tokens /
   window). Two profile variants: `--enable-ready-horizon` vs without.
3. **TTFT / TFTT** by scenario (L1-hit / L2-restore / RH-staged-L3 / cold-L3),
   P95, from real streaming first-token timestamps; cold-L3 reported but not
   held to <1 s.
4. **L3->L2 stage distribution with n >> 2** (Q2 = ready_mono - prefetch_issue,
   from probe M2/ready_host).
5. **Queue lead vs ~300 ms stage** (Q1 = admission - enqueue from probe
   M1/admission.v2): does it cover the stage?
6. **C1/C4/C5/C6/C8** concurrency matrix (C2 sanity-only, excluded).

Frozen P2-B0 semantics from R71 that remain binding: C-labels = nominal
concurrency; `total_throughput` is **not computable** (T4 default) until the
user supplies a numerator/denominator/window — surface in writing, do not
substitute another metric; missing fields are `not computable`, never 0; every
row binds full profile + per-row arg/source hash; gains only from matched
completion sets.

Concurrency axis note: the frozen 3090 profile has `--max-running-requests 1`;
the C-sweep requires raising it per cell and recording that in the per-row arg
capture. This is the P2-B concurrency axis, not a P0-C profile drift.

Deferred / out of scope for this dispatch: G1 restart-rebuild (production hard
gate, NOT blocking P2-B0; needs Pattern Intake + Novel Mechanism first).

## Current frontier — R-HBA1 Ready Horizon Behavioral Acceptance (2026-09-12,
## user authority; SUPERSEDES the P2-B0 anomaly experiment order)

The user ruled that RH functional correctness, RH product effectiveness, and
engine throughput must be settled separately. The reordered
`E-C1 -> E-A -> E-B -> E-C3 -> E-D -> E-E` plan is SUPERSEDED. The P2-B0 C4/C8
throughput matrix is on hold until R-HBA1 closes.

Frozen product contract (one line): given a fully durable reusable prefix D
absent from L1/L2 and present in L3, plus a queued continuation with sufficient
lead and resources, RH must stage D L3->L2 before admission, restore D, skip
recomputation of D, and bring the A->B task-switch gap near the L2-hot control.

Profile: same Qwen3.5-4B W4A16/Marlin; extent L3 + RAM index; FP8 KV;
`--max-running-requests 1`; `--hicache-storage-prefetch-policy wait_complete`;
do NOT enlarge the pool; do NOT change CUDA Graph / quantization / kernels.

A = short prompt, fixed streamed output, controllable horizon.
B = ~27K durable prefix D, proven `device_hit=0`/`host_hit=0`/`storage_hit=D`,
KV+Mamba complete, +128 fresh suffix, output 1.

Conditions (repeated): (1) L2-hot; (2) L3-only RH OFF; (3) L3-only RH ON short
lead; (4) L3-only RH ON sufficient lead. Marks on one monotonic clock:
B_enqueue, prefetch_issue, ready_host, A_last_token, B_admission,
restore_success, B_first_token; plus D_req, restored, executed-prefill,
durable recompute, disposition, Mamba restore, hybrid discard.

Hard gate: `ready_host <= B_admission`; restored == D_req; KV+Mamba complete;
**avoidable recompute in D_req == 0**; no PARTIAL/shortfall; no hybrid discard;
HTTP complete. `TFTT = B_first_token - A_last_token`; RH-ON sufficient-lead p95
within `max(100 ms, 25%)` of L2-hot p95 and materially better than RH OFF.

Known blocker to solve before runs: ExtentFileBackend L3 RAM index does not
survive restart (`extent_file_backend.py:20`, E0 G1), so L3-only state must be
constructed inside ONE server session (prime -> evict L1/L2 -> measure).

### R-HBA1 todo (runtime projection; durable truth = ledger.md)

- [x] Record R0 microbenchmark + supersede old order (ledger 2026-09-12 R0/R-HBA1).
- [x] Freeze problem definition: `work/R-HBA1-ACCEPTANCE-CONTRACT-20260912.md`
      sha256 `0cc5d27012fd30bf2e57e051b032f2188aaa70c5d1a363268310dd1d89742877`
      (claim grading FACT/INFERENCE/OPEN/DECISION; profile; tier-accounting
      anchor; 4 conditions; marks; derived metrics; hard + effectiveness gates;
      verdict semantics; out-of-scope). New launcher `launch-rhba1.sh` sha
      `d6d037fa…cd351` (extent + RH toggle + C1, own extent dir).
- [x] `scout` (background) seam reconnaissance: RH trigger/lead, tier
      accounting under staging, admission/first-token marks at C=1, L1/L2
      eviction retaining L3, RH-OFF sync query, bench_multiturn, marks inventory.
- [x] Fill the contract's `OPEN` items -> `FACT` (contract now sha
      `a3232e02…9262`): `/flush_cache?timeout=N` is a clean L3-only constructor
      (L1/L2 cleared, extent L3 + RAM index preserved; 400 was the idle gate);
      admission.v2 IS observed at C=1; tier disposition `{device:0,host:0,
      storage:D}`; `D_req` is empirical; RH-OFF still eager-prefetches (isolates
      predictive staging, not restore); mark clocks are mixed mono/wall.
- [x] **R-HBA1 mechanism preflight = PASS (live).** prime D -> `flush?timeout=60`
      200 -> B restored `storage=27648`, `device=0`, `host=0`,
      `kv_fetched==kv_expected==27648`, mamba 1/1, `ready_host <= admission`
      (ready ~4.84 ms early), `Prefill batch #new-token:152 #cached-token:27648`
      => D NOT recomputed. Evidence: ledger 2026-09-12 preflight;
      `/mnt/data/nerun-dev/rhba1/preflight-on.json`.
- [x] Build R-HBA1 harness (`work/R-HBA1-bundle/rhba1_harness.py` two-session
      driver + live SSE `sink`; `rhba1_analyze.py` gate analyzer; runner
      `/mnt/data/nerun-dev/rhba1/run_rhba1.sh` fresh-extent + RAM>=18GiB guard).
      Harness bug fixed: `complete()` now streams live so B is enqueued during A.
      Mark regex fixed for `restore_state_before` field order + `reparse()`.
- [x] Run conditions 1-4, n=20 each, on the 3090 under `/mnt/data/gpu/3090.lock`
      (fresh server + fresh extent dir per condition; GPU released after).
      Evidence: `/mnt/data/nerun-dev/rhba1/result-<cond>.json`, `rhba1-report.json`.
- [x] Analyze against hard gates + TFTT effectiveness gate. **§9 hard gates
      PASS 20/20** (ordered_rh, hidden, restored==D_req, avoidable_recompute==0,
      mamba complete, no discard); `within_hot_band=true`; **§10
      `better_than_off=false`** (RH-OFF p95 103.4 ms vs RH-ON 108.8 ms).
- [x] **R-HBA1 verdict artifact**
      `work/R-HBA1-VERDICT-20260912.md` sha `e7aad638…c5de9`: §9/§1(a-d) PASS
      20/20; §10 not evaluable at C1 because the RH-OFF control is degenerate
      (`scheduler.py:6068-6072` eager-prefetches D at enqueue with RH off);
      strict overall NOT_VERIFIED (not FAIL, not fabricated PASS).
- [x] **DECIDED by user (Option A, 2026-09-12):** R-HBA1 Behavioral Correctness
      = PASS / CLOSED (20/20). §10 RH-vs-OFF = NOT EVALUABLE at C1 (RH-OFF has
      upstream eager prefetch). Incremental RH effectiveness moved to RH
      Pressure Acceptance. Option B rejected; no C1 re-run.

## Current frontier — RH Pressure Acceptance (2026-09-12, user-authorized)

Origin: R-HBA1 closed as behavioral PASS; the RH-vs-eager-prefetch incremental
value must be measured under contention. Compare RH-ON horizon-aware staging vs
RH-OFF enqueue-time eager prefetch across C4/C5/C6/C8, judging: earlier
`ready_host`, less `avoidable_recompute`, lower TFTT, lower `cache_induced_gpu_idle`,
higher `request_tps`/completion.

### RH Pressure Acceptance todo (runtime projection; durable truth = ledger.md)

- [x] Freeze framing: `work/RH-PRESSURE-ACCEPTANCE-CONTRACT-20260912.md`
      sha256 `b9bb2e17892d8659624ed377e53b97a2894b180727f195364b1d389f69eb8919`
      (comparative effectiveness under C4/C5/C6/C8; direction-consistency
      verdict; naming + seam-gap rules; correctness side-condition).
- [x] Re-sample executed: run1 (C4/C5/C8 x ON/OFF) + run2 (order-reversed) +
      run3 (position-balanced `on,off,off,on`, RAM-gated). Launcher delta
      `launch-p2b0m.sh` adds `--enable-metrics` ONLY (required for the authorized
      `/metrics` idle seam; frozen profile otherwise identical). Raw
      `/mnt/data/nerun-dev/p2b0/{run1,run2,run3}/`.
- [x] `cache_induced_gpu_idle_engine` now computes (was 404 without
      `--enable-metrics`). Two graded methodology corrections recorded:
      (a) driver grows context (not the contract's fixed-H sweep);
      (b) non-stationary environment (ambient RAM/position) dominates single
      cells, reversing signs between runs.
- [x] **RH PRESSURE VERDICT frozen**
      (`work/RH-PRESSURE-VERDICT-20260912.md` sha `9b37bd1e…4da6`):
      C8 idle COMPLETE separation (ON max 0.425 < OFF min 0.426, 3/3 runs) but
      throughput NOT reproduced; C4/C5 NO SEPARATION. Overall: RH incremental
      effectiveness at this profile = **NOT DEMONSTRATED** (partial: robust idle
      reduction at C8 only). Not converted into a PASS.
- [x] **DECIDED by user (2026-09-12):** RH effectiveness line CLOSED as NOT
      DEMONSTRATED (retain C8 idle partial benefit); option D rejected; FP8 KV
      stays a separate line; **next mainline = G1 restart-rebuild DESIGN GATES**,
      then G1 implementation+verify, then P3 soak/restart/fallback.

## Current frontier — G1 restart-rebuild DESIGN GATES (2026-09-12, user authority)

`FACT`: `ExtentFileBackend` has no metadata persistence (`extent_file_backend.py:20`,
test `test_crash_reopen_all_cold`); after restart the data bytes survive but the
RAM-authoritative index is gone, so L3 is unreachable. This blocks production
durability sign-off and would poison P3 restart/fallback/soak.

Frozen design boundary (user): compact persistent `manifest/checkpoint` +
append-only metadata `WAL` -> rebuild RAM index at restart; NEVER scan extent
data files. Contract minimum: `key -> extent_id/offset/length/generation/
component`; versioned + integrity-checked checkpoint; WAL append recoverable
only after durable-write ACK; `load checkpoint -> replay WAL -> rebuild index`;
torn/malformed/impossible-generation -> fail closed; recoverable GC/invalidation;
KV+Mamba sidecar identity/all-or-nothing preserved across restart.

Corpus: `/home/dev-codex/workspaces/nerun-dev/storage/{pattern,testing,review/gates}`
HEAD `1953397436683219e543e19dff89560d07fa3c6f`. G1 is NON-EXEMPT -> full Pattern
Intake + Novel Mechanism gate required before any code.

### G1 todo (runtime projection; durable truth = ledger.md)

- [x] Corpus recon (scout) -> `work/G1-CORPUS-RECON-20260912.md` sha
      `d069e893…c5c1`; corpus HEAD `1953397436683219e543e19dff89560d07fa3c6f`.
- [x] Target recon (scout) -> `work/G1-TARGET-RECON-20260912.md` sha
      `03ef4584…b566`: no header/magic/checksum/fsync; RAM-only index; ExtentRef
      `{extent_id,offset,length,generation}`; hook points; cold-restart confirmed
      empirically (`test_crash_reopen_all_cold` -> OK).
- [x] **CRITICAL discovery:** an existing E2E restart oracle already encodes the
      G1 behavior — `TestHiCacheSpecExtentStorage` via shared mixin
      `hicache_spec_storage_common.py:228-272` asserts post-restart
      `storage_cached_tokens >= input_token_len-2*page_size`; `file` is warm
      (dir scan `hicache_storage.py:459,591,721`), `extent` is cold -> the extent
      variant is expected RED. G1 must make it green; it is the acceptance oracle.
- [x] Architect authored the package; classification NOVEL_MECHANISM; status proposed.
- [x] Independent adversarial review #1 -> **BLOCKED** (3 real correctness holes
      D-01/02/03 + 5 majors + 3 minors + 2 anchor errors). Review persisted
      `work/G1-bundle/G1-GATE-INDEPENDENT-REVIEW-01.md` sha `a155fc99…`.
- [x] Repair pass issued (all ids dispositioned) ->
      `work/G1-bundle/G1-GATE-REPAIR-RESPONSE-01.md`; contract sha
      `31f742fd…9a69`, novel `15403306…abf9`, intake `24f7078c…9e30`.
      Key fixes: write-ahead durable invalidation before slot reuse (D-01);
      torn-tail truncate+fsync before append (D-02); durable
      `(namespace_epoch, group_seq)` group id, new decision D7 (D-03);
      D-04..D-11; anchors re-pinned to HEAD (A-01/A-02).
- [x] Pre-implementation baseline frozen: 77/77 extent unit tests pass (CPU).
- [x] R1 re-review closed D-01/D-03; R2 closed NEW-1..NEW-10/§0.2/W5; R3 closed
      NEW-11 (deleted the gate-release optimization; added the pending-rotation
      promotion rule) + NEW-12.
- [x] **Final R3 re-review = ACCEPT-WITH-CONDITIONS; reviewer: mechanism SAFE TO
      FREEZE; blockers now authority-only.** Persisted
      `work/G1-bundle/G1-GATE-INDEPENDENT-REREVIEW-R3-01.md`.
- [in_progress] Apply the 4 minor doc alignments N-1..N-4 (N-3/N-4 orchestrator in
      `authority.yaml`; N-1/N-2 architect R4 in the bundle), repin, freeze.
- [ ] **BLOCKED ON AUTHORITY: D1, D3, D7** (plus novel acceptance) — decision set
  staged in `work/G1-DECISION-BRIEF-20260912.md`; manifest `authority.yaml`.
  **NO CODE until D1/D3/D7 are decided.**

## Current v0.5.19 release-integration frontier (user decision 2026-09-13)

- Formal release tags only; do not follow `upstream/main`; target at most one formal release behind.
- Fixed upgrade sequence: dry merge -> overlap matrix -> semantic adjudication -> merge -> frozen
  regressions.
- Current U3 remains blocked on reconciliation contract freeze, not abandoned. The active contract
  artifact must be independently accepted before minimum reconciliation-interface implementation.
- No merge commit or U4 until contract ACCEPT, implementation, adversarial lifecycle tests, independent
  review, and required runtime evidence are complete.
- After v0.5.19 closure, schedule a separate seam-reduction refactor so local RH/Extent/linker/
  reconciliation behavior is connected through narrow adapters rather than long-lived scheduler or
  UnifiedRadixCache forks.

## Session handoff frontier (2026-09-13)

The historical planning blocks above are retained; this appendix is the current frontier for the next
session and supersedes older U3 “contract freeze pending” wording.

- **U3 current state:** latest F2/F4/F6/F7 repair staged; source/model tester checks PASS as
  `MODEL_EVIDENCE_ONLY`; independent reviewer pending; dependency-backed/runtime evidence BLOCKED;
  merge and U4 unauthorized.
- **Active owner:** reviewer `U3-F2-F4-F6-F7-REVIEW-20260913` / `ses_f65a0c851ffeIEL2MFtX0yERZq`.
- **Next gate:** read `/mnt/data/nerun-dev/p3/U3-f2-f4-f6-f7-review-20260913/REVIEW.md`, reconcile it
  against the actual staged diff, then either repair concrete findings or preserve separate source/model
  PASS and dependency/runtime BLOCKED dispositions.
- **Do not:** infer U3 acceptance from model tests, merge while runtime/authority requirements are
  unresolved, or alter unrelated staged RH/HOST_ALLOC/trace paths.
- **After genuine U3 closure:** create the single v0.5.19 merge commit, then execute U4's frozen
  regression corpus. P3/soak remain downstream.

## Final handoff frontier (2026-09-13)

- Latest source review is **REJECT**: `/mnt/data/nerun-dev/p3/U3-f2-f4-f6-f7-review-20260913/REVIEW.md`.
- Current repair frontier is F2/F4/F6/F7 plus: legacy HiRadix host-release acknowledgement/identity,
  current-epoch group reconciliation, and `staged_prefetch_tokens()`/scheduler ready-horizon return-shape
  compatibility.
- Latest tester is model/source PASS only (`20/20` and `8/8`, `MODEL_EVIDENCE_ONLY`); dependency-backed
  and product-runtime evidence are BLOCKED. Do not merge on this evidence.
- All current specialists are complete. Next session owns one bounded repair, followed by fresh
  independent review/adversarial testing. External ambiguous effects remain `FAILED_UNKNOWN`/blocking.

## Repair6 verification frontier (2026-09-13)

- Repair4 and repair5 review gates remain historical **REJECT** dispositions: repair4 retained RH/runtime
  errors despite 20/20 model checks; repair5 retained F2 atomicity plus cleanup/rollback/raw-fallback
  blockers despite source 20/20.
- Repair6 is not yet a gate result. The coder receipt
  `/mnt/data/nerun-dev/p3/U3-repair6-20260913/receipt.md` is source/model only; six target paths are
  `MM`, `MERGE_HEAD` is present, and unmerged paths are zero. Fresh independent review and tester
  evidence are still pending/blocked.
- **U3 remains NOT ACCEPTED.** Do not merge or start U4; do not treat the broad staged merge as
  accepted. External authority blockers remain `FAILED_UNKNOWN`/blocking.
