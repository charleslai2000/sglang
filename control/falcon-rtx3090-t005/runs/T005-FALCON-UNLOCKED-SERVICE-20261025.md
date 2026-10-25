# Falcon RTX3090 解锁后服务复测

## 身份与方法
- UTC run: `20261025T094033Z`; raw artifacts: `/data/sglang-hicache/falcon-unlocked-20261025/runs/20261025T094033Z/`。
- Model: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; tokenizer/config/index/two weight shard hashes match the frozen T005 manifest.
- Runtime: 当前唯一工作区 `3090-gemma4-e4b-hicache` HEAD `b2c58c93ed730407162729ab43fceeff51968e68`; Python 3.12 / PyTorch 2.13.0+cu129 / SGLang 0.5.20.dev22+g9c9e7b7c7 / Transformers 5.12.1. Local SM86 AOT binary SHA256 `085f305b405be0a1591be83c36dede9154162c69fd009813d5713426dd669156`, exposed using isolated `/data` bootstrap.
- GPU: RTX3090 guest BDF `0000:00:10.0`, Driver 580.178.04, 350W cap; unlocking state was previously confirmed in dmesg. This is a fresh Falcon run, not a locked Stock-vs-Unlocked Falcon pair.
- T005 fixed fixture SHA is `a83e3325f72cf4d25e3addb7c288a6879030b333351d3240a0bee9f86fd0beed` (64 token IDs; compact fixture array SHA in original fixture remains placeholder). Greedy, 256 new tokens, ignore EOS; one warmup before each concurrency's 3 waves, 4*C requests per wave.
- T005-like serving config: static memory fraction .9, max-running 32 (runtime capped at 16 by 83 Mamba states and five slots/request), max queued 128, chunked prefill 2048, max prefill 16384, FlashInfer attention/sampling, Triton Mamba, prefill CUDA graph disabled. `server.log` captures actual full arguments and startup memory pool.

## Results
| Client concurrency | Waves (output tok/s) | Mean ± sample SD | Request success |
|---:|---|---:|---:|
| 8 | 433.4116, 457.4765, 455.7160 | **448.8680 ± 13.4146** | 32/32 each |
| 32 | 778.3216, 776.9648, 776.5525 | **777.2796 ± 0.9256** | 128/128 each |

Every measured request produced the full 256 tokens. 1K prefill request used exactly 1,024 token IDs and returned 16 tokens; server E2E `0.4487514 s`, client wall `0.494564865 s`. Ordinary text smoke returned 32 tokens.

## Comparison limits
Historical final clean T005 values are c8 `435.65 ± 1.97` and c32 `732.93 ± 2.72` output tok/s. They are an approximate historical comparison only: separate dates/runs, and this run used current Gemma checkout/runtime state. Do not treat deltas as causal GPU-unlock effects. The c32 number is 32 client requests in flight; server max running was capped at 16 and graph capture reached 16.

Prior GEMM A/B evidence (different workload) showed identical Stock/Unlocked output hashes and FP16/BF16/TF32 speedups 1.591×/1.620×/1.635×. It does not establish Falcon model-level speedup.

## Artifact integrity and cleanup
- `smoke-response.json` SHA256 `5dcdb1334dd0691ce2b81456915630d61a0997f0039d632eff2b32c60dfb2714`.
- `prefill-1k-response.json` SHA256 `eaa55bdf8f70b6d02f18a7801cb937a1ace7e4425d8593002f414a72233d131b`.
- Model hashes: `model-sha256.txt`; throughput raw JSON in `c8/` and `c32/`; fixture/prompt IDs, server config/log and GPU before/during/after snapshots co-located.
- Server stopped, port closed, GPU returned to 1 MiB / 0%, power cap remained 350W. No repository dirty content was modified by the run; no source commit was made.
