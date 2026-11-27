# T011 Full Attention Extend plan

Status: DONE — BF16 Ragged candidate closed on measured end-to-end regression; production source restored.

## Established results

1. **Native FP8 FA2 is unsupported on the target.** FlashInfer 0.6.17 builds the one-byte large-head
   FA2 variant only for SM100+; RTX 3090 (SM86) fails at `paged.plan()` with
   `No supported CUDA architectures found for major versions [10, 11, 12]`. No gate override.

2. **Runtime geometry is Full `head_dim=512`, Q/KV 8/2, SWA 256.** The earlier "head_dim=256" stop
   used the unconverted source config and is superseded.

3. **BF16 Ragged candidate works at the operator level.** FP8-index gather + transient BF16 prefix,
   two bf16 ragged attentions and `merge_state` (log2 LSE kept through the merge) beat complete Triton
   extend by 27–48% on every isolated shape, with FP32 oracle error ~1e-5 and 112 MiB prefix memory
   (inside the 128 MiB cap). Evidence: `runs/T011-BF16-RAGGED-QUALIFICATION.md`,
   `runs/20261127T-bf16-ragged-r1..r9/`.

4. **It does not transfer to the frozen workload.** Official C-8 L1-only A/B on the same source:
   650.06 TPS control vs 561.55 TPS with the candidate (−13.6%), extend 169.5 s → 219.1 s (+29.2%),
   decode unchanged, 800/800 both cells. The isolated loop still shows −48.5% at 4096+9216, so the
   loss is per-forward/per-layer integration overhead (two blocking `plan()` readbacks per Full layer
   plus per-layer prefix materialisation), not kernel throughput.

## Decision
Candidate closed; no production integration retained. `triton_backend.py` is back to the frozen
source; the module is archived at `runs/archive/bf16_ragged_extend.py` for the record. Decode, SWA,
Marlin, KV capacity, quantization, scheduling and cache tiers were never modified.

## Reopen condition
Only if the per-layer `plan()` readbacks and repeated prefix conversion are removed (build prefix
indptr from the host lists already present, convert once per forward) and a fresh L1-only A/B is
authorised. That is new scope, not a continuation of this task.
