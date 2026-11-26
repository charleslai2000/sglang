# T010 — Long-context three-tier cache performance

Status: ACTIVE (cells measured; the L3 restore contract is the identified largest loss, not yet fixed)
Objective: on the frozen stack (`e3beda6088`; Full/SWA capacity, 8 GiB host, concurrency 32,
chunk 4096, `write_back` + `wait_complete`, prefill graph disabled) quantify what each cache tier
is worth at ~32K context and remove the largest measured loss without rebuilding telemetry.
Completion: same-load L1-only vs three-tier comparison on a working set that genuinely exceeds
L1+L2, substantial and valid L2/L3 restores, and a verified optimisation of the dominant loss.

Result (2026-11-26):
- Workload: 96 clients × 6 rounds × 5,000-token turns (36.5K final context), 10,448,641 prompt
  tokens in both cells, working set 3.5M vs L1 1.44M + L2 0.877M.
- Cell B (L1 only): 78.66 TPS, 1874.5 s, duty 99.54%, 264,759 cached tokens (2.5%).
- Cell A (three tiers): **112.51 TPS, 1310.6 s (−30.1%), duty 93.36%**, L1 3,438,033 (32.9%),
  L2 687,524 (6.6%), **L3 0**, re-prefilled 6,323,084 (60.5%); extend 1107.1 s vs 1747.0 s
  (−640 s); D2H 7.34M tokens / 64.9 GB / 22.4 s; L3 writes 3.26M tokens.
- L3 restore never succeeds: 522 prefetch attempts → 436 `miss_reason=miss`, 77
  `PARTIAL requested=15511 granted=5000 reason=shortfall`, 723 extent reads, 0 tokens served.
  Diagnosis: the lookup requires a root-contiguous durable chain, and the partial path caps at one
  turn, so sessions whose older spans left L2 without a contiguous L3 chain restore nothing.
- Second loss: eviction 509.9 s of the 1107 s extend (4.27M evicted tokens, 1,232 passes).
- Reproduce: `runs/t010_compare_cells.py` over the two cell directories; report
  `runs/T010-LONG-CONTEXT-TIERS-20261126.md`.

Remaining:
- Implement anchor-based longest-durable-span restore (walk to the deepest durable ancestor, load
  from there, re-prefill only the tail), keeping the L2 correctness proofs and the per-layer
  `LayerDoneCounter` wait authoritative; then re-run both cells and the C-8 regression.
- Only after that, consider the eviction cost if it is still the second-largest item.
