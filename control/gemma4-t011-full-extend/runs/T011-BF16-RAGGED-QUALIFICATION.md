# T011 Full Attention Extend — BF16 Ragged candidate (SM86)

Baseline for this continuation: `48e2ecffae981fedf55fdfc8db552eaeddd2be9a`; frozen production
source `a76206a5fbd65b81ddbb470ac8088a46cf78697a`. Model geometry is the runtime-converted one:
Full `head_dim=512`, Q/KV heads 8/2, SWA `head_dim=256`.

**Status: closed on measured end-to-end failure.** Operator-level speedup and FP32 agreement were
achieved, but the L1-only acceptance regressed (−13.6% TPS); no production change is retained.

Native FP8 FA2 (`Paged Prefix`) was closed earlier: FlashInfer 0.6.17 only builds the one-byte
large-head variant for SM100+ (`No supported CUDA architectures found for major versions [10,11,12]`),
so the FP8 path cannot run on RTX 3090. See `T011-FULL-EXTEND-FA2-QUALIFICATION.md`.

## Candidate as measured

`python/sglang/srt/layers/attention/bf16_ragged_extend.py` (new module) +
`TritonAttnBackend._try_t011_bf16_ragged_full_extend` (opt-in gate):

* FP8 E5M2 pool stays authoritative; the live prefix slots are gathered by index and converted to a
  transient BF16 K/V pair, chunked (4096 tokens) so only a small FP8 staging buffer is added.
* Two FlashInfer FA2 **BF16** ragged attentions: non-causal over the gathered prefix, causal over the
  original-precision new K/V, then `merge_state`.
* LSE stays in FlashInfer's log2 domain through the merge (kernel writes `log2(d)+m`; `merge_state`
  consumes the same domain). Only oracle comparisons convert by `ln(2)`.
* Temporary BF16 prefix **hard cap 128 MiB** (`2 * total_prefix * kv_heads * 512 * 2`), enforced
  before any allocation; 64 MiB FlashInfer workspace; no resident BF16 cache; no pool reduction.
* Gate: `SGLANG_ENABLE_T011_BF16_RAGGED_FULL_EXTEND` (default off), Full dim512 8/2, BF16 compute,
  FP8 E5M2 pool, eager (never during graph capture), no custom mask, no sliding window, DCP=1,
  non-shared K/V (shared-KV layers keep Triton), unit cache scales, total prefix ≤ 32768 tokens.

## Isolated operator results (RTX 3090, SM86)

Full path = gather + BF16 conversion + both plans + both attentions + merge + sync, versus the
complete production Triton extend.

| (new,prefix) | candidate | Triton | net reduction | FP32 oracle | vs Triton |
|---|---:|---:|---:|---:|---:|
| 4096 + 28672 | 39.90 ms | 69.49 ms | **42.6%** | 1.03e-5 | 1.5e-4 |
| 4096 + 12288 | 19.17 ms | 35.57 ms | **46.1%** | 1.41e-5 | 2.7e-4 |
| 1024 + 7168 | 4.12 ms | 5.65 ms | **27.1%** | 1.51e-5 | 2.7e-4 |
| unit-scale 4096 + 28672 | 40.01 ms | 69.56 ms | **42.5%** | 8.0e-6 | — |

Plan cost alone is ~0.40–0.57 ms per forward and is included above. Measured incremental device
allocation for the longest case was 218 MB peak (BF16 prefix 112 MiB + FP8 staging + FlashInfer
workspace + merge temporaries).

Artifacts: `runs/20261127T-bf16-ragged-r1..r6/`, driver `runs/t011_bf16_ragged_operator.py`.
r1–r4 used a wrong synthetic `sm_scale=1/sqrt(512)`; r5 also mis-split the cache descale. Those rows
are superseded by r6 (production `scaling=1`, prefix-only descale) and the integrated-module run.

## Integrated-module and glue validation

`runs/20261127T-bf16-ragged-r7` exercises the shipped module against Triton and FP32:

| case | net reduction | FP32 oracle | vs Triton |
|---|---:|---:|---:|
| 4096 + 28672 | 40.8% | 8.8e-6 | 1.4e-4 |
| ragged batch [1024,2048,512] / [700,300,1500] | 20.8% | 6.4e-5 | 8.4e-4 |
| 1024 + 7168 | 19.2% | 1.7e-5 | 2.7e-4 |

`runs/20261127T-bf16-ragged-r8` calls the real backend method unbound against a stand-in for `self`:
it engages for the dim-512 Full cases, and correctly falls back for zero prefix, a 33000-token
prefix (over the 128 MiB cap), shared-KV (`k=None`), sliding-window, non-unit `k_scale`, and the
disabled flag.

## L1-only acceptance (official C-8 protocol, same source)

Both cells used `t007_c8_profile.sh` with `HICACHE_MODE=off`, chunk 4096, window 0, baseline argv
from `20261126T-t009-c8-acceptance-r8`, 40 clients x 20 rounds, 1024-in/256-out, Poisson seed 42,
max-parallel 64, `--fixed-history-tokens`. Only difference: the candidate env flag.

| cell | TPS | bench s | duty | TTFT | ITL | decode s | extend s |
|---|---:|---:|---:|---:|---:|---:|---:|
| off (control) | **650.06** | 315.05 | 99.24% | 3.714 | 0.0407 | 143.13 | 169.53 |
| on (candidate) | 561.55 | 364.71 | 99.06% | 4.404 | 0.0473 | 142.21 | **219.05** |
| Δ | **−13.6%** | +15.8% | −0.18 pp | +18.6% | +16.0% | −0.6% | **+29.2%** |

Both cells completed 800/800 with 0 failures; decode time is unchanged, so the whole regression is
in the extend path. The candidate therefore **fails the L1-only acceptance**.

Operator measurements say the kernel path itself is not the problem — the same module is faster than
Triton on every shape tested, including C-8-scale prefixes (`runs/20261127T-bf16-ragged-r9`):

| (new,prefix) | candidate | Triton | net reduction |
|---|---:|---:|---:|
| 4096 + 9216 | 15.42 ms | 29.96 ms | 48.5% |
| 4096 + 16384 | 24.59 ms | 43.78 ms | 43.8% |

The regression is therefore attributed (inference from the measured split, not a profiler result) to
the per-forward, per-layer integration overhead that does not exist in the isolated loop:

* two `plan()` calls per Full layer per extend step. FlashInfer's `plan()` reads indptr metadata back
to host (`qo_indptr`/`kv_indptr`/last-page lengths) before scheduling, so each call is a blocking D2H
inside the scheduler's extend path — 7 Full layers x 2 wrappers = 14 readbacks per extend forward.
T007/T009 had already identified blocking synchronisation in this scheduler as the dominant idle
source, which matches adding ~50 s to the extend path while duty stays ~99%.
* the transient BF16 prefix pair is materialised per layer, so the FP8 pool is converted 7 times per
forward instead of being read in-kernel the way Triton does.

Measured allocation for the longest operator case was 218 MB incremental device memory (112 MiB BF16
prefix + FP8 staging + 64 MiB FlashInfer workspace + merge temporaries), inside the 128 MiB prefix cap
required by the task.

## Decision

**Candidate closed.** The operator-level win is real (27–48% on isolated shapes, FP32 oracle
1e-5 class), but it does not transfer to the frozen production workload: L1-only end-to-end is
−13.6% TPS with extend +29%. Per the task gate, no production integration is kept — `triton_backend.py`
is restored to the frozen source, the module is archived at `runs/archive/bf16_ragged_extend.py`, and
production behaviour is unchanged. No Decode, SWA, Marlin, KV capacity, quantization, scheduling or
cache-tier behaviour was modified at any point, and no FlashInfer architecture gate was overridden.

Residual option if this direction is ever revisited: remove the per-layer `plan()` readbacks (build
the prefix indptr from the already-present host lists and call the module plan directly) and/or
convert the prefix once per forward instead of once per layer. Neither was attempted here because it
exceeds the authorised candidate and the measured acceptance already fails.

## Scope notes

No Decode, SWA, Marlin, capacity, quantization, scheduling or cache-policy change. The Triton kernel
remains the unconditional fallback. Production behaviour is unchanged unless the environment flag is
set.
