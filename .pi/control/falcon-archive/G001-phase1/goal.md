# G003 — Phase 2B Falcon-H1 HiCache correctness and host-tier reuse

## Goal
Validate Falcon-H1 GPTQ-Int4 hybrid HiCache GPU-L1 ↔ host-DRAM-L2 behavior, including FULL/KV and MAMBA host pools, device eviction, host-resident radix-node survivability, H→D load-back, and session churn, without changing the Phase 2A production baseline.

## Production baseline
- Falcon-H1 GPTQ-Int4
- Mamba SSM BF16
- Mamba radix strategy `extra_buffer` only
- prefill CUDA graph disabled
- decode CUDA graph full
- Radix cache on
- speculative decoding off
- context 8192 initially

## Only new variable
HiCache L2 host tier. Do not use `extra_buffer_lazy`.

## Scope
- B1 source audit of actual UnifiedRadixCache/hybrid controller/FULL+MAMBA host-pool path.
- Reuse and explicitly account for the HiCache improvements already present in the 3090 reference lineage: unified hybrid component residency, MAMBA `host_value`, host/device LRU separation, evictable host leaves, host/device transfer lifecycle, restore retry/frontier wake, host-allocation telemetry, and focused dependency-free tests.
- B2 minimal L2 bring-up with ratio 1, write-through, no L3/storage backend.
- B3 semantic correctness and decode-graph gate.
- B4 forced GPU eviction followed by evidence-based host hit and H→D load-back.
- B5 only if needed: minimal fix for a demonstrated host-anchor/prune defect.
- B6 only after B4 PASS: 200 logical-session churn.

## Exclusions
- No `extra_buffer_lazy` or `SGLANG_OPT_MAMBA_SKIP_DECODE_LOCK=1`.
- No HiCache storage/L3 backend, Mooncake, file cache, or `--hicache-size`.
- No 32K context, KV FP8, memory-ratio changes, speculative decoding, or performance tuning.
- Do not infer host hit/load-back from TTFT alone; use cache telemetry and transfer events.
- Do not modify source before the audit and minimal bring-up establish a concrete defect.

## Completion
PASS only if HiCache OFF/ON semantic controls pass, FULL and MAMBA host allocations are observed, the forced test proves D→H backup, device eviction, host residency, H→D load-back, reduced recompute, and correct semantics, and 200-session churn passes. If a concrete known bug is proven, record BLOCKED at that seam or apply only the smallest authorized fix with a focused regression.
