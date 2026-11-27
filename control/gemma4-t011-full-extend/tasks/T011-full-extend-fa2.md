# T011 — Full Extend FA2 qualification and conditional integration

Status: DONE

## Work area
`python/sglang/srt/layers/attention/`, `python/sglang/kernels/ops/attention/`, `control/gemma4-t011-full-extend/`, durable run artifacts under `/data/sglang-hicache/gemma4/runs/`.

## Objective
At frozen baseline `c102ccbc5cfd17b510f896b23107204daf5ed0d7` / production source `a76206a5fb`, qualify and, only if effective, integrate the user-specified FlashInfer FA2 Paged Prefix + Ragged Extend + MergeState path for Full Attention Extend with head_dim=512. No substitute algorithm.

## Inputs
- Existing trace: `/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof/nsys/gemma4.sqlite`.
- Prior evidence/report: `control/gemma4-rtx3090-throughput-scheduling/runs/T010-GPU-HARDWARE-PROFILING-20261127.md`, `runs/T011-ATTENTION-REVIEW.md`.
- Reference path: `python/sglang/srt/layers/attention/flashinfer_backend.py`; FlashInfer FA2 `attention/prefill.cuh`, paged/ragged wrappers and `cascade.merge_state`.
- Fixed shapes: (new,prefix) = (1024,7168), (4096,12288), (4096,28672); SM86, BF16 Q, FP8 E5M2 prefix KV, head_dim512, page_size1, actual GQA geometry.

## Completion
First correlate trace grid `(1,8,128)` to actual layer/type and source-derived head_dim/BLOCK_M/BLOCK_N/context, without full recapture. Then isolate supported FlashInfer APIs and measure complete plan + Attention + merge cost against current complete Triton Extend for all three shapes, including memory overhead. If unsupported or no clear net benefit, stop the candidate with evidence and no production edit. If it passes, integrate only the Full Extend route using existing pool/metadata/owner mapping; preserve FP8 prefix+descale, original-precision new K/V+causal mask, Shared-KV semantics, LSE log-base and empty Prefix. Verify outputs/LSE against FP32 oracle, then one original C-8 L1-only acceptance and full three-tier restore. Report operator speedup, actual memory cost, end-to-end outcome and source SHA; commit/push authorized T011 changes.

## Result
The earlier head_dim=256 applicability STOP was incorrect and is superseded. Correct conversion and independent checkpoint shapes establish Full head_dim=512, Q/KV heads 8/2, SWA head_dim=256. The bounded qualification reached FlashInfer `paged.plan()` and failed before timing with `No supported CUDA architectures found for major versions [10, 11, 12]`. Installed FlashInfer 0.6.17 requests only SM100+ for one-byte KV with head_dim>256 (except its NVFP4 opt-in); target is RTX 3090 SM86 and requested KV is FP8 E5M2. The specific FA2 path is therefore unsupported under the frozen production constraints. No shape measurements, oracle, production integration, C-8 acceptance, or three-tier restore were run; no speedup, memory, or end-to-end claim is made. Production remains unchanged at `a76206a5fb`. Evidence: `runs/T011-FULL-EXTEND-FA2-QUALIFICATION.md` and `runs/20261127T-fa2-op-r1/driver.log`.

## Remaining
None within the authorized candidate. Resumption requires a material scope change to supported hardware/library or KV representation, outside current authorization.
