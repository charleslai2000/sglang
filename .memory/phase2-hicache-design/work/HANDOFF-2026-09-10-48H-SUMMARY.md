# 48-hour handoff summary — 2026-09-10

## Goal

On the RTX 3060 12G target, optimize the complete HiCache hierarchy end to end:
L1 GPU, L2 host RAM, and L3 persistent storage. The desired steady state is that
L3→L2 staging for the next task overlaps current GPU computation, so task
switch/admission does not synchronously wait for L3. Outcome metrics are GPU
utilization approaching 100%, `TTFT <1s` as an optimization target (not an
absolute gate), total throughput, aggregate TPS, and c4/c5/... scenario gains.
The earlier `TFTT` reference was the user's typo and is not a required metric.

Additionally, the capacity baseline must always record the complete server
arguments. The apparent `FP8 KV≈65,536` versus allocator `≈193,294` token
 difference must not be treated as a contradiction until mem-fraction, mamba
ratio, max-total-tokens, and related profile parameters are compared.

## Workspace and scope

- Product workspace: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Product branch: `3060-12g-qwen35-4b`
- Task memory: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- `3090-24g-hicache` is the coordination/report workspace, not the 3060 product checkout.
- No push, history rewrite, cleanup, reset, rebase, commit, or new live trace is authorized by the current state unless separately authorized.

## Confirmed accomplishments

1. **3060 runtime/bootstrap:** RTX 3060 12GB, SM86, CUDA 12.4, AWQ W4A16/Marlin,
   FP8 E4M3 KV, CUDA Graph, HiCache file backend, and RH startup path were verified.
   Health returned 200. SM86 AOT/import and loader packaging were repaired and verified.
2. **Correctness:** BF16 single-request smoke passed (HTTP 200, valid output).
   AWQ is the production candidate; BF16 is only a correctness smoke configuration.
3. **Decode baseline:** short-request aggregate output TPS was measured as c1=87.64,
   c2=24.24, c4=48.83, c6=73.06, c8=98.09; all tested points had zero HTTP failure,
   OOM, zero-progress, and admission failure.
4. **Capacity:** 64K/128K/192K single-session prompts completed in 36.79/105.49/205.27s;
   256K was rejected at an allocator ceiling near 193,294 tokens, not by OOM.
5. **Three-tier restore:** single-session repeat measured L1 device 54,976 tokens/0.230s,
   L2 device+host 10,240+44,736/0.391s, and post-restart L3 storage-hit 54,976/38.301s.
   KV+Mamba durable ACK and no full-history recompute were observed. The 38.301s value
   is end-to-end restore, not isolated L3→L2 latency.
6. **HOST_ALLOC:** classification/capacity behavior passed, including positive KV+Mamba
   seeded restores and no crop/lower-checkpoint/Mamba-fetch/hybrid-discard signatures.
   Feasible-generation wake after a real allocability epoch change remains unproven.
7. **RH telemetry:** a swallowed ambiguous-bool error from a multi-element Tensor in
   `prefix_indices` was fixed. Dependency-free regression was 19/19; a live probe
   verified normal `rh_match_prepare.v1` before `rh_stage.v2` with no failure marker.
8. **RH SPEC_BUDGET:** post-issue cursor capture and a monotonic
   `speculative_release_epoch` were implemented. Exactly-once speculative release
   increments the event counter; duplicate/missing release and DEMAND release do not.
   Strict `current < cursor` semantics remain. The unsampled 0→N→0 ABA cycle is covered,
   and successful issue consumes the stale negative entry. Static final review is APPROVE.
9. **3090/P2-IO:** ExtentFileBackend v1/v2 closed-loop and 2048-page boundary tests,
   durability/identity/residency/finalization safeguards, and multiple fail-closed fixes
   were completed or statically verified. These are not a 3060 production acceptance.

## Evidence status and non-claims

- Dependency-complete focused RH runtime tests are **PENDING**. The local interpreter
  lacks pytest/orjson/msgspec/torch. A remote environment `/root/sglang-env-3060-4b`
  exists in prior evidence; an earlier focused remote run passed the two new
  SPEC_BUDGET tests but had six pre-existing fixture/API failures in the broader file.
- Clean post-fix 3060 blocker+A/B OFF/ON acceptance is **NOT VERIFIED**. The previous
  driver/join bundle and stable RID→intended-A/B mapping are unavailable; later
  x/y/z/w/q runs cannot be relabeled as the old A/B. Therefore B-specific cursor,
  release wake, host-ready-before-admission, no cached=0, and no recompute claims remain
  unestablished.
- RH code/telemetry gates are PASS, but RH performance/causal acceptance is not.
- True streaming TTFT, total throughput, RH-ON aggregate TPS, c5, paired c4/c5/...
  uplift, workload GPU-utilization time series, L3→L2 lead/stage duration, L2→L1
  duration, and production-safe multi-session capacity are unavailable. TTFT <1s
  and GPU utilization approaching 100% are optimization targets, not absolute gates.
- Capacity reports must bind every token-capacity claim to the complete server-argument
  profile. The 65,536-token FP8 KV startup figure and the 193,294-token allocator
  ceiling currently come from different measured contexts or profiles; reconcile
  mem-fraction/mamba-ratio/max-total-tokens and related args before drawing a capacity
  conclusion.
- No claim is made that HiCache is production-ready or that task switching is already
  free of synchronous L3 dependency.

## Open decisions for expert

1. Define the measurement workload/window and reporting method for the optimization
   targets `TTFT <1s` and GPU utilization approaching 100%; neither is an absolute gate.
2. Define total-throughput versus aggregate TPS and whether c5 is mandatory.
3. Decide whether queue-only RH has enough lead time or needs advance-resume/preannouncement.
4. Decide whether L2 residency and feasible HOST_ALLOC wake are production hard gates.
5. Audit `decode_hicache_mixin.py` → `query_storage_hit_length` for synchronous L3 metadata
   work on the task-switch/preallocation path. Do not redesign it until profiling proves
   it is the critical blocker; if confirmed, design an async L3 probe/ticket separately.
6. Set production-safe concurrent context capacity and evaluate FP8 scaling-factor quality.

## Recommended frontier

A. Run the focused RH/release/ABA tests in the dependency-complete environment and record
   exact environment/source hashes and stdout.
B. After A passes, run one fresh, hash-pinned, durable KV+Mamba 3060 blocker+A/B OFF/ON
   trace with a stable driver/join bundle and matched completion set.
C. Build one benchmark schema emitting streaming TTFT, e2e, throughput/TPS, c4/c5,
   GPU utilization, stage/lead/queue times, cache hits, restore/recompute, capacity,
   complete server args, and failure counters.
D. Use measured timing/profiling to decide any decode-side synchronous L3 redesign.
E. Only then run multi-session capacity, soak, restart/fallback, and production gates.

## Source evidence

Key reports are in this task's `work/` directory, including:
`SCOUT-HICACHE-OPT-GOAL-20260910.md`, `CODER-RH-RELEASE-EPOCH-FIX-20260910.md`,
`CODER-RH-STALE-NEGATIVE-20260910.md`, `REVIEW-RH-FINAL-TEST-GATE-20260910.md`,
`TEST-RH-RELEASE-EPOCH-20260910.md`, `TEST3060-HICACHE-RESTORE-R3-20260910.md`,
`OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md`, and the RH live reconciliation reports.
