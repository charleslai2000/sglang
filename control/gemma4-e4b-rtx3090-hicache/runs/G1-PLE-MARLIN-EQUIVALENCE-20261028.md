# G1 PLE Marlin equivalence and layer growth — 2026-10-28

## Finding

The PLE W4A16 Marlin repack and group scales are equivalent to the pinned checkpoint/HF logical weight path for both bound N512/N514 forwards. The prior ~`1e-4` projection residual is therefore a backend arithmetic/accumulation difference on identical logical weights, not evidence of a Marlin repack, dimension, group-scale, or zero-point defect. No production change is justified. The frozen guard remains **FAILED**, G1 **NOT ACCEPTED**.

## Weight/metadata checks

- Pinned checkpoint `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Quantization config: symmetric INT4, group strategy, group size 32, no act-order, no activation quantization. Source PLE projection packed tensor is `[10752,320]`; scales `[10752,80]`; logical weight shape `[10752,2560]` (HF Linear orientation `[out,in]`). BF16 scale dtype. No zero-point tensor is present for this symmetric format; no `g_idx`/act-order mapping is present.
- Applied the repository's actual `gptq_marlin_repack` to the source packed tensor in the production loader orientation, and the actual `marlin_permute_scales` to checkpoint scales. Compared to the captured post-load Marlin buffers: packed INT4 buffer exact equality, `3,440,640/3,440,640` words; permuted scales exact equality, `860,160/860,160` values. Result shapes `[160,21504]` and `[80,10752]`, respectively. Thus this verifies the real runtime repack and parameter layout, not an assumed Marlin inverse decoder.
- Independently applied compressed-tensors official `unpack_from_int32` and `dequantize` for symmetric INT4/group32 to the pinned source tensors. The resulting BF16 `[10752,2560]` matrix is bitwise equal to the matrix captured after HF's official `decompress_model()` lifecycle: max/mean/rel-L2 all zero, differing elements zero. This establishes logical matrix identity between the checkpoint interpretation used by HF and SGLang's packed source.
- The captured SGLang live Marlin buffer comparison is an instance-level loaded-parameter tap rather than a parameter snapshot atomically keyed to each request UUID. It was captured from the same pinned model/runtime and independently reproduced from checkpoint using the production repack functions; request-bound output comparison below remains the actual N512/N514 evidence.

## Matched projection and downstream boundary

For each exact-ID/position bound EXTEND Forward (N512 UUID `9a8002e27f914c4d96dacc3ca231d01b`, RID `34dbafbab17a4d7d8c071e92b402681b`; N514 UUID `497f1b1f349244b4b853aed44d1cd6ec`, RID `4d01e4276ac64fff81c0d91e7876b56b`), main/PLE embeddings are bitwise equal to HF and the first layer input is bitwise equal. On the matched BF16 PLE input, actual Marlin Linear output vs HF official decompressed Linear output remains rel-L2 `8.855e-05` (N512) / `8.853e-05` (N514), max abs `0.001953125`. After common projection scale and BF16 materialization, PLE norm input residual is max abs `6.1035e-05`; same-input RMSNorm CUDA-vs-HF-formula rel-L2 remains `2.62e-6` / `6.07e-7`. This small initial difference is consistent with backend GEMM accumulation/rounding; it is not a proof of all later error being benign.

The reused layer-output sidecars are individually bound to the above Forward/RID, exact IDs and positions `1..N`, EXTEND, and pinned model SHA. Correct pairing is SGLang `layer_output.i` (decoder layer i output including residual/PLE/scalar) against HF `hidden_states[i+1]`; `hidden_states[0]` is embedding/layer-0 input. Full-sequence rel-L2 at layers 0/1/16/17/23/40 is:

| N | L0 | L1 | L16 | L17 | L23 | L40 |
|---|---:|---:|---:|---:|---:|---:|
| 512 | .005277 | .003336 | .012746 | .024836 | .036407 | .070676 |
| 514 | .006052 | .003911 | .016736 | .031239 | .070977 | .062366 |

The first consequential observed growth is between layers 16 and 17 (delta rel-L2 +`.01209` N512, +`.01450` N514), with further accumulated residual, including N514 layer23. This is localization only, not attribution: later operator inputs/effective weights/masks are not jointly established equivalent. The layer41 endpoint has a large apparent residual (`~.928`) but its HF `hidden_states[42]` post-final-normalization boundary is not equivalent to the SGLang decoder-output sidecar; do not treat it as a decoder-layer-41 defect. No full GSM8K run was repeated.

## Disposition

No INT4 repack/group-scale/zero-point/dimension/dtype production defect was found. Keep the frozen guard and tolerance unchanged. Do not classify the whole downstream divergence as Marlin weight corruption; continue with matched-input layer16/17 component attribution and operation-level precision/mask comparison. Existing RMSNorm and embeddings results stand. GPU verification used `/tmp/f1-r16b-gpu-exclusive.lock`; no service remains.

## Artifacts

- Bound captures and HF weights: `/data/sglang-hicache/gemma4/runs/20261028T-g1-first-boundary/fixed/` (`forward.9a8002e27f914c4d96dacc3ca231d01b.*`, `forward.497f1b1f349244b4b853aed44d1cd6ec.*`, `hf-cuda-ple-n512.pt`, `hf-cuda-ple-n514.pt`, `sgl-ple-weights-v2.pt`).
- Full causal HF hidden-state references: `/tmp/hf-full-causal-ple-n512.pt`, `/tmp/hf-full-causal-ple-n514.pt`.
- Production transformations inspected/executed: `python/sglang/srt/layers/quantization/compressed_tensors/schemes/compressed_tensors_wNa16.py`, `python/sglang/srt/layers/quantization/marlin_utils.py`, `python/sglang/srt/layers/parameter.py`; HF decompression: installed `compressed_tensors` pack-quantized compressor/lifecycle APIs.
