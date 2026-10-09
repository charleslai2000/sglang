# OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910

## Scope

- Hardware: one RTX 3060 12 GB, SM86.
- Model: `Qwen3.5-4B-AWQ`.
- Weight backend: compressed-tensors W4A16 with Marlin startup path.
- KV dtype: FP8 E4M3.
- CUDA Graph: enabled; HiCache enabled; RH was OFF for the sweep.
- Request: short prompt, generation length 256, same trace shape per concurrency point.
- Sweep: nominal concurrency `c1/c2/c4/c6/c8`.
- The service was restarted between points and restored to the AWQ RH-ON c1 profile after the sweep.

## Results

| Nominal c | Returned/OK | Generated tokens | Batch wall (s) | Aggregate output TPS | Per-request TPS | HTTP failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1/1 | 256 | 2.9209 | 87.64 | 87.68 | 0 |
| 2 | 2/2 | 512 | 21.1211 | 24.24 | 12.12 | 0 |
| 4 | 4/4 | 1024 | 20.9702 | 48.83 | 12.21 | 0 |
| 6 | 6/6 | 1536 | 21.0232 | 73.06 | 12.18 | 0 |
| 8 | 8/8 | 2048 | 20.8778 | 98.09 | 12.27 | 0 |

The c2-c8 points reached a stable shared-batch decode rate of roughly 12.2
tokens/s/request; aggregate throughput therefore scales approximately with the
number of concurrent requests through c8. No OOM, zero-progress, HTTP error, or
request admission failure occurred in this sweep.

## Runtime evidence

- The c6 log reports `#running-req: 6`, `mamba num: 18`, and mamba usage `0.34`.
- The c8 log reports `#running-req: 8`, `mamba num: 24`, and mamba usage `0.45`.
- The c8 endpoint returned HTTP 200 for all eight requests.
- The restored c1 RH-ON service returned health HTTP 200 after the sweep.
- Representative idle/after samples stayed around 8.5 GiB used and 3.5 GiB free
  GPU memory. These are samples, not peak power or peak allocator measurements.

## Interpretation and limits

This is a successful decode-concurrency stability sweep, not yet the final
production ceiling. The tested workload used only 256 generated tokens per
request and short prompts; it does not establish long-context admission capacity,
HiCache restore correctness, RH staging effectiveness, or a 55K-session result.
The next required measurement is context capacity with fixed AWQ + FP8 KV + graph
ON, followed by the durable GPU/Host/L3 restore path.

## Service handoff

The remote service was left on the AWQ W4A16/FP8-KV RH-ON c1 profile. Final health
check was HTTP 200. No Neuron process was touched.

