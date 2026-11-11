# QUASAR BF16 vs E5M2 KV A/B — 2026-11-11

## Scope and quality disposition

This is a descriptive matched service capacity/throughput comparison. No quality set was rerun. Frozen paired GSM8K evidence remains BF16 **1,091/1,319 (82.714%)** and E5M2 **1,098/1,319 (83.245%)**, delta **+7 items / +0.531 pp**, paired bootstrap 95% CI **[−0.834,+1.895] pp** (20,000 resamples, seed `20261106`). Because no applicable Owner threshold or product decision is recorded, E5M2 remains **NOT ACCEPTED**. See `experiments/g2-gsm8k-root-cause-20261107/postrope-e5m2-capacity-performance-20261111.md` and T006 for frozen quality artifact hashes and scorer details.

## Runtime and source identity

RTX3090, TP1, Gemma4 QUASAR GGUF SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`; BF16 compute; context 8192; `max_running_requests=16`; static memory fraction 0.88; chunked prefill 2048; Triton attention; prefill/decode CUDA graphs and Radix cache disabled; server seed 666360643. Only `--kv-cache-dtype` differs between the two A/B arms (`bf16` vs `fp8_e5m2`).

Both successful services use isolated Extend kernel overlay SHA-256 `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e`, Git blob `1e32f1eb41f5ba6aa9d576be364a4a98c6fd6e4f`, exactly equal to `HEAD:python/sglang/kernels/ops/attention/extend_attention.py`. The shared worktree copy is different (SHA-256 `168d7ac52da68c3bc396b54a38f5b0384def02b4494d730e784867087472bd94`) and was not modified. AOT `common_ops.abi3.so` SHA-256 `22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2` in both runs. Historical private-Extend overlay was not restored; this A/B says nothing about that distinct execution path.

Workload uses the existing E5M2 fixture copied byte-for-byte to both runs (fixture SHA-256 `2c1c415a60a3f64ecf32aed413ac152d7f189084e831ee0bce75704a342f1077`): 64 input IDs, forced 32 output tokens, c1/c4/c16, one warmup and three measured waves per concurrency. This exactly reuses the c1/c4/c16 requests from the existing E5M2 performance run; c8 is intentionally excluded. All measured calls returned exactly 32 IDs, with no HTTP/request failures in the valid runs.

## Allocated pool and practical concurrency

| KV dtype | Full slots | SWA slots | Free GPU memory after pool |
|---|---:|---:|---:|
| BF16 | 528,954 | 14,353 | 2.59 GB |
| E5M2 | 1,093,791 | 14,353 | 2.46 GB |

Pool slots are allocated token slots, not the number of simultaneous requests. At the tested request shape, both services actually admitted and completed each concurrent wave: c1 = 1, c4 = 4, c16 = 16 simultaneous requests; every request generated all 32 tokens. Thus c16 is the largest practical request concurrency demonstrated here, not a measured maximum/OOM boundary. At c16, pool slots alone are not a substitute for per-request context mix, Mamba state, allocator headroom, or scheduler admission.

E5M2 provides **2.068x Full slots** (+564,837, +106.8%) at the same setting; SWA slots are unchanged. Full KV slot count doubles while residual GPU memory differs by only 0.13 GB; do not interpret this as a pure dtype-only byte comparison without accounting for all pool/model/runtime allocations.

## Measured client aggregate output throughput

Three measured waves each, mean ± sample standard deviation, aggregate completed output tokens divided by concurrent-wave client wall time:

| Concurrency | BF16 tok/s | E5M2 tok/s | E5M2 relative to BF16 |
|---:|---:|---:|---:|
| 1 | 9.008 ± 0.031 | 8.329 ± 0.997 | −7.5% |
| 4 | 33.797 ± 0.165 | 33.733 ± 0.063 | −0.2% |
| 16 | 114.163 ± 0.295 | 114.371 ± 0.112 | +0.2% |

C1 E5M2 has a slower third wave (7.18 tok/s versus 8.87 and 8.94); its mean is sensitive to this one observation and should not be taken as an established c1 regression. c4 and c16 are close under this short synthetic workload. These are client wall-time aggregate rates, not decode-only throughput, confidence-qualified product benchmarks, or SLO claims.

## Retries, limits, and cleanup

- First BF16 invocation used a newly generated fixture different from the historical E5M2 workload; it also showed outlier c1/c4 waves, and the shell tool timed out at 600 seconds before summary/cleanup. It is **invalid and excluded**. The residual service was explicitly stopped; GPU returned to 1 MiB/0%, port was clear, and lock was available.
- First fixed-fixture BF16 attempt completed all requests but the harness initially failed to copy the external fixture into its output directory before hashing. Its throughput rows were not used. The artifact bug was fixed; the full fixed-fixture BF16 rerun passed (run3).
- Valid run directories: `/data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-ab-bf16-run3/` and `/data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-ab-e5m2-run1/`. Each contains config, source identity, model info, pool capacity, fixture, raw requests, summary and per-file SHA-256 manifest. Runner teardown lines saying `Killed` are process-group cleanup after outputs were written; both valid run exit codes are 0.
- Both valid runs used `/tmp/f1-r16b-gpu-exclusive.lock`. Final checks: no listener on 31258, GPU 1 MiB / 0%, and lock available. No per-kernel dispatch trace was collected. This comparison establishes neither an E5M2 product quality threshold nor acceptance.

## Frozen artifact SHA-256

- BF16 run3 fixture: `2c1c415a60a3f64ecf32aed413ac152d7f189084e831ee0bce75704a342f1077`
- BF16 run3 raw request waves: `f4541e5d846b2ffbb50146a4d01c851153d78b17ede684374eb663c582c37127`
- BF16 run3 summary: `08c8711d35ce802be8c96e79220bb76d876a9993a2cad506964089e7e651f664`
- BF16 run3 artifact hash manifest: `43f8ac44fe9cc24dca43679caeaeb1377fe8de05722c316c409d33a127457031`
- E5M2 run1 fixture: `2c1c415a60a3f64ecf32aed413ac152d7f189084e831ee0bce75704a342f1077`
- E5M2 run1 raw request waves: `a8640789715b8da16e66b98c6b8306a41bbbb7547b48942fc7a950106929ea9b`
- E5M2 run1 summary: `c0e5fb1cb11ade55cb4d51a0bf1572f8a91dc6439b75e9fc1aae2b36e527747b`
- E5M2 run1 artifact hash manifest: `47e9382948d84201b5403716c467480f8b677386bd23e14363d40ad334a6c2dc`
- Model: `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`
- HEAD kernel overlay: `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e`
- SM86 AOT binary: `22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2`
