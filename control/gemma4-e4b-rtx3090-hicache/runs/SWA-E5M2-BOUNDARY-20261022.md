# Gemma4 E5M2 vs BF16 around SWA window — 2026-10-22

Real matched raw-token completions through the actual SGLang service; E5M2 and BF16 used identical deterministic input token arrays, `temperature=0`, `max_tokens=1`, `--disable-radix-cache`, context/total-token budgets 4096, and independent Forward UUIDs. Checkpoint identity is pinned to revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, model SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. E5M2 KV physically allocated as `torch.float8_e5m2` in full and SWA pools; decode graph bs1 capture completed. First-run artifacts are under `/data/sglang-hicache/gemma4/runs/20261022T052139Z-e5m2-swa-boundary/`; the all-layer rerun is `/data/sglang-hicache/gemma4/runs/20261022T065916Z-e5m2-swa-boundary/`.

## Boundary measurements

The clean all-layer rerun reproduces the prior 510–514 logits and greedy results exactly; the numbers below are from the completed 06:59 UTC actual GPU run.

| tokens | E5M2 vs BF16 max abs | mean abs | RMSE | rel L2 | service BF16 greedy | service E5M2 greedy | HF BF16 greedy |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 510 | 1.27176 | 0.195739 | 0.246427 | 0.06298 | 131865 | 131865 | 131865 |
| 511 | 1.60192 | 0.215992 | 0.270837 | 0.07690 | 568 | 568 | 568 |
| 512 | 1.54066 | 0.253036 | 0.318876 | 0.10202 | 107 | 107 | 236761 |
| 513 | 1.56911 | 0.213881 | 0.271078 | 0.08479 | 204064 | **238247** | 204064 |
| 514 | 1.66400 | 0.363550 | 0.424178 | 0.09837 | 236761 | 236761 | 527 |

A service E5M2/BF16 greedy divergence is observed at 513; the short-prompt 8-token diagnostic cannot qualify this SWA/long-context behavior. All five exact prompt arrays have independent BF16 HF oracle logits captured at identical text positions 1..N in `oracle-n{N}.pt`; aggregate exact-input comparisons are in `oracle-comparison.json`. Service logits against HF Oracle (max abs / mean abs / RMSE / rel L2):

- N=510 BF16 relL2 .10564, E5M2 .11529; both greedies match.
- N=511 BF16 .05169, E5M2 .06927; both match.
- N=512 BF16 .20965, E5M2 .19835; service BF16 and E5M2 choose 107, but HF chooses 236761. This is a BF16/service-vs-HF discrepancy at the exact boundary; it is important and not explained by E5M2 quantization.
- N=513 BF16 .11739 and greedy matches HF token 204064; E5M2 .14437 chooses 238247 instead. HF BF16 logits for 204064 and 238247 tie exactly at 13.1875, and HF's deterministic argmax chooses lower ID 204064. SGLang BF16 also ties them exactly at 13.46727753 and chooses 204064. E5M2 shifts these scores to 13.36728001 and 13.46727753 respectively, producing a 0.09999752 pairwise lead for token 238247; its global top-2 margin is only 0.04995155 (next candidate 90296). This is consistent with an FP8 perturbation of an HF near-tie, but does not prove tolerance acceptance.
- N=514 BF16 .25989 and E5M2 .32647; both service modes choose 236761 while HF chooses 527. Thus the SGLang BF16 long-input reference itself does not consistently match HF at 512/514.

This is a real correctness gap; no overall tolerance has yet been frozen. Do not call 513 the sole failure or infer that every difference is legal quantization: the exact 512 and 514 comparisons reveal service-BF16/oracle disagreements too. The existing model's config says SWA window 512, 18 KV-shared layers beginning at layer 24. Layer types are sliding at 24–28 and 30–34, full at 29 and 35; the final shared full-attention layer 41 maps to owner layer 23 (nearest preceding full-attention layer), per HF and local `Gemma4Attention` logic. Exact config/layer inventory: `checkpoint-swa-sharedkv-inspection.json`.

## Per-layer output comparison

Full layer outputs for all 42 decoder layers at the last prompt position are recorded in the rerun and analyzed in `layer-error-analysis.json`. At N=513 E5M2-vs-BF16 relative-L2 peaks at layers 29–32: layer29 .04991 (max abs 1.78125), layer30 .05282 (1.40625), layer31 .05661 (1.5625), layer32 .04745 (1.296875). These are **shared layers** after layer 24; layer29/35/41 are full-attention, with owner 23, and layer30–32 are SWA-shared with owner 18. But the most elevated relative error does not occur uniquely at the window transition: at N=510 the peaks are also layers31 (.05765), 29 (.05288), 30 (.04812), 32 (.04571); N=511 similarly peaks at 29–32. N=512 and N=514 show lower errors in those layers, while the HF oracle discrepancy itself varies substantially. This pattern does not isolate a cache/scale defect. Layer-output capture measures residual outputs, not actual cache reads/writes; it cannot establish exact per-slot membership or scale application.

## Current finding and next decisive test

Exact-position HF hidden states are now compared against all 42 SGLang residual outputs for both dtypes, stored in `layer-oracle-analysis.json`. At N=513, BF16 per-layer rel-L2 is modest through the pre-shared region (layer23 .02350); shared layer24 .02046; shared layers29–32 .02834/.03252/.03140/.02756; E5M2 has the same early outputs through layer23 (as expected before the first FP8 cached-attention read) but grows to .06990/.07536/.08066/.06732 at shared layers29–32. This is compatible with quantization error accumulating through later shared layers, but does not prove the storage scale or window routing correct. At other lengths the layer-error pattern varies: N=510 BF16 already reaches rel-L2 .07265 at layer31, N=511 stays ≤.03087 through layer31, N=512 rises at full-attention layer35 to .04555 and N=514 is already .08055 at layer23. There is no fixed single-layer discontinuity common to lengths 510–514, so the evidence remains insufficient to label the 513 change an indexing/scale defect. The largest hidden-state residual at layer41 (rel-L2 about .91) is an artifact of comparing different output semantics: HF exposes a final-normalized model hidden state there, while the SGLang layer tap is before final RMSNorm; exclude layer41 from layer-boundary diagnosis. The full per-layer data now enables targeted follow-up without another broad source review.

A later audit found and fixed a Global proportional RoPE cache-layout defect, described in `G1-PROPORTIONAL-ROPE-20261022.md`. The exact HF Global/SWA operator tests now pass, but post-fix real GPU N512/514 logits remain mismatched (table and IDs in that report). Thus the original values above are pre-fix and historical, not acceptance data; E5M2/shared-KV root cause remains open. Next compare target N514 layer17 components to supported HF operation outputs, and continue owner-layer window/scale capture. Keep G1 NOT ACCEPTED until tolerances, long-context decode, graph numerical parity, API/cancellation/concurrency, stable performance and capacity ledger complete.

The earlier attempt at `/data/sglang-hicache/gemma4/runs/20261022T051559Z-e5m2-swa-boundary/` is invalid for full-prefix comparison because RadixCache reused 510 cached tokens and the later call captured only one suffix token. The corrected no-radix-cache runs above are authoritative. Graph capture at startup does not prove graph replay numerical parity.
