# Gemma4 RTX3090 Radix Prefix-Hit performance

## Goal
Measure fixed 7,168-token Radix L1 prefix hit + 1,024-token extend, 8,192-token prompt, greedy 256-token output at concurrency c1/2/4/8/16/24/32 on RTX3090. Historical W4A16/BF16-KV remains the reference; later model/runtime variants must be identified as separate observations, not silently attributed.

## Constraints
TP1, Triton, GPU Radix L1, no Host/Disk HiCache substitution. Record actual server Decode batch and CUDA Graph separately from client concurrency. Preserve dirty worktree and exact source/model/instrumentation identities. GPU workloads hold `/tmp/f1-r16b-gpu-exclusive.lock`.

## Completion
Every accepted run verifies exact cache/prompt/output lengths from client and Scheduler; at least warmup plus three valid trials; records Prefill/Decode CUDA Event boundaries, client throughput, TTFT/E2E, graph/batch evidence and GPU peak; preserves raw evidence and hashes; cleans up server, port, GPU and lock. Comparisons disclose any model, cache dtype, source, instrumentation, or config mismatch.
