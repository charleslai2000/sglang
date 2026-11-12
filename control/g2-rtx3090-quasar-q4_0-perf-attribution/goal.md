# G2 QUASAR Q4_0 RTX3090 Performance Attribution

## Goal
Identify actual QUASAR GGUF weight formats and serving kernels, explain 8K Radix Prefix-Hit Extend and Decode performance costs with controlled GPU evidence, and repair confirmed dispatch/configuration defects with a same-model/workload A/B where feasible.

## Constraints
Preserve the existing dirty tree and all source ownership. Use current production fork/runtime, exact QUASAR checkpoint and BF16 compute/E5M2 KV; no other model, quantization replacement, new kernel framework, or quality re-certification. GPU workloads hold `/tmp/f1-r16b-gpu-exclusive.lock`. Historical W4A16 data is a reference only; separate kernel and model identities explicitly. No broad instrumentation or whole-model NCU sweep.

## Completion
Establish tensor formats and per-linear runtime dispatch for representative c1/c8/c32 scenarios; profile actual GPU kernel time and attempt targeted hardware counters; state confirmed/excluded/unknown causes; if a confirmed authorized issue is fixable, make narrow repair and run same-identity A/B; otherwise document the evidenced no-fix disposition. Preserve artifacts and comparability limits. Result: c8 Extend and c32 Graph-node costs are attributed; NCU is blocked by device permission (`ERR_NVGPUCTRPERM`); no actionable code defect identified; c8 DeviceTimer/NVTX decomposition remains explicitly UNKNOWN.
