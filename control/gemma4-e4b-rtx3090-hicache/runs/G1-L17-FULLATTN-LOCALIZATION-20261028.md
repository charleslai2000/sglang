# G1 L17 full-attention localization — 2026-10-28

## Result

N512/N514 L16→L17 shows increased absolute error, but it is not evidence by itself of a full-attention defect. The denominator (HF L2 norm) also drops sharply at L17. Existing same-Forward layer captures confirm the boundary change; a new locked GPU run recaptured operation taps for L5/L11 controls and L17 on both frozen prompts, and official HF `decompress_model()` CUDA layer-17 replays consumed the exact captured SGLang L16 output, exact PLE tap, positions `1..N`, and additive causal mask. No production semantic error was proven; no source fix or guard change is justified. G1 remains NOT ACCEPTED.

## L2 accounting

SGLang `layer_output.i` is paired with HF `hidden_states[i+1]`. Values below are full-sequence Frobenius/L2 norms over `[N,2560]`; delta is `||SGLang-HF||₂`.

| N | boundary | delta L2 | HF output L2 | rel-L2 |
|---|---|---:|---:|---:|
| 512 | L4 | 12.66671 | 2033.647 | .006229 |
| 512 | L5 | 16.31592 | 2107.988 | .007740 |
| 512 | L10 | 17.99579 | 2660.237 | .006765 |
| 512 | L11 | 22.34155 | 2814.012 | .007939 |
| 512 | L16 | 35.83710 | 2811.704 | .012746 |
| 512 | L17 | 48.99832 | 1972.903 | .024836 |
| 514 | L4 | 12.96052 | 2045.696 | .006336 |
| 514 | L5 | 17.11237 | 2063.692 | .008292 |
| 514 | L10 | 18.81889 | 2646.275 | .007111 |
| 514 | L11 | 23.85015 | 2791.678 | .008543 |
| 514 | L16 | 47.06352 | 2812.077 | .016736 |
| 514 | L17 | 61.43641 | 1966.656 | .031239 |

Absolute error rises by 13.16122 (36.7%, ×1.367) at N512 and 14.37289 (30.5%, ×1.305) at N514 from L16 to L17. The HF norm simultaneously falls 29.8% / 30.1%, so rel-L2 nearly doubles (`.012746→.024836`, `.016736→.031239`). L5 and L11 are modest control increases (absolute ×1.288/×1.242 at N512, ×1.320/×1.267 at N514; rel-L2 increases only ~.0015–.0020). L17 is a stronger boundary-localized growth, not proof of causality.

## Same-input component capture and direct replay

A real SGLang service ran both exact frozen prompts under `/tmp/f1-r16b-gpu-exclusive.lock`, BF16 KV, Triton prefill, no radix prefix, no CUDA Graph. Component taps cover layers 5, 11 and 17 and bind to their own request RID, Forward UUID, all exact IDs, positions, prefix/query lengths, and model SHA. For each watched layer the captured `decoder_layer_input` equals the prior layer-output sidecar bitwise. N512 Forward `27938aaa288e45b7bae2e56fd66fc740`, RID `08f220441c0b4db48fe32d233ca22b0c`; N514 Forward `a73eab08f12143d5aa4fb4fac4a6708f`, RID `265b487b3dd047c4ad26cfa42f09f31b`.

For both Ns, HF CUDA L17 replay loaded the official pinned model and applied its official compressed-tensors `decompress_model()` lifecycle. Replay inputs were taken from the corresponding SGLang L16 output and L17 PLE tap (BF16), with positions `1..N`; mask was additive causal `-inf` above the diagonal `[1,1,N,N]`. HF attention implementation was explicitly eager. The replay captured HF input norm, Q/K/V projections/norms, RoPE operands, consumed attention mask, attention-head output, O projection and decoder submodules. This is an independent same-input layer replay, not a production-change test.

- L17 attention-norm input vs SGLang runtime tap is close (rel-L2 `1.431e-5` / `1.389e-5`; max abs `.03125`), consistent with fused RMSNorm rounding.
- HF decompressed Q/K/V Linear vs SGLang Marlin Q/K/V on the replay input: Q `.00010485/.00010904`, K `.00010673/.00009752`, V `.00011706/.00010164` rel-L2 (N512/N514). Post-QKV per-head norm differences are each ~`1.4–1.6e-4`. These are backend arithmetic-scale differences, not a demonstrated weight/layout error; PLE Marlin loading equivalence was established separately in `G1-PLE-MARLIN-EQUIVALENCE-20261028.md`.
- The initial HF eager replay gave attention-head rel-L2 `.003587` (N512) / `.003439` (N514), max abs `.03125`, but was not same-Q/K/V and could not isolate attention. That result is superseded for operator localization by the same-operand comparison below.
- HF replay post-attention/FFN/PLE boundaries were captured, but differ in upstream inputs and do not by themselves prove the first erroneous production operation.

## Same-operand attention closure

A second locked service run recaptured only the frozen N512/N514 forwards and bound components by RID, Forward UUID, all input IDs, positions, and model identity. Actual post-RoPE Q/K and consumed V at `Gemma4Attention` entry are bitwise equal to Q/K/V passed into the Triton backend. Shapes are N×8×512 for Q and N×2×512 for K/V; the runtime tensors are `torch.bfloat16` (capture sidecars serialize their values as float32). Kernel operands are Q/K/V extend tensors, and capture checks confirm they match these model-side operands. `qo_indptr=[0,N]`; `kv_indptr=[0,0]`, `kv_indices=[]`, prefix=0, page size 1. Thus all keys are in the current extend tensors, with the valid mask exactly `key_position <= query_position`; no custom mask or sliding window is active. Kernel flags/parameters: causal=true, sm_scale=1.0, k/v descale=1.0, max_extend_len=N, logit_cap=0, sliding_window_size=-1. Gemma4 model source also sets RadixAttention scale to 1.0.

Using the exact captured Q/K/V, cast back to runtime BF16, HF CUDA eager-style GQA (`repeat_kv`, QK matmul, additive upper-triangular -inf mask, softmax, PV matmul) with **explicit scale 1.0** gives SGLang Triton attention-head rel-L2 `.00357372` (N512) and `.00340166` (N514), max abs `.03320/.03125`. The scale comparator was also evaluated on those runtime-BF16 inputs. This is a valid same-operand/mask comparison; it does not alone identify a semantic defect because eager and Triton reductions may round differently. The default `1/sqrt(512)` comparator instead gives rel-L2 `1.04845/1.01453`, demonstrating that HF's unconfigured default scale is not the Gemma4 contract. No mask/index or scale mismatch is observed.

The earlier `.003587/.003439` replay comparison was not same-QKV and is superseded for attention localization by this direct result. A separate FP64 reference was computed in float64 from the exact runtime BF16 Q/K/V and causal `key<=query` mask at scale 1.0; each backend was compared separately against that reference. Results: N512 Triton rel-L2 `.0016913`, max abs `.01858`, RMSE `.001339`, median/p90/p99/p99.9 abs `.000560/.002110/.004162/.007423`; HF CUDA Eager rel-L2 `.0032594`, max abs `.03342`, RMSE `.002581`, percentiles `.001185/.004089/.008889/.014145`. N514 Triton `.0016899`, max `.01805`, RMSE `.001350`, percentiles `.000567/.002131/.004196/.007443`; HF Eager `.0030947`, max `.03191`, RMSE `.002472`, percentiles `.001112/.003885/.008620/.014058`. On these same BF16 operands Triton is closer to the FP64 arithmetic reference; this does not itself establish the FP64 reference as an end-to-end model oracle or a semantic defect.

A controlled real-service counterfactual then ran both frozen prompts in isolated baseline/replacement arms with the same exact IDs/positions and model SHA, no prefix cache/graphs, and bound each capture by RID + Forward UUID. The opt-in hook computes both candidate outputs from the actual same Q/K/V; baseline returns Triton, replacement changes only the L17 attention-head tensor to the BF16 HF-Eager result. Sidecar tensor equality independently confirms baseline effective==Triton and replacement effective==Eager bitwise. Layer output is compared against HF `hidden_states[18]`; last-prompt-row full logits against the exact full-causal HF oracle:

| N | arm | L17 abs L2 to HF | L17 rel-L2 | final-logits rel-L2 | logits max abs | greedy vs HF |
|---|---|---:|---:|---:|---:|---|
|512|baseline|48.99832|.0248356|.311283|3.11537|same (107)|
|512|Eager-head replacement|49.55342|.0251170|.357772|3.33177|same (107)|
|514|baseline|61.43641|.0312390|.188240|5.88972|same (236761)|
|514|Eager-head replacement|61.87130|.0314601|.196530|6.63554|same (236761)|

Replacement worsens L17 absolute error by `.55511` (1.13%) / `.43488` (.71%) and logits rel-L2 by `.04649` (14.93% relative increase) / `.00829` (4.40% increase), for N512/N514. It swaps rank order within top-10 in both cases, but not greedy token. Thus the Eager-vs-Triton difference has measurable downstream influence but the requested substitution does not improve agreement with HF; it is not a plausible correction to the observed G1 divergence. No production semantic error is proven. The same-Forward run includes SGLang O-projection, fused post-attention/pre-FFN norm, MLP, post-FFN norm, PLE and decoder output taps. Attention-only substitution has now been directly measured; that kernel investigation is closed. Existing taps were reused for CPU arithmetic checks using the pinned HF model after the official compressed-tensors `decompress_model()` lifecycle, with the exact same BF16 attention-head, pre-attention-norm residual, or pre-FFN tensors supplied as each runtime tap. HF O projection followed by post-attention norm vs SGLang runtime post-attention norm rel-L2 is `.0001183/.0001419` (N512/N514), max abs `.03125`; this is consistent with backend accumulation/rounding, while an isolated O-projection output tap is absent and effective Marlin O weight parity is unproven. BF16 residual-add then pre-FFN norm vs runtime pre-FFN tap rel-L2 `.002944/.002935`, max `.015625/.0078125`; upstream component operands are BF16 and this is not evidence of a semantic error. MLP replay on the exact runtime pre-FFN BF16 tensor vs runtime MLP tap rel-L2 `.002646/.002616`, max `.0078125`; no independent MLP semantic mismatch was found. These CPU same-input computations are operation-localization, not CUDA acceptance proofs; exact effective O/MLP Marlin weight parity is still absent. The operation summary and caveats are in `/data/sglang-hicache/gemma4/runs/20261028T182819Z-g1-l17-attn-closure/l17-matched-operator-comparison.json`. This result file is external to the checkout; detailed numerical values are preserved in this committed report.

Do not compare those L17 taps to the separate full-causal HF hidden-state oracle as if they were the same Forward: the component run UUID/RID differs from the original boundary run, and captured PLE differs slightly from HF combined PLE (~`.00195` rel-L2). Oracle contracts are also distinct: the frozen guard is HF CPU Eager, `use_cache=False`, compressed-tensors QAT execution; the full-causal layer oracle is HF CUDA Eager, additive causal mask and full context PLE. HF CPU-vs-CUDA Eager alone differs by rel-L2 `.151008/.073112` at N512/N514. Neither oracle contract changes here. The frozen HF guard remains FAILED and its choice as a hard RTX3090 production oracle requires architecture/owner disposition; this is the bounded unresolved decision, not a reason to alter tolerance or production math. No independent L17 O Projection, Residual/Norm, or MLP semantic defect was demonstrated. No full GSM8K rerun or production source change.

## Artifacts

- Original component run: `/data/sglang-hicache/gemma4/runs/20261028T174357Z-g1-l17-fullattn-components/` (L5/L11/L17 and initial HF replays).
- Exact Q/K/V and kernel metadata run: `/data/sglang-hicache/gemma4/runs/20261028T182819Z-g1-l17-attn-closure/`; validated machine-readable results are in `same-operand-attention-summary.json`, and FP64 per-backend errors in `fp64-reference-comparison.json`. Counterfactual RIDs/Forward UUIDs, IDs/positions and captures are bound in `counterfactual/bound-counterfactual-forwards.json`; impact metrics are in `counterfactual/counterfactual-impact-summary.json`. These runs bind model identity and exact inputs; replacement is validated by effective-output bitwise equality to its Eager candidate.
- HF direct CUDA replays: `hf-cuda-l17-n512.pt`, `hf-cuda-l17-n514.pt` in the original component run directory.
- Existing bound layer-output/HF references and earlier PLE evidence are cited in `G1-PLE-MARLIN-EQUIVALENCE-20261028.md`.
- GPU returned idle; server exited and lock released. The final O Projection/Residual/MLP computations ran on CPU with official HF dequantized weights; no GPU recapture was performed.
