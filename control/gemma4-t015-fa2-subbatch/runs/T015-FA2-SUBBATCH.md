# T015 — FA2 Bounded Ragged Sub-batch

| | |
| --- | --- |
| Baseline | `c1feed4d21` (T014), T012/T013 results preserved |
| Change | `python/sglang/srt/layers/attention/bf16_ragged_extend.py` (+group split, group plans, group gather, group merge), `triton_backend.py` (dispatch branch) |
| Scope honoured | no scheduler change, no new memory budget, no Humming change, no new kernel |
| Arm definitions | A = Marlin + Triton, B = Humming + FA2 (now with sub-batch), both `SGLANG_CTWNA16_HUMMING=1`, B adds `SGLANG_FA2_RAGGED_EXTEND=1` |

## 1. Premise check (required before implementation)

Existing FA2 fallback counters from the T013 C-8 / three-tier / long cells and the T014
service window:

| run | attempts | plans | skip_no_prefix | skip_over_budget | over-budget share of skips | max prefix / budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T013 c8-fa2-r5 | 367 | 256 | 27 | 84 | 75.7 % | 2.55× |
| T013 c8-fa2-r6 | 261 | 192 | 29 | 40 | 58.0 % | 1.85× |
| T013 long-fa2-r2 | 1533 | 1408 | 25 | 100 | 80.0 % | 1.73× |
| T013 tiers-fa2-r3 | 288 | 128 | 26 | 134 | 83.8 % | 2.84× |
| T014 tiers-fa2 | 191 | 128 | 24 | 39 | 61.9 % | 1.70× |

Over-budget skips are the majority of all skips in every run, and the rejected
forwards are up to 2.8× the budget. To check the *splittability* premise a run-scoped
diagnostic recorded every rejected forward's shape during a fresh three-tier cell
(`cells/tiers-fa2-coverage1`, budget 128 MiB, 353 plan attempts: 192 plans +
29 no-prefix + 132 over-budget):

| quantity | min | median | max |
| --- | ---: | ---: | ---: |
| requests per forward | 3 | 4 | 4 |
| total prefix tokens | 33 024 | 59 904 | 95 232 |
| largest single-request prefix | 8 704 | 17 664 | 24 576 |
| groups needed (⌈ total / 32 768 ⌉) | 2 | 2 | 3 |
| transient bytes needed | 135 MB | 245 MB | 390 MB |

**132 of 132** rejected forwards had every single request inside one 32 768-token
group (largest single request 24 576 tokens), and none needed more than 3 groups.
The ceiling — not the per-request size — was rejecting them, so implementation
proceeded. Group-count histogram of those forwards: 2 groups 81×, 3 groups 51×.

## 2. Design as implemented

1. **Partition.** `_partition_groups` walks the batch in order and closes a group when
   adding the next request would exceed `max_group_tokens()` (= budget ÷ per-token
   BF16 K+V bytes = 32 768 tokens at a 128 MiB budget). Requests are never split,
   never reordered, so a group is a contiguous request range.
2. **Plan.** `plan_forward` builds one prefix plan per group at forward level (one
   FlashInfer wrapper each; they share the existing 8 MiB split-KV workspace, which is
   disabled). The extend plan stays one whole-batch causal plan, exactly as before.
   All Full layers of the forward reuse these plans; nothing is planned in the layer
   path.
3. **Run.** `run_layer_subbatched` runs the causal extend attention once for the whole
   batch, then for each group gathers that group's prefix into the shared transient
   pair, runs the group's non-causal prefix attention, and merges that group's partial
   state with the extend state of *exactly its own Q rows* (`merge_state`, same log2
   LSE domain). Because groups are contiguous row ranges, the original Q order is
   reconstructed by contiguous writes.
4. **Fallback.** A single request whose own prefix exceeds the budget still rejects the
   whole forward (`skip_request_over_budget`), i.e. the previous Triton fallback. No
   partially covered batch is ever produced.
5. **Unchanged path.** With one group the plan tensors, wrapper and kernels are the
   T013 ones, so every accepted single-group result keeps applying bit for bit.

## 3. Numeric equivalence

`runs/t015_subbatch_glue_check.py` drives the module's own `plan_forward` +
`run_layer`/`run_layer_subbatched` on a synthetic batch with real FP8 pool tensors and
compares the grouped output against an ungrouped reference plan over the same batch.

| case | partition (requests → prefix tokens) | max abs diff | bitwise equal |
| --- | --- | ---: | --- |
| 4 × 15 360 tokens (61 440 total) | [0,2) 30 720 + [2,4) 30 720 | 0.0 | yes |
| 4 × 9 000 tokens (36 000 total) | [0,3) 27 000 + [3,4) 9 000 | 0.0 | yes |
| 5 × 8 192 tokens (40 960 total) | [0,4) 32 768 (exactly the cap) + [4,5) 8 192 | 0.0 | yes |
| 8 × 12 288 tokens (98 304 total) | 4 × 24 576 | 0.0 | yes |
| 1 × 40 000 + 1 × 1 000 tokens | rejected: `plan_is_none`, Triton fallback | — | as designed |

Per-request max abs diff is 0.0 for every request in every case, against reference
amplitudes of 0.068–0.076 (the synthetic output scale). The diff is zero, not merely
small, because each group runs the same kernel over the same rows and the merge is a
per-row operation. Raw artefacts: `runs/probe/glue-*.json`.

## 4. Net benefit on real over-budget forwards

Measured with the T014 offline driver (production ModelRunner, pools, graphs; the
measured forward repeated 3–4×):

| shape (previously rejected) | Triton | FA2 sub-batch | delta |
| --- | ---: | ---: | ---: |
| 4 requests × 12 288 prefix + 1 024 extend (49 152 prefix tokens, 2 groups) | 615.45 ms | 549.95 ms | **−10.6 %** |
| 2 requests × 12 288 prefix + 1 024 extend (24 576 tokens, fits: 1 group) | 321.46 ms | 284.35 ms | −11.6 % |

The second row is the control: shapes that were already covered keep their T013 gain,
so the sub-batch branch does not disturb the accepted path.

## 5. Service acceptance

Frozen argv, frozen benchmark workload (40 clients, 20 rounds, 1 024/256, rate 8,
max 64) for C-8 and three-tier; T010 long-context workload (96 clients, 6 rounds,
5 000/256) for the long cells. Identical payload multisets within each workload
across both arms (sha1 digests: C-8 and three-tier `3215cb6df740e8b1`, long
`4d2dbd2da6a8ff23`), KV capacity byte-identical: full 1 443 628 tokens +
SWA 65 536, `available_gpu_mem=1.07 GB` at start in both arms.

| workload | A Triton | B FA2 sub-batch | delta | T013 accepted (A → B) |
| --- | ---: | ---: | ---: | --- |
| C-8 L1-only | 744.10 | 784.03 / 792.17 | **+5.37 % / +6.46 %** | 737.55 → 760.17 (+3.07 %) |
| three-tier HiCache | 632.84 | 657.38 | **+3.88 %** | 624.85 → 644.21 (+3.10 %) |
| long context (T010) | 116.62 | 138.40 | **+18.68 %** | 116.51 → 135.22 (+16.06 %) |

Coverage change (same workload, same budget):

| cell | plans | skip_over_budget | sub-batch plans | groups | peak VRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| tiers before (diagnostic cell, T015 premise run) | 192 | 132 | — | — | 23 996 MiB |
| tiers after | 320 | **0** | 122 | 344 | 23 996 MiB |
| C-8 after r1 / r2 | 384 / 384 | **0 / 0** | 108 / 109 | 290 / 292 | 24 124 MiB |
| C-8 Triton reference | — | — | — | — | 24 100 MiB |
| long before (T013 long-fa2-r2) | 1408 | 100 | — | — | — |
| long after | 1536 | **0** | 114 | 228 | — |

The `tiers-fa2-coverage1` row is the premise/diagnostic run of the *pre-change*
module (extra per-forward sample capture enabled); its 612.78 TPS is not comparable
with the timed cells and is quoted only for the coverage counters.

The transient peak stays inside the existing budget: the scratch pair is one group
(≤ 32 768 tokens ≈ 128 MiB), reused sequentially by every group of every layer, so the
observed peak grows by 24 MiB versus Triton and remains below the pre-change FA2 bound.

## 6. Three-tier cache contract

Same procedure as T013 (`runs/restore/run_restore.sh` primes the extent with a fresh
process, `run_restore4.sh` — T013's final-verdict script, only the source/port paths
changed — then restores it in one fresh process per arm and reads the
`restore_disposition` line). Both arms, T015 code, 10 305-token prompt:

| arm | disposition | restored cached tokens | extent reads |
| --- | --- | ---: | ---: |
| Triton | `RESTORE requested=10304 granted=10304 reason=full` | 10 304 | 11 |
| FA2 sub-batch | `RESTORE requested=10304 granted=10304 reason=full` | 10 304 | 11 |

`full_restore_both_arms=true`, `verdict=PASS`; greedy `target` and all four `short`
completions are byte-identical between the arms (`target_text_equal=true`,
`short_text_equal=true`). The cache tier contract is therefore unaffected by the
sub-batch change.

## 7. Limitations

- Group gathers are per (layer, group), so a multi-group forward gathers its full prefix
  once per Full layer (7×) instead of once per KV owner (4×). The measured net is still
  positive (−10.6 %), and the extra copy stays inside the same transient budget.
- The offline driver cannot exercise 3-group forwards (its SWA pool caps a single
  process at ~65 k resident prefix tokens); 3-group splits are covered by the module
  equivalence check (up to 4 groups) and by the service cells, where the 122 sub-batch
  forwards of the three-tier cell used 344 groups (2.8 per forward).
- A single request above the budget is out of scope by the fixed plan and still falls
  back to Triton.

## 8. Decision

Keep the sub-batch change with the existing opt-in (no new switch). It converts 100 % of
the over-budget skips on all three loads into covered forwards, costs one extra gather
per (Full layer, group) and no extra VRAM budget, and improves the accepted FA2 arm on
every load (C-8 +5.4/+6.5 % versus Triton today, three-tier +3.9 %, long +18.7 %). The
deployment recommendation still needs the launch-time exports, all of them default off or
below the measured value:

```bash
export SGLANG_CTWNA16_HUMMING=1
export SGLANG_FA2_RAGGED_EXTEND=1
export SGLANG_T011_BF16_PREFIX_BUDGET_MB=128   # default 32 MB; group cap is budget-derived
```

See `control/gemma4-e4b-3090-archive/DEPLOYMENT.md` for the archived configuration.
