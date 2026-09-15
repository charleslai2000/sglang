# Performance Baseline Specification v2 — P0 telemetry normative erratum

**Status:** normative erratum to v2; the original v2 Markdown, JSON, and hashes
remain immutable. No GPU, server, workload, or performance rerun is authorized.

**Binding:** `P0-TELEMETRY-EXPERT-GATE-20260914.json` and its recorded hash are
the controlling telemetry contract for this erratum.

## Cache prompt conservation

The v2 cache equation is corrected to the exclusive partition:

```text
C = L1_tokens + L2_tokens + L3_tokens
newly_prefilled_tokens = prompt_tokens - C
prompt_tokens = L1_tokens + L2_tokens + L3_tokens + newly_prefilled_tokens
```

The four source components are non-negative, mutually exclusive, and must sum
exactly to `prompt_tokens`. `L2_tokens` excludes L3-restored positions. Mamba
slots and auxiliary native units are not part of this equation. Negative or
oversummed inputs are `tier_nonconservation` and invalid; they must not be
clamped into a valid record.

The normative contract key is `cache_prompt_conservation`.

## Cache optimization opportunity

`avoidable_recompute_tokens` is a separate derived subset, not a conservation
source:

```text
avoidable_recompute_tokens =
  max(0, min(prompt_tokens, durable_reusable_prefix_tokens) - C)
```

It is emitted only when durable prefix authority is proven, and must satisfy
`0 <= avoidable_recompute_tokens <= newly_prefilled_tokens`. Otherwise it is
`null`. It must not be added to prompt tokens, actual prefill tokens, source
counter sums, or throughput denominators. The normative contract key is
`cache_optimization_opportunity`.

## Telemetry binding

The controller assigns `prefetch_issue_mono_ns` exactly once immediately before
queue publication. Positive L3 matched-prefix credit requires same-lineage,
attempt, generation, prompt-lineage, and complete-component proof; otherwise
the durable fields are `null`/unknown. Prometheus uses the four conservation
sources only, with avoidable recompute in its separately named counter. JSONL
uses `outcome=complete|partial|invalid` with the fixed reason/null semantics
from the Expert Gate. Telemetry derivation and observation failures are
best-effort and cannot affect serving.

This erratum changes no prior raw run and does not rewrite the v2 artifacts.
