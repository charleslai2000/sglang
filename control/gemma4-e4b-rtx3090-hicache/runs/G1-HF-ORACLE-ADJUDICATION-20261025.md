# HF Oracle adjudication — 2026-10-25

## Ruling
The existing N=512/514 CPU HF Logits Guard is **not a backend-matched production-correctness oracle** for RTX3090 SGLang. Keep its frozen rows **FAILED** as an unresolved cross-implementation discrepancy; do not relax tolerance, change SGLang math, or declare a broad correctness PASS. The evidence does not prove the HF implementation wrong or a production semantic defect. Supported classification: **numerical discrepancy without demonstrated production-semantic error**.

## Controlled HF rerun
Transformers 5.12.1, PyTorch 2.13.0+cu129, checkpoint SHA-256 `19d89d2a…fe0c5d`, exact frozen N=512/514 IDs and positions `1..N`, BF16 weights, Eager attention; compare full-vocabulary final-position logits for `use_cache=False/True`:

| N | CPU cache-mode rel-L2 / max-abs | CUDA cache-mode rel-L2 / max-abs | Shared KV shapes (SWA, Full) |
|---|---:|---:|---|
| 512 | 0 / 0 | 0 / 0 | `[1,2,512,256]`, `[1,2,512,512]` |
| 514 | 0 / 0 | 0 / 0 | `[1,2,514,256]`, `[1,2,514,512]` |

`past_key_values` exists only with cache enabled; shared states are returned both ways. CPU-vs-CUDA HF Eager differs: rel-L2 **.151008 (N512)** and **.073112 (N514)**. Greedy is CPU 107 vs CUDA 236761 at N512; both choose 527 at N514, but top-10 differs. Thus cache omission is not the cause (the original Oracle used `use_cache=False`, positions 1..N), but CPU and GPU arithmetic materially differ.

Against existing BF16 SGLang logits:

| N | SGLang vs CPU HF rel-L2 | SGLang vs CUDA HF rel-L2 | greedy (SGLang / CPU / CUDA) |
|---|---:|---:|---|
| 512 | .140989 | .238353 | 107 / 107 / 236761 |
| 514 | .238613 | .261462 | 236761 / 527 / 527 |

CUDA HF is not uniformly closer. The identity of the “correct” backend cannot be inferred by closeness or greedy selection. Full metrics, top-10, and logits are saved in `/data/sglang-hicache/gemma4/runs/hf-oracle-audit-20261025/{cpu-eager.pt,cuda-eager.pt,cpu-gpu-sglang-comparison.pt}`. Driver: `runs/hf_oracle_cache_audit.py`.

## Implementation facts and limits
- Installed Gemma4 source SHA-256 `90bb5dbd…f96b776` contains the #45312 Shared-KV fix: shared layers always read `shared_kv_states[self.layer_type]`, even with a Cache, because sliding cache may not retain full history. Same-input cache-mode parity was observed; neither proves SGLang semantic equivalence.
- Gemma4 constructs separate Full and sliding causal masks via Transformers masking utilities. The dynamic SWA cache returns the full current prefill KV states to attention while retaining only the most recent window for later calls; N512/514 shared SWA tensors have full sequence length. Exact materialized mask tensors were not serialized; source/metadata inspection cannot exclude different numerical realization.
- Checkpoint config SHA-256 `7f0cd2d1…9c893d3`, format `pack-quantized`, compressed-tensors W4 groupwise symmetric INT, 4-bit, group size 32. `run_compressed` is absent from the checkpoint JSON; Transformers default is True for compressed models. Its loader packs the model and, with `run_compressed=True`, does not take the post-load decompression path. CPU/CUDA HF execution is compressed-tensors QAT; observed parameters/model compute are BF16, and LM head is BF16. Exact effective-weight parity to SGLang Marlin was not established.
- HF uses Eager attention and compressed-tensors execution; SGLang uses Triton attention and W4A16 Marlin. Device/backend accumulation differences are material even inside HF. Same IDs, positions, cache mode, and final-logit boundary do not make these arithmetic implementations equivalent.
- Official and Fork RTX3090 service full-vocabulary rows are elementwise identical at N=8/512/514 under matched service conditions. This supports their pairwise parity only. Both differ from HF; no HF result is deemed correct merely because it is closer.

## Independent IFEval scorer
No evaluation rerun. Replaying stored outputs with the independent scorer reproduces exactly one discrepancy per arm: BF16 sample key 3456 (all-caps instruction) and E5M2 key 1122 (all-lowercase instruction). Both invoke `langdetect.detect()` after case checks; the installed DetectorFactory seed defaults to None and the same stored response changed result during replay. This establishes scorer nondeterminism/context sensitivity, not output change. Harness vs independent totals remain BF16 439/438 and E5M2 444/443. Preserve both and disclose scorer instability; IFEval is complete and independent of this logits ruling.

## Recommendation
Keep N512/N514 guard status FAILED and the frozen threshold unchanged. Label it a **cross-backend numerical diagnostic / unresolved**, not proof of production semantic incorrectness and not acceptance. Oracle promotion requires agreed effective-weight/quantization parity, exact mask contract and matched CUDA arithmetic/backend, plus owner-approved numerical contract. No production math edit is justified. G1 remains ACTIVE / NOT ACCEPTED.
