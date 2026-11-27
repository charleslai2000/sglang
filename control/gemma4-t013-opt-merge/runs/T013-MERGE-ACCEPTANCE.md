# T013 — merge acceptance of the existing GPU optimisations

**Outcome: both opt-ins retained; the Humming + FA2 combination is the better one on all three
workloads.** Baseline `7ed79dab11` (T012 close-out). No new algorithm, no telemetry framework, no
scheduling change: the only new production code is the archived T011 FA2 module installed verbatim
plus its call-site glue behind an independent flag.

## 1. What was merged

| piece | location | default |
|---|---|---|
| FA2 BF16 ragged Full extend with one plan per Forward (T011 accepted candidate, verbatim, 441 lines) | `python/sglang/srt/layers/attention/bf16_ragged_extend.py` | imported but inert |
| opt-in switch `SGLANG_FA2_RAGGED_EXTEND` | `python/sglang/srt/environ.py` | **off** |
| call-site glue: one plan per prefill Forward, per-layer run, every fallback gate | `python/sglang/srt/layers/attention/triton_backend.py` (+155 lines) | inert while the flag is off |
| Humming post-load switch (unchanged from T012) | `SGLANG_CTWNA16_HUMMING` | off |

The glue is deliberately narrow. A plan is built once per prefill `Forward`, on the first Full layer
that is statically eligible, from that Forward's authoritative host lengths; every later Full layer
of the same Forward reuses it and nothing re-plans or reads indptr inside the layer path. The path
runs only for `ForwardMode.EXTEND`, non-cross-attention causal layers with `qk_head_dim == v_head_dim
== 512`, TP-local head counts equal to the backend's, no sliding window, no custom mask, no
`score_mod`, no sinks, no XAI temperature, `page_size == 1`, no unified-pool translate hook, no DCP
and no deterministic mode. Anything else — including the four sliding-window layers and decode —
stays on the unchanged Triton/Marlin code. Decode, SWA, KV capacity, cache policy and the scheduler
are untouched; the FA2 path only replaces the extend attention call for the seven Full layers.

**Defect found and fixed during acceptance (recorded, not hidden).** The first glue draft set the
"planned for this Forward" flag on the first extend layer, which in Gemma4 is a sliding-window layer,
so no Forward ever built a plan: the flag was inert and the first measurement round measured two
identical Triton configurations. The engagement check caught it (no plan, no coverage counters), a
call-level probe localised it (`plan=False` at the first Full layer), and the fix moves the attempt
onto the first *statically eligible* Full layer. Round-1 cells are kept under
`runs/20261127T-combo/cells-pregate/` marked superseded; every number below is from the fixed source
and each FA2 cell reports its own coverage counters.

## 2. Combination results (same argv, flag is the only difference)

Model, checkpoint, request load, KV capacity and cache configuration are fixed. `A` = Humming +
Triton, `B` = Humming + FA2. Frozen C-8 argv; the three-tier cells use the production HiCache stack
(`L1+L2+extent`, `write_back`, `wait_complete`, chunk 4096); the long-context cells use the T010 load
(96 clients × 6 rounds × 5000-token turns, 256 out, Poisson 8, max-parallel 64, 36.5K final context).

| workload | cell | TPS | extend device s | decode device s | bench s | TTFT s | ITL s | duty | completed |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| C-8 L1-only | A r1 | 735.92 | 155.9 | 120.3 | 278.3 | 3.125 | 0.0388 | 99.25% | 800/800 |
| C-8 L1-only | A r2 | 739.17 | 155.6 | 119.5 | 277.1 | 3.057 | 0.0386 | 99.27% | 800/800 |
| C-8 L1-only | **B r1** | **760.48** | 147.4 | 119.7 | 269.3 | 2.992 | 0.0374 | 99.18% | 800/800 |
| C-8 L1-only | **B r2** | **759.87** | 147.6 | 120.0 | 269.5 | 3.003 | 0.0375 | 99.29% | 800/800 |
| three-tier | A | 624.85 | 168.5 | 119.9 | 327.8 | 4.260 | 0.0409 | 87.98% | 800/800 |
| three-tier | **B** | **644.21** | 160.3 | 120.3 | 317.9 | 5.100 | 0.0315 | 88.26% | 800/800 |
| long-context | A | 116.51 | 1073.9 | 104.6 | 1265.7 | 93.99 | 0.1426 | 93.12% | 576/576 |
| long-context | **B** | **135.22** | 908.7 | 104.4 | 1090.5 | 79.12 | 0.1215 | 92.91% | 576/576 |

| workload | A → B TPS | gain | extend device | repetitions |
|---|---:|---:|---:|---|
| C-8 L1-only | 737.55 → 760.17 | **+3.07%** (+3.34% / +2.80%) | −5.4% | two per arm, FA2 reps 0.08% apart |
| three-tier | 624.85 → 644.21 | **+3.10%** | −4.9% | one per arm (arm spread 0.4%) |
| long-context | 116.51 → 135.22 | **+16.06%** | −15.4% | one per arm (arm spread 0.9%) |

The gains come from the extend path only: decode device time is unchanged (120.3 → 119.7 s,
119.9 → 120.3 s, 104.6 → 104.4 s). The long-context cell gains most because every turn re-prefills a
long cached prefix, which is exactly the work the ragged prefix attention replaces; TTFT drops by
15 s and the same 576 requests finish 175 s sooner.

Every cell logged the identical payload multiset (800 or 576 request hashes), so the arms do the same
work. Each FA2 cell also reports its own coverage counters, which is what makes the deltas
attributable rather than inferred:

| FA2 cell | plans | no-prefix skips | over-budget skips | owner conversions | shared-KV reuses | max requested prefix |
|---|---:|---:|---:|---:|---:|---:|
| C-8 L1-only r1 | 256 | 27 | 84 | 1020 | 765 | 341.8 MB |
| C-8 L1-only r2 | 192 | 29 | 40 | 764 | 573 | 248.5 MB |
| three-tier | 128 | 26 | 134 | 508 | 381 | 381.7 MB |
| long-context | 1408 | 25 | 100 | 5628 | 4221 | 232.5 MB |

The skips are the module's own 128 MiB transient-prefix ceiling: a Forward whose whole prefix would
need more than that keeps Triton, so the measured gain is a lower bound on what the path would give
without the memory cap. Owner conversions are amortised across shared-KV consumers exactly as
designed (7 Full layers = 4 owners + 3 reuses per Forward).

## 3. Resources, CUDA Graph and capacity

| workload | KV tokens (A / B) | SWA tokens | peak GPU mem (A / B) | decode graph replay counter (A / B) |
|---|---|---|---:|---|
| C-8 L1-only | 1,443,628 / 1,443,628 | 65,536 / 65,536 | 24,098 / 24,124 MiB | 7,165 / 7,179 |
| three-tier | 1,443,628 / 1,443,628 | 65,536 / 65,536 | 23,982 / 24,102 MiB | 7,094 / 7,251 |
| long-context | 1,443,628 / 1,443,628 | 65,536 / 65,536 | 23,798 / 23,896 MiB | 6,770 / 6,728 |

* **KV capacity is byte-identical** between combos in every workload, so the merge costs no cache
  capacity. FA2's own footprint is the 8 MiB FlashInfer scratch plus at most one 128 MiB transient
  prefix pair, visible as +26/+120/+98 MiB peak and still inside the 24,576 MiB device.
* **Decode CUDA Graph** is captured and replayed in every cell (`Capture target decode CUDA graph
  end` plus the replay counter above), because the path is gated to `ForwardMode.EXTEND` and never
  runs inside a replayed decode graph.
* No OOM, no retraction spike, no failed request anywhere; duty is unchanged between arms on all
  three workloads.

## 4. Numerical correctness and real L3 restore

* Reused evidence, unchanged by this merge: T011 operator/integration checks (BF16 ragged
  prefix+extend+`merge_state` against the production Triton kernel, log2 LSE semantics) and T012's
  weight-identity proof (253/253 Text Core WNA16 layers with identical packed INT4 words and BF16
  scales, converted-GEMM error 2.4–3.7% of output mean, Humming running inside the replayed graph).
* New glue check on the restored source (`runs/t013_fa2_glue_check.py`,
  `runs/20261127T-glue/result.json`): one plan per Forward, plan identity unchanged across all
  seven Full layers, all seven engaged, four owner conversions reused by three shared-KV consumers,
  max |Δ| against the production Triton kernel **9.16e-4** (the same figure T011 reported), and every
  fallback gate holds (flag off, decode mode, no prefix, over budget, sliding window, head geometry,
  custom mask all return without planning or running).
* New combo-level numerics and **real L3 restore** (`runs/20261127T-restore2/`,
  `runs/t013_restore_roundtrip.py`, `runs/t013_restore_text.py`): a fresh extent tier is
  primed by a 10,305-token greedy request under `write_through`, then a **new process** is
  started on the same extent directory with empty device and host tiers and asked for the
  identical prompt. In both combinations the lookup resolves to the extent tier:
  `disposition=RESTORE requested=10304 granted=10304 reason=full`, `cached_tokens=10304` of
  `prompt_tokens=10305`, 11 extent reads, and the greedy completion is identical between the
  Triton and FA2 arms on the restored prefix as well as on four short prompts. That is the
  contract that matters for the merge: a prefix rebuilt from the durable tier and then
  attended by either backend produces the same tokens.
  A separate same-process probe (`runs/20261127T-restore/` and `runs/20261127T-restore2/`) additionally showed the expected
  host-tier behaviour under eviction pressure (`prefetch_revoke storage_hit=0`,
  `restore_recompute cause=miss`, `final_storage_survivability=host`) with identical greedy
  output in both arms — the same workload T010 documented as "L3 delivers nothing at C-8
  scale", unchanged by this merge.

## 5. Decision

| combination | verdict |
|---|---|
| A — Humming + Triton | baseline, unchanged, still the default |
| **B — Humming + FA2** | **retained**: +3.07% C-8 L1-only, +3.10% three-tier, +16.06% long-context, identical capacity, identical payloads, decode graph intact, correctness verified |

Both switches stay independent and default off, so nothing changes for any other model or for a
fallback. For the production deployment the recommended launch env is
`SGLANG_CTWNA16_HUMMING=1 SGLANG_FA2_RAGGED_EXTEND=1` with the frozen C-8/tier argv unchanged; the
gain is largest for long-context traffic and is bounded below by the 128 MiB transient ceiling on
short-context bursts. Raising that ceiling is not part of this merge (the module treats 128 MiB as a
hard limit and the frozen `--mem-fraction-static .94` leaves little headroom).

What is *not* retained or reopened: the T011 FA2 direction stays closed as a *C-8-only* optimisation
(it was +1.71% there on Marlin and failed its ≥5% gate); the earlier T011-specific measurement is
superseded by this merge, which shows the same code paying off at +3% on C-8 with Humming and +16% on
the long-context load. Prefill CUDA graph stays disabled, and no FA2 variant is enabled for any other
model or dtype.

## 6. Reproduce

```
# scored cells (A then B), one workload at a time
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh c8    triton r5
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh c8    fa2    r5
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh tiers triton r3
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh tiers fa2    r3
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh long  triton r2
bash control/gemma4-t013-opt-merge/runs/20261127T-combo/run_combo.sh long  fa2    r2
python3 control/gemma4-t013-opt-merge/runs/20261127T-combo/compare_combos.py \
  control/gemma4-t013-opt-merge/runs/20261127T-combo
# correctness / restore
bash control/gemma4-t013-opt-merge/runs/20261127T-restore/run_restore.sh
```

## 7. Artifacts

In-repo: `runs/t013_fa2_glue_check.py`, `runs/t013_restore_probe.py`,
`runs/t013_restore_roundtrip.py`, `runs/t013_restore_text.py`,
`runs/20261127T-glue/{result.json,glue.log}`, `runs/20261127T-engage/` (engagement evidence),
`runs/20261127T-combo/{run_combo.sh,run_all.sh,run_followup.sh,run_round2.sh,run_round3.sh,
compare_combos.py,combo-verdict.json,combo-compare.txt,combo-status.txt,cell-intent.txt}`,
per-cell evidence under `runs/20261127T-combo/evidence/<cell>/` (official summary, launch argv,
manifest, request-hash log, end-state metrics, FA2 coverage counters), `runs/20261127T-restore/`
(host-tier eviction probe), `runs/20261127T-restore2/{restore2,restore4}/` with the round-trip
verdicts and the `disposition=RESTORE` lines.

Raw cell directories (full server logs, GPU samples, benchmark logs) are archived under
`/data/sglang-hicache/gemma4/runs/20261127T-t013-combo/`, together with `cells-pregate/` — the
superseded pre-fix round kept for traceability. The L3 extent bytes and per-request metric logs were
dropped because they are reproducible. Scored cells: `c8-{triton,fa2}-r5/r6`,
`tiers-{triton,fa2}-r3`, `long-{triton,fa2}-r2`.
