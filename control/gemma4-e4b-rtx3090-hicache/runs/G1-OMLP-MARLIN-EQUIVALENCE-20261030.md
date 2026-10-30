# G1 O-projection and MLP Marlin equivalence — 2026-10-30

## Result

**PASS — no O-projection/MLP packed-weight or scale mismatch found** for the captured layer-17 TP=2 runtime rank 0. The pinned checkpoint tensors, after SGLang's actual source orientation, gate/up fusion and production Marlin repack/scale permutation, are elementwise identical to the loaded SGLang Marlin buffers. This closes the specific effective-weight-layout hypothesis for these targets/layer; it does not certify every layer, operator arithmetic, HF-vs-SGLang outputs or G1 acceptance. No source correction was indicated.

## Scope and method

Checkpoint: `google/gemma-4-E4B-it-qat-w4a16-ct`, revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, `model.safetensors` SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Config declares symmetric INT4, group strategy, group size 32; no activation quantization, zero-point or act-order.

Reused the established layer-17 N512 path (the L17 causal full-attention Forward and existing same-input O/MLP operator evidence), PLE Marlin verification procedure, and actual SGLang `CompressedTensorsWNA16.process_weights_after_loading()` behavior. One locked GPU service run received the existing frozen 512-ID request and captured post-loader rank-0 Marlin parameters from layer 17: RID `c1816dcc1b9a4303b150ca25dec023bc`. The request returned HTTP 200 / one generated token. Snapshot is instance-bound to that runtime RID; `gemma4_forward_id` is unavailable at the outer model-forward seam (`null`), so it is not represented as an atomic operation-level forward capture.

Compared the checkpoint's packed source tensors transformed using SGLang production `gptq_marlin_repack` and the source-defined `marlin_permute_scales` ordering against the captured runtime buffers. This uses the real stored pack-quantized layout and loader's Q/K/N and scale transformations, not a guessed Marlin inverse decoder. O projection retains full K/N parameter layout despite RowParallel execution; fused MLP `gate_up_proj` concatenates complete gate then up projections; `down_proj` retains its full parameter layout. TP rank/size are recorded as 0/2. Runtime shapes and target source mapping are preserved in the JSON artifact.

## Exact comparisons

All six tensors are elementwise equal; mismatches are zero and expected/actual SHA-256 values match:

| Runtime parameter | Shape | Elements | Result |
|---|---:|---:|---|
| `o_proj.weight_packed` | `[256,5120]` int32 | 1,310,720 | exact |
| `o_proj.weight_scale` | `[128,2560]` BF16 | 327,680 | exact |
| `gate_up_proj.weight_packed` | `[160,40960]` int32 | 6,553,600 | exact |
| `gate_up_proj.weight_scale` | `[80,20480]` BF16 | 1,638,400 | exact |
| `down_proj.weight_packed` | `[640,5120]` int32 | 3,276,800 | exact |
| `down_proj.weight_scale` | `[320,2560]` BF16 | 819,200 | exact |

## Disposition

Close the layer-17 O-projection/MLP packed-weight/scales mismatch hypothesis as **not supported**. Prior same-input operator differences remain arithmetic/backend evidence, not evidence of wrong effective weights; neither this comparison nor the reused L17 results justify production math changes. Frozen HF CPU Oracle/guard/thresholds are untouched; G1 remains **FAILED / NOT ACCEPTED**. No source or control files were staged or committed; existing dirty and untracked worktree state was preserved. GPU cleanup verified: no service remains; `nvidia-smi` reported 1 MiB and 0% utilization.

## Artifacts

External, local-only artifacts under `/data/sglang-hicache/gemma4/runs/20261030T-g1-omlp-weight-equivalence/`:
- `sglang-layer17-marlin-weights.pt` — runtime snapshot, SHA-256 `20cc906dd8268fb11e4a716535d05e0a95b3170842118d937925ebeebe2171ab`.
- `sglang-layer17-marlin-weights.comparison.json` — per-tensor counts, shape, hash and equality, SHA-256 `b81fd05afae37d7c535b9c5c48e8490d7462a142a41ddc972b22ee4d7dcc1af3`.
- `compare_marlin_snapshot.py` — reproducible comparison driver calling production CUDA Marlin repack and the source scale permutation.
- `bootstrap/capture_omlp_weights.py`, `bootstrap/sitecustomize.py` — one-shot narrowly scoped layer-17 capture hook.

Related prior evidence: `G1-PLE-MARLIN-EQUIVALENCE-20261028.md`, `G1-PLE-RMSNORM-ATTRIBUTION-20261028.md`, `G1-L17-FULLATTN-LOCALIZATION-20261028.md`, and `/data/sglang-hicache/gemma4/runs/20261028T182819Z-g1-l17-attn-closure/l17-matched-operator-comparison.json`.
