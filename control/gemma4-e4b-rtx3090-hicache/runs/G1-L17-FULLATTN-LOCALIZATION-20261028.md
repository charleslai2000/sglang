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
- Comparing HF eager replay's attention-head output with SGLang Triton output gives rel-L2 `.003587` (N512) / `.003439` (N514), max abs `.03125`. This is **not** a same-Q/K/V direct attention-kernel comparison: HF replay uses its own decompressed QKV weights and numerics, and component capture does not include SGLang's post-RoPE q/k operands, actual kernel mask/index buffers, O-projection output, or SGLang residual-add intermediate. Therefore this delta cannot distinguish upstream QKV/RoPE/mask propagation from an attention-kernel difference. The attempt to recompute HF RoPE on the captured SGLang pre-RoPE Q/K did not pass shape validation against HF's consumed `[B,H,N,D]` tensors; no numerical result is claimed from it.
- Subsequent HF replay boundaries (post-attention norm, pre-FFN norm, MLP, post-FFN norm and PLE branches) were captured, but their differences likewise include upstream QKV/attention output differences. They do not prove the first erroneous production operation.

## Disposition and next decisive evidence

No confirmed Full Attention defect. The first confirmed same-input arithmetic delta in the L17 path is the small W4A16 QKV Linear output difference (~`1e-4` rel-L2) against HF dequantized CUDA Linear; the Marlin effective-weight semantics are already validated, so this is backend arithmetic absent contrary evidence. It is not established as the cause of the L16→L17 error growth. Attention output is the first *layer boundary* with the larger residual, but causal attribution remains unresolved.

To close the requested operator attribution, a follow-up must capture SGLang post-RoPE Q/K operands and actual Triton causal/mask/index parameters for the bound Forward, then run a same-Q/K/V/positions/mask CUDA comparison against HF/independent causal attention; compare O projection on the same head output and capture residual/MLP/PLE additions separately. Do not call the current `.0034–.0036` output delta an attention semantic defect. No guard tolerance changed, no full GSM8K rerun, no production source changed.

## Artifacts

- SGLang run `/data/sglang-hicache/gemma4/runs/20261028T174357Z-g1-l17-fullattn-components/` (`bound-forwards.json`, request/RID/UUID-bound component JSONs for L5/L11/L17, layer outputs and server log).
- HF direct CUDA replays: `hf-cuda-l17-n512.pt`, `hf-cuda-l17-n514.pt` in the same run directory.
- Existing bound layer-output/HF references and earlier PLE evidence are cited in `G1-PLE-MARLIN-EQUIVALENCE-20261028.md`.
- GPU after run: `0%`, `1 MiB`; server exited; lock released.
