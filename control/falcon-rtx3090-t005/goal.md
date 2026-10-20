# T005 — Falcon RTX3090 online critical-path performance optimization (closed 2026-10-20 per Owner ruling)

## Goal
Using only the current `3090-24g-hicache` branch and existing `control/` evidence, identify one repeatable Falcon online Restore→Prefill or other major critical-path bottleneck, implement one bounded optimization, establish frozen numerical correctness, run at least three matched before/after A/B pairs across fixed-shape and representative online/cache-pressure workloads, make an evidence-based ACCEPT or REJECT decision, and selectively commit/push only accepted implementation plus its tests and reproducible evidence.

## Authority and constraints
- Sole checkout: `/home/ubuntu/workspaces/3rdparty/sglang-hicache`, branch `3090-24g-hicache`; use no worktree or other branch.
- Preserve all pre-existing tracked modifications and untracked artifacts. No reset/clean, blanket staging, overwriting, or unrelated commits. The working tree was observed with 52 tracked modified/deleted paths and 5,241 untracked entries; rerun exact inventory before integration.
- Start from current branch control history, not assumed runtime-source completeness of T004 evidence commit `078915a17c2d2cf7dbef53c796c4c5fa1a9332ac`.
- GPU use is authorized by repository instructions. Before each GPU workload acquire `/tmp/f1-r16b-gpu-exclusive.lock` exclusively; enforce a hard runtime deadline and monitor. Current initial GPU snapshot: RTX3090 idle (1 MiB, 0%, 34C); do not assume that remains true.
- Reuse existing Nsight 2026.5.1/FPM, T004 L0FIX7 ledger, T002 seven-shape CUPTI and existing L1/L2/L3 evidence/regressions. Do not repeat already accepted ACK, lock, cache recovery or three ON/OFF mechanism certifications.
- Keep Scheduler Wall, FPM wall, CUDA runtime API, H2D event, Kernel Busy Union, whole-GPU counters, physical I/O and service performance semantically distinct. Wall minus kernel union is not GPU idle.
- No numerical tolerance widening to accommodate the historical 4K logits anomaly. No performance acceptance before correctness passes. No cross-run data splicing.

## Scope
1. Reconcile existing same-run evidence and source identity; identify reproducible bottleneck components using existing events and the minimum controlled repeats needed.
2. Freeze Falcon model/tokenizer/checkpoint identity, full token IDs, greedy and sampling policy, batch/prefix/cache conditions, Cache-OFF reference and justified logits/state tolerances.
3. Choose one measured bottleneck and document source path, expected time saving, state/numerical/resource risk and rollback boundary before code change.
4. Implement one optimization and verify cache/model correctness, long greedy generation, ordinary Radix prefix reuse, FULL KV+MAMBA Host restore and Storage restore as applicable.
5. Run fixed-shape execution comparison plus normal online c8/c16, high pending + real L3 restore, and requests with Prefill plus at least 128 Decode tokens; at least three matched before/after pairs with identical workload/config/cache frontier/capacity. Report per-stage distributions, queue and H2D waits, bytes/bandwidth, actual batch distribution, TTFT/TPOT/TPS/throughput, GPU metrics/stall evidence where supported, memory and variance. Reuse valid existing measurements; do not repeat full profiler certifications unnecessarily.
6. Decide ACCEPT or REJECT against frozen criteria, preserve negative results and candidate rollback evidence, selectively integrate only accepted owned files, and verify commit/push SHA.

## Exclusions
- Do not extend T004 completion criteria or reopen its queue-prefetch mechanism certification.
- Do not redesign/redevelop three-tier HiCache.
- Do not start T006 or expand into unrelated performance work.
- Do not claim causal GPU-idle/stall or physical-media bandwidth absent direct evidence.

## Owner-directed terminal disposition (2026-10-20)
The Owner superseded the original optimization/A-B completion scope and ordered this phase to end after: (1) minimal Storage Worker timestamp fix with semantic and targeted regression validation; (2) actual RTX3090 B0 c8/c32 hardware-efficiency capture and bounded stop/continue ruling; (3) selective repair commit/push and separate GPU evidence/control commit(s). No further Ratio/Lazy/Decode Skip, capacity expansion, or new optimization direction. The measured T005 result is an explicit REJECT/stop recommendation: c8/c32 hardware results and existing mature paths do not justify a safe optimization that closes the gap; 985.1 output TPS was not reached. Do not start follow-on optimization automatically. Cache-OFF numerical oracle and original generic matched A/B gates remain incomplete and are not reclassified as pass.