# T015 — FA2 bounded ragged sub-batch

- Baseline: `c1feed4d21` (T014 report), working tree only.
- Scope: `bf16_ragged_extend.py` + the FA2 dispatch in `triton_backend.py`.
- Out of scope: scheduler, KV pool sizing, Humming, new kernels, decode path.

## Acceptance

| Item | Gate |
| --- | --- |
| Evidence for the premise | over-budget dominates FA2 skips, and the skipped forwards are splittable per request |
| Numeric equivalence | grouped vs ungrouped reference: max abs diff 0 (module level) |
| Single-group path | unchanged (same plan tensors, same kernels) |
| Net benefit | over-budget forward faster than the Triton fallback it used to take |
| C-8 L1-only | above the accepted 760.17 TPS (T013 FA2) with identical payloads |
| Three-tier | above the accepted 644.21 TPS, capacity and L3 restore unchanged |
| Long context | not below the accepted 135.22 TPS |
| Resources | peak VRAM within the frozen budget, decode graph intact |
