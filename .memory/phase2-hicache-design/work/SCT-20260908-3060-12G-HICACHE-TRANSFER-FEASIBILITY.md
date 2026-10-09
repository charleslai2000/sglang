ENTRY: ACCEPT

# SCT-20260908-3060-12G-HICACHE-TRANSFER-FEASIBILITY

- Task ID: `SCT-20260908-3060-12G-HICACHE-TRANSFER-FEASIBILITY`
- Epoch: `phase2-hicache-design/2026-09-08`
- Role: `scout`
- Invocation status: `done`
- Scope: read-only repository exploration plus creation of this report only.

## 1. Target repository

`/home/dev-codex/workspaces/3rdparty/sglang-3060-12g-hicache` does not exist.

The nearest same-level candidate found was:

`/home/dev-codex/workspaces/3rdparty/sglang-2060-6g-hicache`

No directory named `3060`, `12g`, or another 3060/12G HiCache repository was found under
`/home/dev-codex/workspaces/3rdparty` at the searched depth. The 2060 candidate is an SM75/
6G-oriented branch, not evidence of a 3060/12G runtime baseline.

## 2. Branch, commit, and dirty state

Observed with `git status --short --branch` and `git log -1`:

| Repository | Branch/status | HEAD |
|---|---|---|
| requested 3060/12G | missing; no git state | n/a |
| nearest 2060/6G | `sglang-sm75...origin/sglang-sm75`, clean in the displayed status | `fb2c68a48e0e95e29e9fb8f965b43ebdb6814de2` (`feat: block-128 INT8 tied embedding/lm_head for sm75 (Qwen3.5-4B)`) |
| 3090/24G reference HiCache | `3090-24g-hicache...origin/3090-24g-hicache [ahead 2]`, dirty | `0a725c6385805f21138111e09bf69464ec29f1dc` |
| 3090/24G reference Opt | `3090-24g-opt...origin/3090-24g-opt`, dirty | `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` |

The 3090 HiCache tree has untracked `3090-dev` experimental assets and `.memory/`. The 3090
Opt tree has modified HiCache source files and untracked P0/P3 vehicles, trace context, and
review artifacts. Therefore a path copy from either dirty tree is not a reproducible commit
transfer by itself.

Repository guidance read: the only repository-local `AGENTS.md` found in the inspected trees is
the documentation-specific `docs/AGENTS.md`; it is not runtime guidance. The workspace-level
`AGENTS.md` supplied with this dispatch requires scout-only discovery and no product edits.

## 3. Reference implementation and differences

### 3.1 Launcher and experiment assets

`3090-24g-hicache/3090-dev/README.md` identifies the reference assumptions:

- RTX 3090 24G;
- `Qwen3.5-9B-w4a16`, GPTQ 4-bit, 32 layers with 24 Mamba layers;
- GPU L1 / Host L2 / L3 NVMe extent HiCache;
- baseline pool64, CUDA Graph enabled, `cuda-graph-max-bs=8`, max running/concurrency 8,
  Ready Horizon off, extent L3 160G, minimum free 10G;
- observed startup allocation: model 10.36GB, Mamba 5.02GB, host Mamba 8.24GB, KV cache
  65,536 tokens (also recorded in the phase2 ledger and production handover).

The reusable driver `3090-dev/cap_ratio_driver.py` encodes a cold prime followed by warm turns:
8 agents, 20 turns by default, full-history resend for warm turns, and the 9B GPTQ model path
`/root/models/Qwen3.5-9B-w4a16`. The reference `3090-dev/gate2-*` assets exercise L3 restore.
The P0 vehicle in `sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py` is explicitly a
vehicle, not a gate decision; its frozen constants are 25 sessions, history target 55,000
tokens, 8 active/build workers, RH off, Mamba ratio 0.42, HiCache ratio 1.3, FP8 KV,
CUDA-graph max batch 8, 120G file, and 256-token restore threshold.

The P0 contract in
`.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md` requires,
per session, one exact build identity, KV and Mamba durability before the durability barrier,
then `durability_barrier < residency_barrier < warm`, exact identity joins, no V2 evidence,
and all 25 sessions accepted. This is a semantic/evidence contract, not a statement that the
same workload fits 12G.

### 3.2 Runtime/source differences

The 3090 HiCache reference contains the extent backend at
`python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`; the 2060/6G candidate
does not contain that file. The 2060 candidate also has no
`python/sglang/srt/managers/scheduler_components/ready_horizon.py`. It does contain
`unified_radix_cache.py` and `unified_cache/components/mamba_component.py`, but their SHA-256
prefixes differ from both 3090 trees. The 3090 HiCache and 3090 Opt copies of the same three
HiCache source paths also have different hashes, confirming that the dirty reference trees are
not interchangeable snapshots.

Relevant 3090 symbols/assets found:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`: unified cache, restore/admission and
  lifecycle integration;
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`: Mamba sidecar
  transfer and restore path;
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: extent L3 storage;
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` and
  `3090-dev/test_ready_horizon_{unit,partition}.py`: READY_HOST/residency policy and tests;
- `3090-dev/test_capacity_model_unit.py`: KV/Mamba per-pool and READY resident capacity model;
- `3090-dev/test_hicache_restore.py` and
  `test_hicache_restore_scheduler_feed.py`: restore/scheduler feed tests;
- `3090-dev/p0_session_barrier_vehicle.py`, `test_p0_residency_barrier_emitter.py`, and
  `test_p0_trace_context_v4.py`: P0 evidence vehicle and focused fixtures, with the product
  trace changes in `python/sglang/srt/mem_cache/trace_context.py` in the Opt tree.

The requested 3060 branch cannot currently be checked for these symbols, launcher flags, model
support, CUDA capability, or storage backend registration. The 2060 branch's SM75/Qwen3.5-4B
commit is not a substitute for that check.

### 3.3 Likely impact surfaces

If a real 3060/12G checkout is supplied, the first comparison should cover:

1. branch/base commit and CUDA/SM support;
2. `unified_radix_cache.py`, `mamba_component.py`, storage backend/factory, and scheduler
   Ready Horizon modules;
3. server argument plumbing for hierarchical cache, Mamba host ratio, memory fraction, KV
   dtype, max running requests, page size, and CUDA graph limits;
4. launcher model path, served model name, L3 directory/size/min-free, trace marker, and
   cleanup behavior;
5. P0 event emitter/trace-context availability before attempting live evidence collection.

## 4. Transferability verdict and blockers

### Verdict

The experiment *method and evidence reducer* are conditionally portable, but the current P0/
P0.1 readiness -> residency -> warm/restore experiment is **not directly migratable** to
`sglang-3060-12g-hicache` because the target repository is absent and the nearest candidate
lacks the 3090 extent/Ready-Horizon runtime surfaces.

### Blocking items

- **B1 — target absent:** no branch, commit, launcher, model config, or dirty-state baseline
  exists to validate.
- **B2 — runtime parity unproven:** 2060/6G lacks the 3090 extent backend and Ready Horizon
  module; its divergent Mamba/unified-cache files cannot establish semantic parity.
- **B3 — 12G capacity mismatch:** the reference 9B allocation already reports 10.36GB model
  plus 5.02GB Mamba before accounting for 12G-specific runtime headroom. Reusing the 9B/
  55K-token/25-session constants is not credible without a smaller model or materially reduced
  cache footprint.
- **B4 — P0 product emitter dependency:** the P0 vehicle needs product-owned V3 durability,
  residency-barrier, session-generation, and exact identity events. A client-side warm label or
  timeout cannot replace them. Their presence in 3060 is unknown.
- **B5 — reference dirtiness:** source and vehicle assets are split across dirty 3090 Opt and
  HiCache trees, so copying “current” files without a pinned manifest risks mixing revisions.
- **B6 — no hardware validation authorized:** SM75/SM86 behavior, CUDA graph availability,
  Mamba checkpoint size, and actual 12G usable VRAM remain unverified because no GPU/remote run
  was performed.

## 5. Conditional 3060/12G sizing proposal for a future audit

These are conservative starting hypotheses for a future local/authorized audit, not observed
3060 measurements:

- **Model:** prefer a Qwen3.5-4B-class model with an existing SM75/SM86-compatible INT8/4-bit
  path (the nearest 2060 commit explicitly mentions Qwen3.5-4B INT8 tied embedding/lm_head).
  Do not assume the 9B GPTQ artifact fits 12G with Mamba and scheduler overhead.
- **GPU/cache budget:** start with `max-running-requests=2`, two active sessions, and a small
  GPU KV budget around 8K logical tokens; reserve headroom for model/runtime rather than trying
  to scale 65,536-token 3090 KV capacity linearly. Keep Mamba host residency small and bounded;
  derive its actual token budget from startup allocation, not from the 3090 ratio.
- **Sessions:** first correctness pass: 1 cold + 1 warm session; then 2 sessions. If both are
  stable, a small pressure pass of 4 sessions is the upper initial bound. Do not begin at P0
  S=25 or the 3090 8-active configuration.
- **History/restore shape:** use one or two completed nodes, initially about 4K-8K history
  tokens, with a short suffix. Increase only after build, durability, residency, warm ordering,
  and full restore are all observed.
- **Trace limit:** cap to 2-4 sessions, one run, one trace file, and the minimal event set:
  build_complete, KV/Mamba durable, durability_barrier, residency_barrier, warm_lookup/warm
  request, restore outcome/complete, and cleanup. Retain event IDs, local arrival order,
  generation, exact identity, and response/build rows; do not collect long soak traces.
- **Minimal 1-2 node timing audit:** for each of 1 and 2 completed nodes, record monotonic
  deltas for (a) build end -> KV durable, (b) build end -> Mamba durable, (c) durability ->
  residency barrier, (d) residency barrier -> warm lookup, (e) restore start -> full restore,
  and (f) warm response. Require the causal order from the P0 contract before interpreting
  latency. Run one single-process/single-node audit first; a second node is useful only if the
  target topology actually supports it and remains within the explicit experiment scope.

This sizing is intended to answer feasibility and ordering, not to compare 3060 performance to
3090. It must be revised after a real target startup reports model, Mamba, KV, host, and L3
allocations.

## 6. Files to copy versus evidence to exclude

### Candidate local assets to copy after pinning a compatible target revision

- The minimal P0 vehicle/reducer and focused fixtures:
  `3090-dev/p0_session_barrier_vehicle.py`,
  `3090-dev/test_p0_residency_barrier_emitter.py`,
  `3090-dev/test_p0_trace_context_v4.py`.
- The small restore/readiness test set:
  `test_hicache_restore.py`, `test_hicache_restore_scheduler_feed.py`,
  `test_ready_horizon_unit.py`, `test_ready_horizon_partition.py`, and
  `test_capacity_model_unit.py`.
- The driver/launcher only as a template after replacing model path, served name, storage path,
  concurrency, cache limits, and trace caps. A target-specific launcher must be pinned to the
  target commit and hardware; do not copy remote host assumptions.
- Product source changes only through a reviewed, pinned change manifest after confirming the
  target already has the corresponding interfaces. In particular, do not copy only
  `trace_context.py` without its scheduler/cache lifecycle call sites.

### Do not copy

- `.memory/phase2-hicache-design/work/*` as runtime evidence or as a substitute for fresh
  target evidence;
- `evidence/`, old gate2 output, production logs, remote host paths, ports, environment names,
  and L3 data directories;
- 3090-specific 25-session/55K-token/8-active constants or the 160G L3/min-free settings;
- historical pass/fail claims as if they proved 3060 behavior;
- dirty-tree artifacts without their source revision and dependency manifest;
- P2-IO exploratory probes when the question is P0/P0.1 readiness/residency/warm/restore;
  they are not a substitute for the P0 event contract.

## 7. Scope declaration

No files were modified except this requested report. No remote host, GPU, server, launcher,
model download, or experiment was started. The search was limited to the specified 3rdparty
workspace candidates, the two 3090 reference repositories, their repository-local docs,
the phase2 HiCache memory files relevant to P0/P0.1, and targeted HiCache/Mamba/Ready Horizon/
launcher symbols. Unknowns remain for the absent 3060 target: exact commit, CUDA/SM support,
real VRAM allocation, model availability, backend registration, and product trace-emitter
parity.

## Summary / followups / open issues

- **Summary:** conditional method portability; no direct 3060/12G migration acceptance.
- **Followups:** obtain or create a pinned 3060/12G checkout; compare the listed source and
  argument surfaces; establish a small-model startup baseline; then run only the proposed
  1-2 node timing audit under a fresh Task ID and explicit hardware authorization.
- **Open issues:** B1-B6 above, especially target absence, runtime parity, and 12G memory fit.
- **Status:** done.
- Extra work requires a fresh Task ID.
