# T015 — FA2 bounded ragged sub-batch

Baseline `c1feed4d21`; T012 (Humming post-load) and T013 (FA2 opt-in + Humming switch)
results are preserved unchanged.

## Problem

The T013/T014 FA2 ragged Full-layer extend runs only when the **whole forward's**
prefix K/V pair fits the 128 MiB transient ceiling. Measured on the production C-8 and
three-tier workloads, that ceiling is the dominant reason FA2 covers a minority of
extend forwards: over-budget skips are 58–84 % of all skips, and the largest observed
forward needs ~2.8× the budget.

## Fixed plan (no deviation without evidence)

1. For a forward whose **total** prefix exceeds the budget while **every single
   request** stays inside it, partition the requests into consecutive groups of at
   most 32768 prefix tokens.
2. Each group's plan is built at forward level and reused by every Full layer;
   plans keep independent metadata and the transient buffers are reused sequentially.
3. Each group computes only its own prefix attention; the causal extend attention
   stays a single whole-batch computation; attention states are merged back into the
   original Q order.
4. A request that alone exceeds the budget keeps the existing whole-forward Triton
   fallback.

## Accepted constraints

- No scheduler change, no new memory budget (the per-forward transient peak stays
  ≤ the existing 128 MiB budget), no Humming re-optimisation, no new kernels.
- KV capacity, numeric semantics and the three-tier HiCache contract are preserved.
- Evidence first: if the fallback counters had not shown the budget as the main
  coverage limit, implementation would have stopped with a report.
