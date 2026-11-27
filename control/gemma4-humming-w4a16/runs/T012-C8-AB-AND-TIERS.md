# T012 — original C-8 L1-only A/B and three-tier validation

**Both gates PASS.** With the CT-loader + Humming post-load branch enabled, the original
C-8 L1-only workload improves by **+12.71% mean output TPS** (two repetitions,
+12.63% / +12.79%), and the production three-tier HiCache stack improves by **+8.90%**
with identical tier activity and payloads. Weight identity and correctness were
established separately in `T012-CTLOADER-HUMMING-QUALIFICATION.md`.

Source: frozen commit for the run is `872bfe1d55` (the opt-in branch committed together
with its qualification evidence). The gate-off arm differs only by the absence of
`SGLANG_CTWNA16_HUMMING=1`; no `--quantization` override, no FA2, no prefill graph, and
no audit instrumentation is present in any of these cells.

## C-8 L1-only A/B

Frozen L1-only argv (`20261127T-t011-l1only-off2/launch-argv.txt`): context 131072,
mem-fraction .94, FP8-E5M2 KV, Triton attention, decode CUDA graph bs≤32, chunked
prefill 4096, HiCache disabled. Workload: 40 clients × 20 rounds, 1024 in / 256 out,
Poisson rate 8, seed 42, 800 requests, `--fixed-history-tokens`, request-hash log.

| cell | TPS | Extend s | Decode s | bench s | TTFT s | ITL s | duty | completed |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Marlin (off) | 653.89 | 168.02 | 142.60 | 313.20 | 3.837 | 0.0399 | 99.17% | 800/800, 0 failed |
| Humming r1 | 736.49 | 156.00 | 120.08 | 278.08 | 3.143 | 0.0388 | 99.27% | 800/800, 0 failed |
| Humming r2 | 737.51 | 155.74 | 120.02 | 277.69 | 3.067 | 0.0387 | 99.28% | 800/800, 0 failed |

- TPS gain **+12.63% / +12.79%**, mean **+12.71%** (repetitions differ by 0.14%).
- Decode device time **−15.8%**, Extend device time **−7.2%**, TTFT −0.7/−0.77 s.
- All three cells logged the identical 800-request payload multiset (sorted request
  hashes), so the comparison is over the same work.
- KV capacity: `max_total_num_tokens` 1,488,985 (Marlin) vs 1,486,169 (Humming) in the
  qualification pair, −0.19%, from Humming's padded repack footprint (weights +20 MB).
  It does not bind on this workload (32 × 32K ≪ 1.48M tokens).
- The control's 653.89 TPS is 1.1% below the 661.27 recorded for the T011 control on
  frozen `371521fc99`; the gain above is measured against this session's own control.

## Three-tier validation (conditional gate)

Production C-8 acceptance argv kept intact: `--enable-hierarchical-cache --hicache-size 8
--hicache-write-policy write_back --hicache-io-backend kernel --hicache-mem-layout
page_first --hicache-host-memory-mode cache --hicache-storage-backend extent`
(64 MiB extents, 32 GiB file) `--hicache-storage-prefetch-policy wait_complete`, chunk
4096. Same workload as above.

| cell | TPS | bench s | completed | L1 cached tokens | L2 backup tokens | extent events | max_total_num_tokens | SWA tokens |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Marlin (off) | 570.65 | 358.89 | 800/800, 0 failed | 9,533,440 | 1,763,808 | 5,570 | 1,441,580 | 65,536 |
| Humming (on) | 621.42 | 329.57 | 800/800, 0 failed | 9,533,440 | 1,763,841 | 5,504 | 1,443,628 | 65,536 |

- **+8.90%** TPS, −29.3 s bench, identical prompt token total (10,547,201) and identical
  L1 cached tokens; L2 backup volume and extent-tier activity are the same order in both
  arms, so the host and extent tiers are exercised under Humming exactly as under Marlin.
- Capacity is not reduced (full-pool metric +0.14%, SWA identical); payload multiset
  identical.
- Duty falls 89.2% → 87.4% because the same idle time buys more work per second.

## Decision

Humming clears correctness, weight-identity, capacity and both performance gates, so the
opt-in implementation is retained. It stays behind `SGLANG_CTWNA16_HUMMING` (default
off), so the production launch must export `SGLANG_CTWNA16_HUMMING=1` to obtain the gain;
the frozen argv, the model, the checkpoint, the tier configuration and Marlin remain
untouched for every other model and for a fallback.

Reproducing these numbers requires the argv files recorded in each cell's
`launch-argv.txt` plus the env flag; the drivers are `run_ab.sh` / `compare_ab.py` and
`run_tiers.sh` / `compare_tiers.py` in this directory.

## Artifacts

Raw run directories (full server logs, per-request metrics, GPU samples, extent caches):
`/data/sglang-hicache/gemma4/runs/20261127T-t012-ab/{c8-off,c8-on1,c8-on2}` and
`/data/sglang-hicache/gemma4/runs/20261127T-t012-tiers/{tiers-off,tiers-on}` (the ~21 GB
L3 extent files were deleted after the run; the extents are a reproducible cache).

In-repo evidence: `evidence/<cell>/{official-summary.txt,official-summary.json,
launch-argv.txt,manifest.txt,exit.txt,bench-exit.txt,client-wall.txt,hashes.jsonl}`
(plus `metrics-at-end.prom` for the tier cells), `ab-verdict.json`, `compare.log`,
`tiers-verdict.json`, `tiers-compare.log`, `ab-status.txt`, `tiers-status.txt`.

Run windows: A/B 11:32:19–11:58:38Z, tiers 12:05:28–12:24:35Z, 2026-11-27. All cells
finished with wrapper exit 0; GPU returned to idle (1 MiB / 0%), ports 31401 released,
`/tmp/f1-r16b-gpu-exclusive.lock` free.
