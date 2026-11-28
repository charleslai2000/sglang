# Gemma4 E4B on RTX 3090 — optimised serving configuration (archive)

Annotated tag: `gemma4-e4b-3090-optimized-v1.0` (this commit). All numbers below are the
accepted results on that exact source, measured on the frozen benchmark workloads; the
reports named at the end carry the per-cell evidence.

## 1. What to run

Checkpoint `/data/sglang-hicache/gemma4/model` (NVFP4/GPTQ W4A16 weights, unchanged), AOT
kernel package `/data/sglang-hicache/aot-sm86-package` (SM86), `fp8_e5m2` KV cache, Triton
attention backend with the two opt-in accelerations enabled at launch time:

```bash
export SGLANG_CTWNA16_HUMMING=1              # CT-Loader + Humming W4A16 post-load conversion (default off)
export SGLANG_FA2_RAGGED_EXTEND=1            # FlashInfer FA2 for Full-layer extend (default off)
export SGLANG_T011_BF16_PREFIX_BUDGET_MB=128 # transient prefix budget; default is 32 MB, ceiling 128 MiB
```

The third export is not cosmetic: the sub-batch group size is derived from it
(`budget / per-token BF16 K+V bytes`), so at the 32 MB default each group holds only
8 192 tokens and most multi-request Forwards fall back to Triton. The accepted numbers
were measured with 128.

Everything else stays at the frozen argv. Exact command lines as launched, per workload:

| workload | argv snapshot (in this repository) |
| --- | --- |
| C-8 L1-only (no HiCache tiers) | `control/gemma4-t015-fa2-subbatch/runs/cells/c8-fa2-r1/launch-argv.txt` |
| C-8 three-tier HiCache | `control/gemma4-t015-fa2-subbatch/runs/cells/tiers-fa2-r1/launch-argv.txt` |

Both are the production argv verbatim (model path, `--context-length 131072`,
`--max-running-requests 32`, `--mem-fraction-static .94`, `--kv-cache-dtype fp8_e5m2`,
`--attention-backend triton`, `--cuda-graph-backend-decode full`,
`--cuda-graph-max-bs-decode 32`, `--chunked-prefill-size 4096`, `--skip-server-warmup`,
plus the HiCache/extent flags for the three-tier case); only `--port` and the
metrics-export directory differ per measurement cell. Prefill CUDA Graph stays disabled.

## 2. Accepted performance

| workload | result | note |
| --- | ---: | --- |
| C-8 L1-only, 800 requests | **788.10 output TPS** | mean of two repeats 784.03 / 792.17 (Triton arm on the same source: 744.10) |
| C-8 three-tier HiCache, same payload multiset | **657.38 output TPS** | Triton arm: 632.84 |
| Long context, three-tier (T010 workload) | **138.40 output TPS** | Triton arm: 116.62 |
| Full KV pool | **1 443 628 tokens** | `fp8_e5m2`, K 5.51 GB + V 5.51 GB |
| SWA KV pool | **65 536 tokens** | `fp8_e5m2`, K 0.63 GB + V 0.63 GB |

KV capacity is identical in both arms of every cell (`available_gpu_mem=1.07 GB` at
start), and payload multisets are identical across arms (sha1 digests `3215cb6df740e8b1`
for C-8/three-tier, `4d2dbd2da6a8ff23` for long context).

Accelerations packaged in this tag:

- **Humming W4A16** (T012): CT Loader + post-load conversion keeps the checkpoint's
  quantised values and scales exactly (253/253 layer parameter hashes identical) and
  replaces the Marlin decode/prefill GEMM path; opt-in, default off.
- **FA2 ragged extend with bounded sub-batch** (T013 + T015): Full-layer extend attention
  runs on FlashInfer FA2 with Forward-level plan reuse; a Forward whose total prefix
  exceeds the transient budget is partitioned into consecutive bounded groups instead of
  falling back to Triton, so FA2 covers 100 % of Full-layer extends (decode attention,
  SWA layers and the sampler are untouched).

## 3. Benchmark workloads (for reproduction)

- C-8: `benchmark/hicache/bench_multiturn.py`, 40 clients, 20 rounds, 1 024 input /
  256 output, Poisson rate 8, max parallel 64, seed 42, 800 requests, ShareGPT V3.
- Long context: 96 clients, 6 rounds, 5 000 input / 256 output, 576 requests.
- Harness: `control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh`
  (frozen argv, GPU lock, per-cell manifests); cell driver
  `control/gemma4-t015-fa2-subbatch/runs/run_cell.sh`, comparison
  `.../t015_compare.py`.

## 4. Evidence map

| topic | report |
| --- | --- |
| Stage baseline, scheduling and harness | `control/gemma4-rtx3090-throughput-scheduling/runs/T007-C8-BASELINE-AND-CHUNK4096.md`, `T007-L1L2-20261125.md`, `T007-ROUND3-GAPS-AND-FIXES-20261125.md`, `T007-SYNC-PYTHON-AND-STEADY-C32-20261126.md`, `T009-C8-R5-R6-20261126.md`, `T009-PREFILL-CUDA-GRAPH-20261126.md` |
| Hardware profile (whole-GPU + operator budget) | `control/gemma4-rtx3090-throughput-scheduling/runs/T010-GPU-HARDWARE-PROFILING-20261127.md`, `T010-LONG-CONTEXT-TIERS-20261126.md` |
| FA2 extent coverage review (desk review, no run) | `control/gemma4-rtx3090-throughput-scheduling/runs/T011-ATTENTION-REVIEW.md` |
| Full-extend FA2 development | `control/gemma4-t011-full-extend/runs/T011-FULL-EXTEND-FA2-QUALIFICATION.md`, `T011-BF16-RAGGED-QUALIFICATION.md`, `T011-FORWARD-PLAN-REUSE-QUALIFICATION.md` |
| Humming W4A16 qualification and A/B | `control/gemma4-humming-w4a16/runs/T012-CTLOADER-HUMMING-QUALIFICATION.md`, `T012-C8-AB-AND-TIERS.md`, `T012-SHAPE-COMPATIBILITY-AND-BENCHMARK.md` |
| Opt-in merge acceptance (Humming + FA2) | `control/gemma4-t013-opt-merge/runs/T013-MERGE-ACCEPTANCE.md` |
| GPU hardware profiling of both arms | `control/gemma4-t014-hwprof/runs/T014-HW-PROFILING.md` |
| FA2 bounded ragged sub-batch | `control/gemma4-t015-fa2-subbatch/runs/T015-FA2-SUBBATCH.md` |

Raw per-cell artefacts, profiler databases and extents are outside Git
(`/data/sglang-hicache/gemma4/runs/…`); each report names its directory, and
`control/gemma4-t015-fa2-subbatch/runs/RAW-EVIDENCE.txt` indexes the T015 ones.

## 5. Known limits recorded in the reports

- Whole-GPU DRAM/SM-issue percentages from nsys need root on this driver and are marked
  NOT COLLECTED (T014).
- Per-kernel counters are only available through the standalone NCU driver, not inside
  the serving process (T014).
- A single request whose own prefix exceeds 128 MiB still falls back to Triton (T015);
  the workload never produces one.
- Group gathers are per (Full layer, group); measured net is still positive (T015).
