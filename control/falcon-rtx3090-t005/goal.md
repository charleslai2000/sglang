# T005 — Falcon RTX3090 online critical-path performance optimization (performance research closed 2026-10-20)

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
The Owner closed T005 as **MEASURED / NO_OPTIMIZATION_ACCEPTED** and ended performance experimentation. Frozen results and limitations are in `runs/20261020T122034Z-ordinary-c8-probe/final-gpu-efficiency-20261020T193249Z/final-results.md`. Do not start Ratio/Lazy/Decode Skip, capacity expansion, or another optimization phase. 985.1 output tok/s was not attained; Cache-OFF numerical oracle and generic matched A/B correctness gates remain incomplete, not passed.

The separate Storage Worker defect was traced to the `int(None)` consumer inside uncommitted T004 telemetry code. A None-preserving correction and targeted regression passed, but HEAD lacks this consumer; it cannot be independently committed without being inert, and the containing T004 telemetry hunk must not be silently imported. The correction remains only in the dirty worktree. T004 must include the None guard and regression test when it next integrates that worker instrumentation. T005 does not own or resolve this T004 integration. Keep its pending risk visible in T004 control state. T005 evidence commits are pushed at `9da9238a3111aec525e4341acc19081cb24a85d1`, `49f8fa9c4d0d3c6735746ca3931d4973945c9678`, and `86cd57fa20c9e626b6de2e8fc1e76786c70580ec`.