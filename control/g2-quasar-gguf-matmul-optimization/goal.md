# G2 QUASAR GGUF MatMul Optimization Feasibility

## Goal
Map measured c32 Q4_0/Q6_K Graph-node kernels to actual Linear/tensor/shapes and assess compatible existing optimizations; implement only a directly reusable, format-compatible improvement with correctness and narrow c32 A/B, otherwise present a new-kernel/format-conversion proposal for architecture decision.

## Constraints
Preserve dirty worktree; do not repeat full profiling/benchmark. GPU only under `/tmp/f1-r16b-gpu-exclusive.lock`. Do not conflate GGUF Q4_0/Q6_K with Marlin W4A16. Separate conversion cost, kernel time, and numerical compatibility. New algorithms/formats require architecture decision before implementation.

## Completion
Correct prior report statistics/unknown wording; map kernels to runtime Linear/tensor/shape/path; run limited same-input kernel comparisons with correctness and any conversion cost; either perform narrowly justified compatible optimization plus c32 A/B, or submit evidence-based technical proposal with estimated upside and engineering cost.