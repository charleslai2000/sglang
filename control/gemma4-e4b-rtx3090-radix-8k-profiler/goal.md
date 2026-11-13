# Gemma4 RTX3090 Radix 8K Prefill/Decode Profiler Diagnosis

## Goal

Use bounded Nsight Systems and, only if indicated, targeted Nsight Compute profiling on the accepted real-batch-16/24/32 Gemma4 W4A16/BF16-KV run configuration to measure 7,168-token Radix match plus 1,024-token Prefill GPU time and explain Decode GPU-forward versus online TPOT timing.

## Scope and constraints

This profiling Goal builds on the accepted throughput result and the separate percentile closure. It does not reopen or replace either measurement Goal.

Reuse the accepted fixture, runner, request-linked Scheduler evidence and clean performance baseline. Profile only necessary Prefill and continuous Decode windows; do not rerun the throughput matrix. Preserve measured actual batches and graph captures to 32. Keep batch GPU time batch-level, distinguish CPU clocks/CUDA Events/Profiler timeline, and tie spans to scheduler steps/RIDs. Do not tune parameters or implement optimizations. No production math, quantization, cache semantics, G1 thresholds, GPU clocks or system config changes. Hold `/tmp/f1-r16b-gpu-exclusive.lock` for all GPU workloads; preserve unrelated dirty/untracked state. G1 remains FAILED / NOT ACCEPTED.

## Completion

Archive valid bounded Nsight traces and analysis with GPU time for 1K Prefill at b16/b24/b32, continuous scheduler-step-linked Decode timelines and a reconciled CPU/GPU activity breakdown. Identify key kernels from Nsight Systems before any narrowly scoped Nsight Compute capture. Answer the five user questions with evidence or UNKNOWN, fix measurement tooling as needed, clean up services/resources, and selectively commit/push only owned artifacts with remote SHA verification.