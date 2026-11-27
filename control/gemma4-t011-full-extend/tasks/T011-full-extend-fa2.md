# T011 — Full Extend optimization (head_dim=512)

Status: DONE

## Work area
`python/sglang/srt/layers/attention/`, `python/sglang/kernels/ops/attention/`, `control/gemma4-t011-full-extend/`, durable run artifacts under `/data/sglang-hicache/gemma4/runs/`.

## Objective
At frozen production source `a76206a5fbd65b81ddbb470ac8088a46cf78697a` (continuation baseline
`48e2ecffae981fedf55fdfc8db552eaeddd2be9a`), improve only Gemma4 Full Attention Extend
(`head_dim=512`, GQA 8/2). Native FP8 FA2 was closed as SM86-unsupported; the authorised follow-up
was FlashInfer v0.6.17 BF16 large-head Ragged Attention over a transient BF16 prefix gathered from the
FP8 pool, with a 128 MiB temporary cap, no resident BF16 cache and no pool reduction. Integrate and
run L1-only acceptance only on clear net benefit; otherwise close without kernel rewrites.

## Completion
Qualify the operator against complete Triton extend including gather, conversion, planning, both
attentions, merge and memory, for 4096+28672 first and other shapes only after ≥20%. Verify outputs
against an FP32 oracle. If it passes, integrate Full Extend with Triton fallback preserved and run the
original C-8 L1-only acceptance. Report measured effects and source SHA; commit/push.

## Result
Closed. Operator qualification passed and was replicated on the shipped module
(4096+28672 −42.6%, 4096+12288 −46.1%, 1024+7168 −27.1%, 4096+9216 −48.5%, 4096+16384 −43.8%;
FP32 oracle error 8e-6–6e-5; 112 MiB BF16 prefix, 64 MiB workspace, 218 MB peak incremental
allocation; log2 LSE preserved through `merge_state`). Glue checks confirmed engagement on dim-512 Full
cases and correct fallback for zero/oversized prefix, shared-KV, sliding window, non-unit scales and
the disabled flag.

The opt-in integration was then measured end-to-end with the official C-8 L1-only protocol on the same
source: control **650.06 TPS** (extend 169.5 s, decode 143.1 s) versus candidate **561.55 TPS**
(extend 219.1 s, decode 142.2 s), i.e. **−13.6% TPS / +29.2% extend**, 800/800 in both cells. Since
the isolated operator is still 48.5% faster at C-8 prefix scale, the loss is integration overhead:
two blocking `plan()` metadata readbacks per Full layer per extend step, plus per-layer prefix
materialisation. Acceptance therefore fails and the candidate is closed.

Production source was restored (no changes under `python/`); the module is archived at
`runs/archive/bf16_ragged_extend.py`. Full evidence: `runs/T011-BF16-RAGGED-QUALIFICATION.md`,
`runs/20261127T-bf16-ragged-r1..r9/`, `/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-{off,on}`.

## Remaining
None. Reopening requires new scope: remove the per-layer plan readbacks and repeated conversion, then
re-run the L1-only A/B.
