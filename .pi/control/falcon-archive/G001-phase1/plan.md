# G003 Plan

## Current state
- Phase 1 source commit: `b0bd1d96fc`.
- Phase 2A is complete; production baseline remains `extra_buffer`.
- The target fork already contains the 3090 HiCache lineage implementation. Relevant source hashes match the reference checkout for the unified radix/tree/controller/scheduler paths; do not replace them with upstream main.
- B2/B3 passed. B4 is BLOCKED because host pressure exhausted the target's host residency before lookup; no source patch was made.
- GPU is currently released.

## B1 audit frontier
1. Read the reference lineage reports and source/test inventory from `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`.
2. Compare target/reference HiCache source and identify exact runtime route for Falcon-H1.
3. Establish whether the old #33713 host-anchor/prune sequence remains possible in this lineage before starting GPU work.

## B2-B6 execution frontier
B2/B3 are complete. B4 requires owner decision on a rerun that preserves the target prefix in the finite host pool while still forcing device eviction. B5/B6 remain stopped until authoritative FULL and MAMBA host-hit/H→D transfer evidence is obtained.

## Stop conditions
Stop on startup incompatibility, semantic corruption, decode graph regression, CUDA/runtime error, scheduler crash, missing MAMBA host tier, missing authoritative host-hit/H→D evidence, or demonstrated host-anchor loss. Do not workaround by disabling eviction.

## Artifacts
All B1 audit, server logs, telemetry, probes, and report belong under `control/G003-phase2b-hicache/`; no benchmark artifacts enter source commits.
