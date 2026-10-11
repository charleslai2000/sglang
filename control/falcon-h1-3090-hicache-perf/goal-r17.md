# R17 — Falcon/3090 throughput, cache KPI, and optimization

## Current status
R17-METRICS remains incomplete and is not accepted. Current evidence, invalidations, and precise gaps are recorded in `runs/R17-20261012T0100Z/R17-METRICS-STATUS.md`. Do not interpret aggregate Host backup as Host restoration; L3 remains `NOT_QUALIFIED`.

## Goal
On the accepted Falcon GPTQ-Int4 / RTX 3090 baseline, determine the effective high-concurrency saturation region, use scheduler-context profiles to justify and A/B one optimization, and measure actual multi-turn Host-cache value. Any final performance decision must jointly consider output throughput and latency, not TPS alone.

## Frozen boundary
- Model `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; one exclusive RTX 3090.
- Start at pushed `3090-24g-hicache` commit `6f612b0301416157e48fc5e40ac01680bc212b3c` (contains R16C `a5895b5d1`); isolated worktree `/tmp/sglang-r17`.
- Preserve accepted R16B random results and R16C parameter-match/profile artifacts; do not repeat them. Do not use sibling opt tree or original dirty worktree. Do not include unverified R15 changes.
- Existing L2 correctness qualification remains valid; L3 lifecycle is not qualified and is not a blocker for GPU-only/L2 performance. Mark all L3 hit/recovery performance `NOT_QUALIFIED` unless the lifecycle gate changes under separate scope.
- No cache semantics or speculative runtime changes merely to generate hits.

## Core KPI contract
Every compared run reports p50/p95/p99 TTFT, p50/p95/p99 TPOT, output TPS, input/prefill TPS, request RPS, end-to-end p50/p95/p99 and request count/errors, actual scheduler running batch and queue distributions, and VRAM. Cache KPIs include token-weighted total and per-tier hit rates `sum(tier hit tokens)/sum(prompt tokens)` for L1 Device, L2 Host, L3 Disk, plus newly-prefilled tokens and conservation checks. Report logical lookups separately from successful restored tokens. Report successful Host→Device and Disk→Host bytes and transfer latency; if counters expose only aggregate writes rather than matched-operation bytes, label attribution `UNKNOWN`. Cold and warm phases are distinct. Report TTFT by cold/warm and cache-tier hit class where sample sizes permit; do not infer causation from aggregate correlation. L3: `NOT_QUALIFIED`.

A candidate is an overall improvement only if throughput is non-regressed and latency/KPI tradeoffs are explicit and accepted; no TPS-only pass.

## Completion
- Fixed, hashed token-ID workloads. Saturation sweep c=1/4/8/12/16/20/24, >=5 requests per offered concurrency, >=3 independent runs at key points. Requested and actual effective concurrency reported separately; no run classified by client limit alone.
- Separate Prefill and Decode rates/tails and valid scheduler-context c8 and saturation-point CUDA traces. Quantify profiling perturbation; profiler traces do not supply clean throughput.
- At least one profiler-evidence-driven optimization hypothesis A/B against unchanged baseline, or a documented no-patch decision if no low-risk change has credible predicted benefit. Any failed/no-gain candidate is reverted/excluded.
- Real multi-turn GPU-only vs GPU+Host comparison using existing `bench_multiturn.py`/cache-hit kit or a minimal corrected reuse path, with a frozen identical manifest and truthful cache-tier logical-hit/recovered-token/bytes/latency evidence. Zero Host hit => workload does not exercise Host benefit. L3 `NOT_QUALIFIED`.
- Correctness regression relevant to the selected optimization; report/plan/task/frontier updated; scoped commit(s) pushed; no GPU/service residue or dirty R17 changes.

## Non-goals
- Do not re-run R16B accepted cases or claim exact G002 replay (historical prompts/harness are unavailable).
- Do not repair L3 in this Goal or bulk-import sibling changes.
