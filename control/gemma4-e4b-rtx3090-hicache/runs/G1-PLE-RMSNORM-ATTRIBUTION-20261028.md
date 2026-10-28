# G1 PLE RMSNorm attribution — 2026-10-28

## Finding

Real N512/N514 CUDA forwards were captured under `/tmp/f1-r16b-gpu-exclusive.lock`; exact token IDs and positions `1..N` were bound to each HF oracle. Main embedding and PLE table embeddings remain bitwise equal. For the new paired forwards, SGLang and HF RMSNorm inputs are **not** equal: max abs difference is `6.1035e-05`, with 582,426/6,881,280 (N512) and 585,386/6,908,928 (N514) elements differing. RMSNorm parameters do match exactly: BF16 weight `[256]`, `eps=1e-6`, BF16 input/output. RMSNorm output differences are max abs `.25`, mean abs about `.000196`, rel-L2 `.002142` (N512) / `.002089` (N514).

HF Transformers computes Gemma4 RMSNorm in FP32 (square/mean, add eps, reciprocal square root, multiply by FP32 weight) then casts to BF16. SGLang selects `forward_cuda -> sgl_kernel.rmsnorm -> FlashInfer RMSNorm`. Applying the SGLang CUDA kernel to the captured SGLang input and matching BF16 norm weight gives close agreement with that explicit HF formula on the **same input**: rel-L2 `2.62e-6` (N512), `6.07e-7` (N514), max abs `.00390625` / `.0009765625`. This supports ordinary reduction/rounding differences at the norm kernel, not an RMSNorm semantic or parameter defect; it is not a bitwise-equivalence claim.

## Upstream PLE projection

The first established difference is already present at the RMSNorm input, hence after the PLE projection and its scale. Additionally, the captured SGLang `ple_projection_raw` is the actual Marlin Linear output (pre-scale): against HF official decompressed Linear output on the same captured BF16 embedding, max abs is `0.001953125`, mean abs `3.19e-08`, rel-L2 `8.855e-05` for N512 and `8.853e-05` for N514. Applying the same scale and BF16 rounding leaves max abs `6.1035e-05`, rel-L2 `9.37e-05` / `9.66e-05`. This establishes a small W4A16 backend numerical difference in the projection itself; it does not distinguish expected Marlin accumulation/rounding from a packing/scaling defect. HF's official compressed-tensors lifecycle yields a BF16 logical Linear weight `[10752,2560]`, applies scale `1/sqrt(2560)=0.01976423537605237`, and produces BF16 Linear output. The pinned checkpoint stores this layer as INT4 `weight_packed [10752,320]`, BF16 `weight_scale [10752,80]`, and `weight_shape [10752,2560]`; quantization metadata specifies symmetric group-32 W4A16. The BF16 RMSNorm checkpoint value was verified elementwise equal to SGLang's captured loaded value.

The follow-up audit now resolves the repack uncertainty: production `gptq_marlin_repack` and `marlin_permute_scales` replayed from the checkpoint reproduce the captured Marlin packed-weight and scale buffers exactly (3,440,640 packed words and 860,160 scales). Compressed-tensors official INT4/group32 unpack/dequantization also reproduces HF `decompress_model()`'s logical BF16 matrix bitwise. See `G1-PLE-MARLIN-EQUIVALENCE-20261028.md` for configuration, tensor orientations, zero-point/act-order absence, and same-Forward layer residuals. The ~`1e-4` matched-input projection delta is therefore not a repack/scale defect; it remains a backend arithmetic/accumulation difference, without establishing later-layer attribution.

## Disposition and next step

No production defect is proven; no production math or guard tolerance changed. Frozen N512/N514 guard remains **FAILED**, and G1 remains **NOT ACCEPTED**. Marlin logical-weight, scale, dimension, dtype and zero-point semantics are now validated; continue with matched-input layer16/17 component attribution and consequential downstream boundaries. No GSM8K rerun is warranted.

## Artifacts

- SGLang norm input/weight: `/data/sglang-hicache/gemma4/runs/20261028T-g1-first-boundary/fixed/forward.d9a23a8c3a314d70823f158f535f0335.inputs` (N512), `forward.3eb037033eba4b3d83ba57427020718d.inputs` (N514).
- HF CUDA projection/norm captures: `/data/sglang-hicache/gemma4/runs/20261028T-g1-first-boundary/fixed/hf-cuda-ple-n512.pt`, `hf-cuda-ple-n514.pt`.
- SGLang Marlin parameter tap: `/data/sglang-hicache/gemma4/runs/20261028T-g1-first-boundary/fixed/sgl-ple-weights-v2.pt` (single service request; forward UUID was not populated on this wrapper capture, so it establishes loaded parameter identity/layout, not same-Forward weight linkage).
- All capture scripts/bootstrap and model outputs are outside the checkout. GPU is now idle (1 MiB used); service was stopped.
