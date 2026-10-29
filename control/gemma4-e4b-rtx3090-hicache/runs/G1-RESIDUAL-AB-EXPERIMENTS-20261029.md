# G1 residual/RMSNorm A/B — evidence closure

**Ruling: Residual/RMSNorm rounding — NOT SUPPORTED AS G1 ROOT CAUSE. No production change adopted. G1 remains FAILED / NOT ACCEPTED.** No guard, Oracle, threshold, or production default path was changed. No further GPU experiment for this rounding hypothesis is authorized or needed.

## N512 matched service A/B

Run: `/data/sglang-hicache/gemma4/runs/20261029T162424Z-residual-rounding-ab-n512-r3/`; full captured tensor artifacts remain local at this path.

| Arm | RID | Forward UUID | Validator | artifacts |
|---|---|---|---|---:|
| A | `a759456a27634a8c9c6b5979448780cd` | `0d7182ddd3ef4095a43e97f6f5c489cc` | COMPLETE | 45/45 |
| B | `9badb54902f14eb69c3558219d59c668` | `e460414e465c4424869accda1b2a9ad5` | COMPLETE | 45/45 |

Both manifests bind the pinned checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb` and model SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Recomputed SHA-256 for every validator-listed artifact in each arm matched all 45 recorded hashes.

Frozen Oracle: `/data/sglang-hicache/gemma4/runs/20261022T065916Z-e5m2-swa-boundary/oracle-layers-n512.pt`, SHA-256 `d00532f370fbbbf4300ddba5077eac1037668c57a50ffddee9e12eb10bb6ea59`. Comparator confirmed exact frozen IDs and positions `1..512`; no oracle regeneration/substitution. Comparator output SHA-256 `1e5d98bbf693410f3b3afb16e35a70a6e1a144fa21c011421b2d7a299570c845` (`comparison-n512.json`).

First A/B difference is at layer 0. A-vs-B full-vocabulary logits: max abs `5.48422`, mean abs `1.87279`, RMSE `2.01697`, rel-L2 `0.673603`; service Top-1 remains 107 in both arms, HF CPU Oracle Top-1 236761. Relative errors against the frozen Oracle (A/B): aligned decoder output layer 0 `0.005257/0.005049`; layer 40 `0.048384/0.049311`; FinalNorm `0.112149/0.111471`; logits `0.214216/0.490851`. B worsens final-logit agreement substantially and changes no greedy token.

## N514 matched service A/B

Run: `/data/sglang-hicache/gemma4/runs/20261029T163639Z-residual-rounding-ab-n514/`; full captured tensor artifacts remain local at this path.

| Arm | RID | Forward UUID | Validator | artifacts |
|---|---|---|---|---:|
| A | `b6f70f95a2f34346a778ec3b080414c7` | `08adf890f8ee4d2fad4f53f22682bdd1` | COMPLETE | 45/45 |
| B | `4fa405da10374e6582fe402a26bf603b` | `fa7b73086b4248bcbf1451e98e254afe` | COMPLETE | 45/45 |

Both manifests bind the same pinned checkpoint revision and model SHA as above. Recomputed SHA-256 for every validator-listed artifact in each arm matched all 45 recorded hashes.

Frozen Oracle: `/data/sglang-hicache/gemma4/runs/20261022T065916Z-e5m2-swa-boundary/oracle-layers-n514.pt`, SHA-256 `1582c75bcbc9b69a490e41438ccb44fe969a9495019d2843d3a03017fe66d3d3`. Comparator confirmed exact frozen IDs and positions `1..514`; no oracle regeneration/substitution. Comparator output SHA-256 `f4e4884673002afc9cef8693da0ed9c184a17a30c3c3a42adf660ce435ea5ccd` (`comparison-n514.json`).

First A/B difference is at layer 0. A-vs-B full-vocabulary logits: max abs `1.45520`, mean abs `0.436694`, RMSE `0.477190`, rel-L2 `0.0989345`; service Top-1 remains 236761 in both arms, HF CPU Oracle Top-1 527. Relative errors against the frozen Oracle (A/B): aligned decoder output layer 0 `0.005292/0.005129`; layer 40 `0.027624/0.034170`; FinalNorm `0.076931/0.090689`; logits `0.129414/0.074537`. B improves final-logit rel-L2 but worsens FinalNorm and layer-40 error, and does not change the incorrect greedy token. This mixed result does not support rounding as the G1 root cause.

## Boundary and artifact interpretation

HF Transformers 5 capture semantics: hidden_states h1–h41 map to decoder layer outputs 0–40; h42 is post-FinalNorm. The frozen Oracle does not provide an independent layer-41 pre-FinalNorm hidden state. The comparator therefore omits that unavailable layer-41 comparison and does not compare SGLang prenorm to an unrelated HF boundary. FinalNorm and logits are checked against their actual HF output references. Per-layer metrics for every available aligned boundary and all A/B logits metrics are in the two local comparison JSON files cited above.

## GSM8K context (not causal attribution)

Existing doc8 same-history SGLang captures at `/data/sglang-hicache/gemma4/runs/20261027T-gsm8k-first-divergence/` show Eager and Graph both consume the shared token `236743` at decode step 2, absolute position 1110, and predict `236800`; full-vocabulary logits agree in Top-1 and margin. This does not establish cross-engine logit equality or link the residual A/B change to GSM8K quality. No new GPU run was performed for this closure.

## Disposition and hashes

**Residual/RMSNorm rounding — NOT SUPPORTED AS G1 ROOT CAUSE; no production modification.** G1 stays **FAILED / NOT ACCEPTED**. Source tensor captures, per-artifact hashes and full comparison JSON remain local at the two run paths; only this lightweight evidence report is intended for Git. N512/N514 capture hashes are preserved in each arm's `verified-capture.json`; all were independently recomputed and matched. GPU was cleaned after the runs (0% utilization, 1 MiB reported memory; no experiment service remained).
