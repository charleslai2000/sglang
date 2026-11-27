# T012 Humming W4A16 — compatibility and kernel-shape screen

Date: 2026-11-27
Frozen source: `c4f6b50da7940ff28fefae2eb3fb0b71eb1014cc`
Host: RTX 3090 (SM86), Torch `2.13.0+cu129`, CUDA `12.9`, humming-kernels `0.1.12`

## Summary

The checkpoint is Gemma4 language-model W4A16: compressed-tensors `pack-quantized`, symmetric INT4, group size 32, BF16 activations, no input activation quantization. The prior plan's suggestion that Marlin's generic shape gate excludes group-32 was wrong: repository `MARLIN_SUPPORTED_GROUP_SIZES` includes 32 and both C-8 Marlin templates are in the observed path. The actual production weights/scales are present as packed int32 and BF16 scale tensors. Schema/device compatibility and matched isolated GEMM timing were established. The decisive call-weighted C-8 savings gate remains **UNKNOWN** because the stored C-8 capture lacks exact per-call projection and M/N/K attribution.

Humming's upstream compressed-tensors schema accepts this exact metadata and maps it to unsigned INT4, group-32. Checkpoint packed int32 values and BF16 scales are byte/value-identical immediately after `convert_humming`. The CUDA repack/pad stage necessarily changes layout, as allowed by scope; it does not requantize. One real Gemma4 MLP gate projection was additionally unpacked into an explicit symmetric-int4 BF16 oracle: Humming output matched with max abs error 0.03125, mean abs 0.00167 at the tested M=8 vector, `allclose(atol=.25, rtol=.02)`. This is a spot check, not full accuracy certification.

The Humming dependency loads and executes on the RTX 3090. Tuning resolves BF16 × INT4 group32 GEMM and configured rows cover requested M=8..4096. Actual-weight Humming and matched Marlin timings were obtained for q-proj `(N,K)=(2048,2560)`, gate `(10240,2560)`, and down `(2560,10240)`. The isolated results show gate/down regressions at M≤1280 and modest gains at M=4096, but stored C-8 traces do not provide per-call projection and M/N/K. Therefore the required C-8 call-weighted ≥15 s savings estimate is UNKNOWN; no integration decision may be inferred from isolated timings.

## Exact source and checkpoint evidence

- Model: `/data/sglang-hicache/gemma4/model/config.json`, `model.safetensors`.
- Config group: target `Linear`; `format=pack-quantized`, `type=int`, `num_bits=4`, `strategy=group`, `group_size=32`, `symmetric=true`, `actorder=null`; `input_activations=null`.
- Runtime dtype: config/model BF16. The captured production Marlin names demangle `Marlin<__nv_bfloat16,...>`.
- Safetensors examples at language layer 0:
  - `mlp.gate_proj`: `weight_packed [10240,320] int32`, `weight_scale [10240,80] bfloat16`, `weight_shape [10240,2560]`.
  - `mlp.down_proj`: `weight_packed [2560,1280] int32`, `weight_scale [2560,320] bfloat16`, `weight_shape [2560,10240]`.
  - `self_attn.q_proj`: `weight_packed [2048,320] int32`, `weight_scale [2048,80] bfloat16`, `weight_shape [2048,2560]`.
- The raw packed values are checkpoint-authoritative. Humming `CompressedTensorsWeightSchema.convert_humming` returned exactly equal weight bytes and scale values for all three shapes. Humming transforms use its CUDA-only repack op, so the layout transform executes on device; no numeric requantization is applied.
- SGLang `HummingLinearMethod` uses the parsed checkpoint schema unless an explicit forced target schema is supplied. This run did not set force schema or online quantization.
- SGLang's compressed-tensors linear selector selects `CompressedTensorsWNA16`; `MARLIN_SUPPORTED_GROUP_SIZES` includes `[-1,32,64,128]`. So there is no group-32 exclusion. Humming and Marlin receive the same checkpoint schema values, with backend-specific equivalent layouts.

## Actual-weight matched GEMM measurements

Bounded Humming and follow-up Marlin GPU runs used actual layer-0 checkpoint weights/scales, BF16 random activations and 15/21 CUDA-event timings per cell after warmup. For Marlin, the checkpoint tensors were transformed through the repository's production Marlin repack and scale permutation routines; no values were requantized. Both paths emitted finite BF16 outputs with expected `(M,N)` shape. Humming's separate decoded-weight correctness spot-check is above.

| Projection N×K | M | Humming median | Marlin median | Humming minus Marlin |
|---|---:|---:|---:|---:|
| MLP gate 10240×2560 | 8 | 0.2221 ms | 0.1513 ms | +0.0708 ms |
| | 16 | 0.2235 ms | 0.1536 ms | +0.0699 ms |
| | 32 | 0.2050 ms | 0.1505 ms | +0.0545 ms |
| | 1024 | 0.6083 ms | 0.5806 ms | +0.0276 ms |
| | 1280 | 0.7281 ms | 0.6994 ms | +0.0287 ms |
| | 4096 | 1.8778 ms | 2.1668 ms | **−0.2890 ms** |
| MLP down 2560×10240 | 8 | 0.2306 ms | 0.1679 ms | +0.0627 ms |
| | 16 | 0.2305 ms | 0.1628 ms | +0.0677 ms |
| | 32 | 0.2406 ms | 0.1638 ms | +0.0768 ms |
| | 1024 | 0.6286 ms | 0.5478 ms | +0.0808 ms |
| | 1280 | 0.7658 ms | 0.7322 ms | +0.0336 ms |
| | 4096 | 1.8504 ms | 2.1381 ms | **−0.2877 ms** |

Humming is slower in the measured gate/down cells through M=1280 and faster only at M=4096 by about 0.29 ms. These isolated measurements cannot be weighted against C-8 because extant traces do not map every call to projection and M/N/K. Thus the ≥15 s C-8 gate is **UNKNOWN**, not established as met or failed. Raw results: `humming-results.json`, `marlin-results.json`; logs/identity: `bench.log`, `marlin-bench.log`, `intent.txt`, `marlin-intent.txt`, `process.txt`, `exit.txt`, `marlin-exit.txt`.

## Trace attribution limits and key correction

C-8 stored Nsight Systems capture at `20261126T-t009-c8-profile-r7/t007-c8-window.sqlite` contains 2,371,545 kernel rows and no NVTX annotations carrying Marlin shape or projection metadata. The two Marlin families are:

| Demangled template suffix | Calls | Sum device time | grid/block |
|---|---:|---:|---|
| `Marlin<bf16,…,256,2,16,4,false,4,2,false>` | 514,670 | 17.3241 s | 82×1×1 / 256×1×1 |
| `Marlin<bf16,…,256,4,16,4,false,4,2,false>` | 43,984 | 24.7942 s | 82×1×1 / 256×1×1 |

These counts/times agree with the T010 C-8 table, but neither grid nor specialization uniquely identifies M/N/K. The C-8 profile has no projection/layer correlation labels; CUDA runtime/kernel correlation identifies launch API intervals, not caller arguments or matrix shape. T010's seven-shape capture has scheduler run_batch ranges, but request phases were not labeled as NVTX and kernels all share the same gridX 82, so it does not safely join each observed Marlin call to M=1024/1280/4096 or decode M=8/16/32. The phase request result files preserve counts/prompts, not the per-forward Marlin shape. Assigning M from kernel variant or grid size would be speculation.

The exact C-8 per-shape M/N/K histogram is not recoverable from extant captures. Matched isolated timings exist, but cannot establish whether the call-weighted C-8 saving is ≥15 s. Therefore the pre-integration gate remains **UNKNOWN** and integration must not proceed.

## Decision / remaining work

Matched isolated actual-weight comparisons are recorded, but exact C-8 shape attribution and the weighted savings estimate remain **UNKNOWN** because stored traces lack per-call projection and M/N/K. T012 is blocked at the pre-integration gate; no integration or C-8 candidate run. Obtain defensible C-8 shape attribution or leave the Goal blocked.
