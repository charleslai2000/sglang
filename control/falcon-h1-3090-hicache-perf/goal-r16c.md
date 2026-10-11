# R16C — Falcon/3090 multi-turn performance and profiling

## Goal
Extend accepted R16B random-workload baseline with reproducible real multi-turn cache reuse measurements and usable Prefill/Decode GPU profiling, then rank evidence-based optimization opportunities.

## Frozen boundary
- Branch `3090-24g-hicache`; Falcon-H1-7B-Instruct-GPTQ-Int4 checkpoint `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, RTX 3090 single-GPU config unchanged.
- Clean baseline `481f2b48530916171d8fe62561e6580a6f4f094b` in `/tmp/sglang-f1-r16b-clean`; exclude unaccepted R15 candidate.
- Preserve R16B's 72 accepted random cases; do not repeat them.
- RTX 3090 exclusive; sibling opt worktree read-only. L3 correctness gaps remain separate and do not block R16C.
- No production cache-semantics changes to manufacture hits.

## Completion
- Matched, deterministic GPU-only and GPU+Host multi-turn workloads at concurrency 1/4/8/9, at least three repeats at key points; same token sequence/order, arrival/barrier policy, output lengths and cold/warm preconditions.
- Record cumulative session prefixes/rounds/checkpoint boundaries, cross-session reuse distance, cache tier hit tokens, D→H/H→D and actual restored amounts, TTFT/TPOT/input/output TPS/RPS/P95 and repeats' spread. Zero host hits require analysis against actual capacity/eviction/reuse distance.
- Valid CUDA kernel traces for Prefill and Decode; first prove the instrumentation captures CUDA work from the actual service scheduler process. Nsight Systems timelines and Nsight Compute kernel metrics are separate evidence.
- Determine concurrency 8→9 mechanism from GPU utilization/metrics, kernel/launch time, CUDA Graph/Mamba limits, request queue/CPU and effective concurrency; mark unsupported causes UNKNOWN.
- Preserve provenance and exclude failed artifacts. Run necessary regressions; commit/push completed work and leave no service/GPU use or dirty worktree.

## Status
ACTIVE. R16B randomized baseline is accepted. GSP helper in R16B is invalid/incomplete; R16C must use the existing token-ID multi-turn cache-hit kit or a minimal deterministic runner based on it. Nsight root cause is not established: main-process CUDA captures; actual spawn child test captures once written correctly; prior child smoke was invalid and old service reports have no kernel data.
