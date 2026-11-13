# T004 integration status — 2026-11-13

## Verified

- Exact-pin standalone GGML backend graph qualification remains in `RESULTS-T004-GRAPH-STAGE-DIAGNOSTIC-20261113.md`.
- Current binding rebuild/test passed gate/O/Q on RTX 3090: pointer equality, capture/replay, input-update output change, relative L2 around 0.53%.
- Added opt-in `SGLANG_GGUF_Q4_0_LLAMA_MMQ=1` dispatch guarded to Full CUDA Graph, BF16 M32, supported Q4_0 geometries; AOT remains default and all ineligible calls fall back.
- Python syntax and `git diff --check` passed. GPU returned to 1 MiB / 0% utilization; no relevant service listener was found; exclusive lock released.

## Not qualified

- No actual SGLang model graph capture or service request has successfully exercised this dispatch. Full repository module import failed before GGUF import because active `sgl_kernel` lacks `fp8_scaled_mm`; this is an environment/package mismatch, not proof the candidate works or fails.
- The freeze Run4 c32 all-token IDs/logits/selected-token logprob comparison and three paired unprofiled A/B have not run.
- No GO, performance, or service correctness claim is made. Do not commit/enable the opt-in path before actual model qualification.

## Immediate integration issue

The service implementation is still experimental and needs a controlled actual-service attempt using the repo-matched AOT `sgl_kernel` extension/runtime. The donor handle is initialized on the two warmup forwards and reused for capture; this lifecycle, graph dependency capture, output aliasing, per-weight handle count and cleanup must be validated in-process. Then prove donor hit via recorded runtime dispatch and graph kernel evidence before running frozen Run4.
