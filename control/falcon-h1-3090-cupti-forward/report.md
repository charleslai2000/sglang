# T002 Falcon-H1-7B Forward CUPTI Range matrix — RTX 3090

Status: seven-shape core matrix measured (3 independent process samples per row); targeted regression passed. Commit/push status is recorded in the task handoff. These are isolated, profiler-enabled GPU measurements, not clean online throughput.

## Matrix

All rows are arithmetic means across `n=3` independent fresh processes/sessions. Prefill batch is 1 with prompt EXTEND length shown; decode batch is the exact captured CUDA Graph batch. `DRAM GB/s` is recomputed individually as `(same-range read bytes + same-range write bytes) / (same-forward graph-seam CUDA Event seconds)`, then averaged. CUPTI GPU duration is separately reported.

| Forward | CUDA Event ms | CUPTI GPU ms | SM Active % | SM Compute %Peak | Tensor Active % | DRAM GB/s | DRAM %Peak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prefill EXTEND 1K | 285.822 | 285.312 | 92.061 | 100.000 | 37.518 | 385.84 | 42.416 |
| Prefill EXTEND 4K | 1,113.026 | 1,112.497 | 96.045 | 100.000 | 38.470 | 362.24 | 39.770 |
| Decode Graph b1 | 13.678 | 13.112 | 70.308 | 100.000 | 13.240 | 596.03 | 68.229 |
| Decode Graph b2 | 15.018 | 14.491 | 68.687 | 100.000 | 18.852 | 564.42 | 64.189 |
| Decode Graph b4 | 15.875 | 15.338 | 70.580 | 100.000 | 17.388 | 574.17 | 65.213 |
| Decode Graph b8 (offline batch) | 17.440 | 16.880 | 73.911 | 100.000 | 15.189 | 596.04 | 67.574 |
| Decode Graph b16 (offline batch) | 20.665 | 20.111 | 79.144 | 100.000 | 15.198 | 628.68 | 70.886 |

## Per-row statistics and evidence

`P50/P95` for `n=3` means median / maximum observed sample, not a population tail estimate. CV is population standard deviation divided by mean. Times in ms, bandwidth in GB/s (decimal).

| Forward | n; Event P50/P95; CV | CUPTI P50/P95; CV | DRAM GB/s P50/P95; CV | Read / Write bytes (three samples) | Actual batch; Graph identity; correctness; Pass / Dropped | Raw evidence |
|---|---|---|---|---|---|---|
| Prefill EXTEND 1K | 3 stable, cold outlier excluded and retained; 286.092/287.283; 0.461% | 285.572/286.756; 0.455% | 385.451/388.298; 0.485% | 95,225,890,816 / 15,085,704,448; 95,187,710,976 / 15,086,790,400; 95,160,257,792 / 15,087,697,536 | 1; EAGER_EXTEND; argmax [48320] all; 1/0 all; exact logits match all | `runs/p1-stable-r0..r2.json`, logs; cold/outlier `p1-final-r0..r2.json` retained but excluded as set due to one 370.618 ms sample |
| Prefill EXTEND 4K | 3; 1112.732/1113.718; 0.044% | 1112.185/1113.204; 0.045% | 362.231/362.340; 0.021% | 347,055,534,208 / 56,094,034,048; 346,971,789,568 / 56,094,940,032; 347,240,205,056 / 56,093,802,496 | 1; EAGER_EXTEND; argmax [48336] all; 1/0 all. Exact logits match on 2/3 final runs; third argmax matches but max absolute logits diff 0.452953 (preserved as non-exact numerical parity) | `runs/p4-final-r0..r2.json`, logs; original `p4-r0..r2.json` are also preserved but excluded because emitted integrity/output fields predate harness hardening |
| Decode Graph b1 | 3 inherited; 13.673/13.741; 0.364% | 13.112/13.136; 0.150% | 596.251/598.573; 0.364% | 7,978,968,192 / 173,237,888; 7,979,161,856 / 173,297,792; 7,979,015,424 / 173,242,496 | 1; ShapeKey(size=1, stream_idx=None, variant_label=None, dsa_variant=None); argmax [12353] all; integrity verified by matching successful logs, one pass/zero dropped | `runs/decode-b1-r17..r19.json` and matching logs |
| Decode Graph b2 | 3; 15.020/15.025; 0.045% | 14.493/14.508; 0.103% | 564.341/564.772; 0.046% | 8,150,741,888 / 325,775,232; 8,150,447,616 / 325,680,512; 8,150,749,440 / 325,724,672 | 2; ShapeKey(size=2, stream_idx=None, variant_label=None, dsa_variant=None); argmax [12353,26806] all; logits exact, 1/0 all | `runs/d2-final-r0..r2.json` and matching logs |
| Decode Graph b4 | 3; 15.862/15.926; 0.237% | 15.315/15.391; 0.245% | 574.638/575.578; 0.240% | 8,484,974,720 / 629,835,008; 8,485,542,784 / 629,888,896; 8,484,971,776 / 629,800,960 | 4; ShapeKey(size=4, stream_idx=None, variant_label=None, dsa_variant=None); argmax [12353,26806,124000,3434] all; logits exact, 1/0 all | `runs/d4-final-r0..r2.json` and matching logs |
| Decode Graph b8 | 3; 17.476/17.484; 0.331% | 16.870/16.961; 0.369% | 594.778/598.825; 0.331% | 9,154,398,336 / 1,240,296,192; 9,154,306,688 / 1,240,250,752; 9,154,329,856 / 1,240,251,264 | 8; ShapeKey(size=8, stream_idx=None, variant_label=None, dsa_variant=None); argmax [12353,26806,124000,3434,1243,17677,14656,126483] all; logits exact, 1/0 all | `runs/d8-final-r0..r2.json` and matching logs |
| Decode Graph b16 | 3; 20.700/20.732; 0.356% | 20.115/20.173; 0.257% | 627.598/631.817; 0.359% | 10,516,766,208 / 2,474,286,720; 10,517,324,928 / 2,474,102,016; 10,516,889,600 / 2,474,120,064 | 16; ShapeKey(size=16, stream_idx=None, variant_label=None, dsa_variant=None); argmax list stable; logits exact, 1/0 all | `runs/d16-final-r0..r2.json` and matching logs |

### Output parity and actual state

Every trial reconstructs the deterministic token fixture from the archived R17 token-ID workload (for each decode batch, tiled frozen rows; each derived fixture SHA is in its JSON), performs real Falcon prefill to establish KV and Mamba state, and runs real `ModelRunner.forward`. Decode uses captured production Full CUDA Graphs and checks exact batch-size ShapeKey. Separate final parity runs confirm CUPTI-ON vs unprofiled same-process output: Decode and Prefill 1K full logits bitwise equal; Prefill 4K exact for 2/3 final trial sessions, and the third differs by max abs 0.452953 while argmax remains equal. This observed mismatch is explicitly preserved, not hidden. The parity runs are correctness evidence, not added to performance statistics.

For every core sample, CUPTI result had `passes=1`, `dropped=0`, `expected_range_count=1`; validation selects exactly one populated target UserRange, excluding CUPTI's all-NaN implicit root row. All decode trials record actual Mamba pool indices and graph identity. Prefill uses eager Extend (`EAGER_EXTEND`), not a CUDA Graph.

## CUPTI lifecycle and timing boundaries

Per workload, initialization / Falcon pool and graph setup / warmup are completed before the measured Range. CUPTI is armed once for the selected Forward; a single named UserRange encloses that real Forward; `PopRange -> Stop -> DecodeData -> Disable` occurs before process exit. Core GA102 metric configuration is one pass. No Application Replay or production online-path synchronization was introduced. The harness synchronizes after the measured invocation to finalize CUPTI; CUDA Events are placed on the same execution stream immediately around eager Extend or, for Decode, directly around the actual captured graph replay in `FullCudaGraphBackend.replay`, excluding CUPTI object setup. GPU CUPTI duration is separately retained from those Events.

Across rows, CUPTI duration is below the CUDA Event (Prefill 1K/4K ~0.16%/~0.05%; Decode b1/b2/b4/b8/b16 ~4.32%/3.63%/3.50%/3.32%/2.75%). This small repeatable boundary/metric difference is not merged or treated as clean throughput. An early invalid b1 `r16` had an Event window of 5568 ms and is explicitly excluded. JSON legacy `dram_gbps` was calculated from a prior host-inclusive Event before the graph seam correction; recompute bandwidth from raw bytes and current `gpu_event_ms` as this report does.

## Bottleneck interpretation

Measured prefill runs report SM Active 92–96%, SM Compute 100%, Tensor Active ~37.5–38.5%, with DRAM at 39.8–42.6% of peak. Decode DRAM is ~63.4–71.1% of peak with SM Active ~67.8–79.4% and Tensor Active ~13.2–18.9%. These data establish substantial compute activity and meaningful DRAM traffic; they do not alone prove a compute-bound or bandwidth-bound roofline bottleneck. **Conclusion: exact limiting resource UNKNOWN** without controlled kernel-level attribution/roofline comparison. b8/b16 are offline captured graph batch experiments, not online concurrency or service TPS.

## Provenance and checks

- Frozen model: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`.
- Branch `3090-24g-hicache`; all trials use sudo and this mainline checkout plus the authorized `/tmp/t002-sm86-overlay-root` kernels overlay; GPU is idle after runs (1 MiB, 0%).
- CUPTI native extension SHA-256 in measured process logs: `82c36b8ec02a3c32be33f0652fae198d842922b943901d3561ce26ec8315b3a4`.
- Core trial files listed above; `*-parity.json`/logs are separate output-parity evidence. Failed initialization/allocation attempts and early invalid diagnostics remain preserved in `runs/` and are not counted.
- Validation: Python `py_compile`, staged/unstaged `git diff --check` passed; Forward metrics unit tests 15 passed with designated SM86 overlay. Full online-service regression was not part of this isolated profiling-only change.
