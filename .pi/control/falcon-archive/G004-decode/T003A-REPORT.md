# G004 / T003A — Low-Intrusion Timeline Attribution

## Verdict

```text
T003A: PASS
ROOT CAUSE: MIXED, Marlin-dominant; compute-vs-memory bound within Marlin remains unresolved
```

No optimization, scheduler change, CUDA graph change, model change, or kernel
change was made. No Nsight Compute or targeted micro-profile was run.

## T002 evidence review

T002 established:

```text
B=8/12/16 actual batch: full configured batch
B=16 scheduler underfill: not observed
GPU utilization: approximately 98%
memory-controller utilization: approximately 66–70%
power: approximately 344–346 W
memory clock: stable at 9501 MHz
SM clock: decreases with increasing batch
VRAM: stable around 21.6 GiB
```

This ruled out scheduler underfill, long GPU starvation, VRAM capacity, and a
simple claim that DRAM bandwidth was already at 100%. It did not identify a
kernel family or distinguish compute-bound from memory-bound behavior inside a
kernel family.

## Capture method

Nsight Systems 2025.1.3 was used with unchanged production execution:

```text
--trace=cuda,nvtx,osrt
--sample=none
--cpuctxsw=none
--cuda-event-trace=true
```

The workload was the T002 48-request full-wave workload at B=8 and B=16. The
capture workload itself completed normally:

```text
B=8:  48/48 completed, cuda graph=True, actual batch=8, queue=0
B=16: 48/48 completed, cuda graph=True, actual batch=16, queue=0
```

The `.nsys-rep` files were finalized asynchronously after server cleanup. The
first temporary zero-byte observation was only an in-progress write; final
reports are readable:

```text
runs/t003a/B8/server.nsys-rep: 21 MiB
runs/t003a/B16/server.nsys-rep: 58 MiB
```

## B=8 vs B=16 kernel summary

The Nsight `cuda_gpu_kern_sum` report gives the following approximate GPU kernel
time shares.

| Kernel family | B=8 share | B=16 share | Interpretation |
|---|---:|---:|---|
| Main GPTQ-Marlin kernel | 47.7% | 48.1% | clear dominant family; share stable |
| CUTLASS BF16 tensor GEMM, 256x128 | 11.2% | 12.2% | second-largest family; share increases |
| BF16 GEMM `ampere_bf16_s16816...` | 9.0% | 8.0% | major GEMM family |
| Mamba `_chunk_scan_fwd_kernel` | 7.1% | 7.6% | largest individually visible Mamba family |
| Mamba `_chunk_state_fwd_kernel` | 4.4% | 4.4% | stable Mamba family |
| Mamba `_state_passing_fwd_kernel` | 1.7% | 1.8% | stable Mamba family |
| Other visible Mamba kernels | ~2–3% | ~2–3% | includes varlen/conv/state/cumsum/bmm families |

Approximate component grouping from the kernel summary:

```text
GPTQ/Marlin FFN and associated linear/GEMM path: ~60–65%
Mamba kernel families: ~17–20%
Attention and other fused/norm/elementwise kernels: remainder
```

The grouping is approximate because several CUTLASS/BF16 kernels are shared
linear/activation paths and cannot be mapped to one component solely by kernel
name. The dominant-family conclusion is not ambiguous: the main Marlin kernel
is approximately half of measured GPU kernel time at both B values.

Important scaling detail:

```text
main Marlin total GPU time:
  B=8:  3.575 s across 1936 instances
  B=16: 3.587 s across 1936 instances
```

The instance count is the same in these reports and total Marlin time is nearly
flat, while the 48-request run's aggregate throughput rises from approximately
335 to 464 tok/s. This is not evidence that Marlin time is free of all scaling
cost; it does show that the dominant kernel's aggregate report is not simply
increasing proportionally with configured batch in this capture. It also means
these whole-capture totals include startup/prefill/lifecycle work and are not a
pure steady-decode slice.

## CUDA graph and API evidence

Server logs and capture runs confirm decode execution used CUDA graphs:

```text
B=8: cuda graph=True
B=16: cuda graph=True
```

`cuda_api_sum` reports:

```text
B=8:
  cudaEventSynchronize: 57.1% API time
  cudaMemcpyAsync:      12.3%
  cudaStreamSynchronize:12.3%
  cudaLaunchKernel:      8.2%
  cudaGraphLaunch:       2.9%

B=16:
  cudaEventSynchronize: 33.0% API time
  cudaMemcpyAsync:      23.9%
  cudaStreamSynchronize:21.0%
  cudaLaunchKernel:      11.2%
  cudaGraphLaunch:        1.3%
```

These are process-wide CUDA API elapsed-time summaries, not a clean steady
window. They cannot be converted directly into GPU idle percentages. They do
show substantial host/API synchronization and memcpy activity, especially at
B=16, but the report does not prove that these calls are on the critical
steady-decode path rather than setup, lifecycle, or asynchronous coordination.

Thus:

```text
CUDA graph replay is confirmed.
A precise replay-to-replay CPU gap and GPU idle-gap ratio is not established.
```

## Timeline / gap conclusion

The Nsight reports provide kernel and CUDA API summaries, but this stage did not
produce a robust steady-window interval accounting table separating:

```text
GPU busy time
GPU idle/gap time
CPU launch/replay gap
prefill/drain lifecycle time
```

Therefore a runtime/launch-bound conclusion is not justified from API summary
percentages alone.

## Final attribution

```text
ROOT CAUSE: MIXED, Marlin-dominant
```

Supported by decisive evidence:

```text
actual batches are full at B=8 and B=16
CUDA graphs are active
main GPTQ-Marlin kernel is ~48% of GPU kernel time at both B values
BF16 GEMM families add ~20% combined
Mamba families add approximately 17–20%
GPU utilization is ~98%
DRAM utilization is ~66–70%, not an obvious platform ceiling
```

What remains unresolved:

```text
whether the dominant Marlin path is compute-bound or memory-bound internally
exact steady-decode GPU idle / CPU replay-gap percentage
```

## Next step

```text
NEXT: targeted deep profile of GPTQ-Marlin dominant kernel family
```

Only the main Marlin family should be targeted first. If the targeted profile
cannot separate SM/tensor pressure from DRAM/occupancy/stall behavior, then a
second targeted profile may be considered; no Mamba or Attention deep profile
is justified before that result.

No optimization was executed.

## Artifacts

```text
runs/t003a/B8/server.nsys-rep
runs/t003a/B8/server.sqlite
runs/t003a/B8/profiler.json
runs/t003a/B16/server.nsys-rep
runs/t003a/B16/server.sqlite
runs/t003a/B16/profiler.json
/tmp/t003a-b8-kern_cuda_gpu_kern_sum.csv
/tmp/t003a-b16-kern_cuda_gpu_kern_sum.csv
/tmp/t003a-b8-api_cuda_api_sum.csv
/tmp/t003a-b16-api_cuda_api_sum.csv
```
