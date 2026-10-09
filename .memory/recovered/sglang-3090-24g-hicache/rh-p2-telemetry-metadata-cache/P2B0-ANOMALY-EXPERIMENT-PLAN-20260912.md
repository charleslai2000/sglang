# P2-B0 severe-throughput-anomaly — experiment plan (for expert review)

```yaml
schema: phase2-hicache-anomaly-plan-1
artifact_id: P2B0-ANOMALY-EXPERIMENT-PLAN-20260912
task_id: P2-B0-ANOMALY-20260912
role: orchestrator (plan only; read-only diagnosis done)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
status: PLAN-FOR-REVIEW (no GPU experiment executed; profile changes require authorization)
```

## 0. Purpose and authority

User ruling 2026-09-12: single-digit aggTPS is a **severe performance anomaly**;
it must not be explained away as "long context / short output". This artifact is
the concrete experiment plan to localize the root cause. It is submitted for
expert review before execution. Everything in §1 is already-measured evidence
(read-only); everything in §3+ is proposed and NOT yet run.

## 1. What is established (measured, read-only)

### 1.1 The anomaly

RH-ON, same ~27.7K-token prompts and 32-token outputs:

| C | aggTPS | reqTPS | mean latency | TTFT mean | TTFT p95 | tftt mean |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 16.93 | 0.529 | 6.70 s | 4.70 s | 8.50 s | 2.00 s |
| 8 | 7.62 | 0.238 | **25.02 s** (max 129.9 s) | **21.66 s** | 81.4 s | 3.35 s |

Doubling offered concurrency **halves** throughput. Latency is ~3.7x worse at C8.

### 1.2 Root-cause candidate #1 — KV-pool capacity cap (structural)

- Live manifest: `max_total_tokens=65536`, `max_running_requests=8`,
  `kv_cache_dtype=fp8_e4m3`, `#tokens: 65536`, `K 0.50 GB + V 0.50 GB`.
- `Load weight end ... mem usage=3.84 GB`; `available_gpu_mem=15.26 GB`.
- One request holds ~27,744 tokens ⇒ **max resident = 65536 / 27744 = 2.36**.
  C4/C5/C6/C8 offer 1.69x/2.12x/2.54x/**3.39x** the pool.
- Confirmed by decode-batch `#running-req` histogram (on-c8):
  `0:109, 1:138, 2:29, 3:27, 4:7, 5:5, 6:3, 7:3, 8:1` ⇒ effective batch ~1.
- Prefill lines show `#queue-req: 6-7`, `#pending-token: 38-42k`.

**Implication:** the offered concurrency C is not real; requests serialize on a
~2-deep pool. `--max-total-tokens 65536` was frozen for the small P1/P2A
workload; the P2-B0 27.7K workload needs ~222K tokens at C8.

### 1.3 Root-cause candidate #2 — decode is ~10 tok/s single-stream

From server decode-batch lines (on-c8):

| #running-req | n | p50 gen throughput |
| --- | --- | --- |
| 1 | 17 | **7.64 tok/s** |
| 2 | 10 | 10.41 tok/s |
| 3 | 3 | 17.97 tok/s |

Client-side cross-check: `tftt_mean = 3.35 s` / 31 inter-token gaps ≈ 108 ms
/token ≈ 9.3 tok/s. For a 4B W4A16 model on a 3090 this is ~10x worse than a
memory-bandwidth-bound estimate (~5-15 ms/token).

### 1.4 Candidate #2b — CUDA graphs are DISABLED

Every batch line has `cuda graph: False` (322/322). Manifest:
`cuda_graph_config.decode.backend='disabled'`,
`cuda_graph_config.prefill.backend='disabled'`,
`cuda_graph_backend_decode='disabled'`, `cuda_graph_backend_prefill='disabled'`.
This is inherited from the frozen 3090 profile
(`launch-r112.sh`/`launch-e`/`launch-p2b0` all pass
`--cuda-graph-backend-decode disabled --cuda-graph-backend-prefill disabled`).

### 1.5 Candidate #3 — recompute/retraction

on-c8 event counts: `retraction_count` fields present, 3200 retract-matching
lines, `restore_recompute` 173, `restore_state` 7575, `restore_success` 112,
`MISS_RECOMPUTE` observed in `rh_match_prepare`. Per-request uncached prefill at
C8 = **7,618 tokens** (prompt 27,744 − device 5,602 − host 3,582 − storage
10,942). So "39 % from L3" is not the whole story; substantial tokens are
re-prefilled or restored-and-recomputed.

### 1.6 Execution config (for the counting baseline)

- GPU: RTX 3090 24G (UUID `GPU-2e3ed202-…`). Model: `Qwen3_5ForConditionalGeneration`,
  `quant=gptq, bits=4` → **gptq_marlin** kernel, bf16, non-SM90.
- Hybrid GDN: 24 linear-attention + 8 full-attention layers; GDN decode =
  **TritonGDNKernel**; `mamba_backend=triton`; `max_mamba_cache_size=53`.
- `max_prefill_tokens=16384`, `chunked_prefill_size=2048`,
  `schedule_policy=fcfs`, `page_size=1`, `enable_metrics=False`
  (so server-side `/metrics` token counters are unavailable unless enabled).

### 1.7 Rough latency budget at C8 (from measured pieces)

```
mean elapsed 25.0 s  =  TTFT 21.7 s            +  decode 3.35 s
TTFT 21.7 s          =  queue/serialization    +  L3->L2->L1 restore  +  prefill compute
prefill compute      ~= 7618 uncached / 5349 tok/s ~= 1.4 s
=> ~20 s of TTFT is NOT prefill compute (queue + restore + scheduling)
```

This must be **measured**, not inferred (§3).

## 2. Hypotheses

| ID | Hypothesis | Prior |
| --- | --- | --- |
| H1 | Effective concurrency is capped at ~2 by `max_total_tokens=65536`; the C4..C8 cells measure a saturated 2-deep queue, not real C-way concurrency. | strong (1.2) |
| H2 | Single-stream decode is ~10x too slow due to CUDA graphs disabled and/or the Triton GDN decode kernel path. | strong (1.3/1.4) |
| H3 | A large fraction of prompt tokens are re-prefilled/recomputed (restore fails, eviction, or retraction), inflating TTFT independent of compute speed. | medium (1.5) |
| H4 | CPU-side scheduling/launch overhead (overlap scheduler, detokenizer, per-token SSE, 200 ms sampler) contributes materially to inter-token latency. | weak-medium |

## 3. Experiment plan

Each experiment is one-variable, bounded, reversible, and uses the shared GPU
lock. Only E-A is executable under current authorization; E-B/E-C2 need the
profile-change decision in §5.

### E-A — Counting + config baseline (no profile change; authorized)

**Question:** is the reported TPS correct, and what is the true per-request
breakdown? **Method:**
1. Re-enable **server-side token counters** (`--enable-metrics` or equivalent)
   so TPS is computed from **actual completion tokens**
   (`realtime_tokens_total{mode="decode"}` delta), NOT SSE chunk count.
2. Re-run **one** cell (C8 RH-ON) and compute, per request:
   `prompt_tokens -> L1(device) -> L2(host) -> L3(storage) -> executed prefill
   tokens -> retraction_count -> repeated-prefill tokens`.
3. Denominator: measure window only — exclude seed build, warmup, inter-cell
   waits; **keep** real queueing and restore time.
4. Emit the four user-named metrics (`aggregate_output_tps`, `request_tps`,
   `effective_compute_tps`, `served_context_tps`).

**Deliverable:** corrected per-request accounting + `#running-req` histogram.
**Falsifies H1** if the running histogram shows a real C-way batch.

### E-B — Residency scaling (profile change; needs authorization)

**Question:** does throughput scale with real concurrency once the pool can hold
it? **Method:** raise `--max-total-tokens` so `C x 27.7K` fits:
`C8 -> 262144` (~3.9 GB, within the 15.26 GB free), `C4 -> 131072`. Keep
everything else frozen; also raise `--max-mamba-cache-size` only if it proves
binding (record actual vs nominal). Compare C4/C8 RH-ON/OFF against E-A's
baseline.

**Decision rule:** if aggTPS scales roughly linearly toward `C x` the
single-stream rate and latency drops to ~service time, **H1 is confirmed and
the pass-1 anomaly is a benchmark/profile-config artifact, not an engine
defect** (the engine was simply never given concurrency). If throughput stays
flat, the bottleneck is elsewhere (H2/H3/H4).

### E-C — Compute vs restore contrast (minimal pair)

**C1 (pure compute ceiling, no cache):** short prompts (~128 tokens, all
device-resident), C1 and C=supported, fixed output length. Measure TTFT,
inter-token latency, decode tok/s. This isolates model + kernel + launch
overhead with **zero** restore/queue.

**C2 (long-context L1 vs L3, same shape):**
- `C2a` a 27.7K-token request replayed a 2nd time in the same session (L1/L2
  hot, no L3 stage);
- `C2b` the same prompt cold / after eviction (L3 restore).
Same output length; report TTFT and decode separately.
**Decision rule:** if C2a is also ~10 tok/s, the slowness is **compute/kernel/
launch**, not restore. If C2a is fast and C2b slow, the cost is **restore**.

### E-C3 — CUDA graph on/off (one variable; needs authorization)

**Question:** how much of the decode gap is launch overhead? **Method:** re-run
E-C C1 with `--cuda-graph-backend-decode` enabled (and prefill as the control
variable). Report decode tok/s and correctness. **Caveat:** the frozen profile
disables graphs deliberately (possible hybrid-GDN/mamba incompatibility); this
is a **diagnostic to quantify the cost**, not an assumed fix. If graphs fail or
mis-compare for the hybrid model, record that as a finding.

### E-D — Short C8 trace (profiling)

Capture one short C8 window with SGLang's server-side profiler
(`/start_profile` … `/stop_profile`) plus the torch profiler / per-step timing.
Inspect: actual decode batch size, gptq_marlin + TritonGDNKernel time share,
CUDA graph presence, synchronous copies, gaps between forward passes.
**Explicitly do NOT** label `first->last token` as "pure kernel decode".

### E-E — Recompute accounting

Extend E-A's per-request join to quantify, per request, tokens served from each
tier vs tokens actually prefilled, and the count of repeated-prefill/retraction
episodes. Cross-check that "no `restore_recompute` event" does not hide
recompute after a PARTIAL restore (prior known trap).

## 4. How results map to the root cause

| Observed | Conclusion |
| --- | --- |
| E-B scales with pool; E-C C1 fast | anomaly = **benchmark config** (pool too small) + slow decode; fix the profile before any RH conclusions |
| E-B flat; E-C C1 also slow | **engine compute path** (graphs/kernels) — escalate to engine owners |
| E-C C2a fast, C2b slow | **restore/staging** cost dominated — RH-path optimization is correct target |
| E-C3 large delta | CUDA-graph-disable is a major, quantifiable cost — needs a decision on enabling graphs for this model |

## 5. Authorization / open decisions for the reviewer

1. **Raise `--max-total-tokens` (E-B):** it is a change to the frozen P0-C
   profile. Needed to test H1. Requested authorization.
2. **Toggle CUDA graphs (E-C3):** frozen profile disables them; needed to
   quantify the cost. Requested authorization (diagnostic only).
3. **Enable server metrics (`--enable-metrics`, E-A):** needed for
   token-accurate TPS. Low risk.
4. The pass-1 10-cell matrix is frozen as **valid but concurrency-uncontrolled**
   (it measured a capacity-saturated system). It is NOT the final scorecard.

## 6. Non-goals

- No RH benefit matrix expansion until the anomaly is localized (user rule).
- No product/test/code changes; no G1/G5 work in this phase.
- No conclusion about production performance from pass-1 numbers.

## 7. Bottom line (current, honest)

**Functional chain passed; end-to-end performance severely low; root cause not
yet localized.** Two measured structural facts dominate: the KV pool holds only
~2 of the 27.7K requests (so C4..C8 are not real concurrency), and single-stream
decode is ~10 tok/s with CUDA graphs disabled. RH 6.9 -> 7.6 TPS at C8 is a
local improvement and is NOT evidence the system is healthy.
