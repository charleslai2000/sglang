# G1 O-projection and MLP Marlin equivalence — 2026-10-30

## Result

**PASS — no O-projection/MLP packed-weight or scale mismatch found** for the captured layer-17 single-GPU TP=1 runtime (the prior commit incorrectly labeled this TP=2). The pinned checkpoint tensors, after SGLang's actual source orientation, gate/up fusion and production Marlin repack/scale permutation, are elementwise identical to the loaded SGLang Marlin buffers. This closes the specific effective-weight-layout hypothesis for these targets/layer; it does not certify every layer, operator arithmetic, HF-vs-SGLang outputs or G1 acceptance. No source correction was indicated.

## Scope and method

Checkpoint: `google/gemma-4-E4B-it-qat-w4a16-ct`, revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, `model.safetensors` SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Config declares symmetric INT4, group strategy, group size 32; no activation quantization, zero-point or act-order.

Reused the established layer-17 N512 path (the L17 causal full-attention Forward and existing same-input O/MLP operator evidence), PLE Marlin verification procedure, and actual SGLang `CompressedTensorsWNA16.process_weights_after_loading()` behavior. One locked GPU service run received the existing frozen 512-ID request and captured post-loader rank-0 Marlin parameters from layer 17: RID `c1816dcc1b9a4303b150ca25dec023bc`. The request returned HTTP 200 / one generated token. Snapshot is instance-bound to that runtime RID; `gemma4_forward_id` is unavailable at the outer model-forward seam (`null`), so it is not represented as an atomic operation-level forward capture.

Compared the checkpoint's packed source tensors transformed using SGLang production `gptq_marlin_repack` and the source-defined `marlin_permute_scales` ordering against the captured runtime buffers. This uses the real stored pack-quantized layout and loader's Q/K/N and scale transformations, not a guessed Marlin inverse decoder. O projection retains full K/N parameter layout despite RowParallel execution; fused MLP `gate_up_proj` concatenates complete gate then up projections; `down_proj` retains its full parameter layout. The capture script itself records only the literal `layer=17` and parameter tensors; it does not provide TP rank/size. The comparison driver erroneously hard-coded `tp_size=2` and `rank=0`, and its first draft sliced source tensors accordingly. That label and slicing were wrong. Reanalysis using the actual full TP=1 source tensors reproduces all six captured buffers exactly; the corrected JSON reports `tp_size=1`, `tp_rank=0` based on the logged server args. Runtime shapes and target source mapping are preserved in the JSON artifact.

## Configuration audit and annotation correction

The captured `server-retry.log` serializes effective `server_args` with `tp_size=1`, `pp_size=1`, `dp_size=1`, `device='cuda'`, `base_gpu_id=0`, `gpu_id_step=1`; CLI launch did not pass a TP override. SGLang's `ServerArgs.tp_size` default is 1. The same host exposes exactly one device, GPU 0, RTX 3090 UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`; no `CUDA_VISIBLE_DEVICES` remapping was set in the launch environment. Thus world size is one. `capture_omlp_weights.py` reads `self.language_model.layers[17]` and dumps parameters but does not query or serialize TP rank/size. The comparison script originally hard-coded `rank=0` (correct rank by default) and erroneously `tp_size=2`, despite the logged `tp_size=1`; its source slicing and report label were therefore wrong. Re-running the same comparison with the full, unsliced checkpoint source and production repack/scale transforms reproduces all six runtime tensors exactly. No second GPU capture was needed: the captured service itself already used the requested single-GPU configuration.

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
- `sglang-layer17-marlin-weights.comparison.json` — corrected runtime configuration label (`tp_size=1`, `tp_rank=0`) plus per-tensor counts, shape, hash and equality; SHA-256 `c0d7b843ab4a420ea012e785d486ee0cf16a41a833800da71a658eebb69286d4`.
- `compare_marlin_snapshot.py` — reproducible comparison driver calling production CUDA Marlin repack and the source scale permutation.
- `bootstrap/capture_omlp_weights.py`, `bootstrap/sitecustomize.py` — one-shot narrowly scoped layer-17 capture hook.

Related prior evidence: `G1-PLE-MARLIN-EQUIVALENCE-20261028.md`, `G1-PLE-RMSNORM-ATTRIBUTION-20261028.md`, `G1-L17-FULLATTN-LOCALIZATION-20261028.md`, and `/data/sglang-hicache/gemma4/runs/20261028T182819Z-g1-l17-attn-closure/l17-matched-operator-comparison.json`.
