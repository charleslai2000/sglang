# G004 / T012-R3 — Final Marked B=16 Steady-Decode Capture

## Result

```text
T012-R3: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

The workload, report finalization, SQLite export, and marker gate all passed. The exact same-interval kernel/component accounting did not pass: the NVTX interval is present, but the kernel activity rows in that interval do not contain the expected production Marlin/GEMM families. Therefore no misleading component percentages are reported and the system-level classification remains unresolved.

## Capture

Workload result:

```text
B=16
48/48 completed
0 client errors
12,288 output tokens
wall_s=26.30333755200263
```

Capture artifact:

```text
runs/t012-r3/B16/server.nsys-rep
```

Report size:

```text
15,182,299 bytes
```

Nsight reported exit status:

```text
NSYS_EXIT=137
```

The report was nevertheless fully generated before the wrapper's final status was observed. Independent offline export succeeded:

```text
runs/t012-r3/B16/server.sqlite
/tmp/t012-r3-kern_cuda_gpu_kern_sum.csv
```

The SQLite file is 44 MiB and `nsys stats --report cuda_gpu_kern_sum` completed successfully. No serving or Nsight process remained after capture cleanup.

## Marker gate

Query:

```sql
SELECT start, end, eventType, text, globalTid, domainId
FROM NVTX_EVENTS
WHERE text IN ('G004_T012_BEGIN', 'G004_T012_END')
ORDER BY start;
```

Recovered exactly two rows:

```text
(59187178779, NULL, 34, 'G004_T012_BEGIN', 317600552770340, 0)
(59775508001, NULL, 34, 'G004_T012_END',   317600552770340, 0)
```

Thus marker presence passed, with exactly one BEGIN and one END and BEGIN < END.

## Marked interval

```text
BEGIN = 59,187,178,779 ns
END   = 59,775,508,001 ns
duration = 588,329,222 ns = 588.329222 ms
actual batch = 16
waiting queue = 0
CUDA graph state = true
```

The serving log during the workload reports full decode batches with `#running-req: 16`, `#queue-req: 0`, and `cuda graph: True`. The marker condition itself required batch size 16, empty waiting queue, and `can_run_cuda_graph=True`.

## Timeline evidence

`CUPTI_ACTIVITY_KIND_GRAPH_TRACE` contains 33 graph traces overlapping the exact marker interval. Their union is:

```text
graph trace union = 585.080870 ms
relative coverage = 99.4479%
uncovered interval = 0.5521%
```

Graph trace start-to-start gaps:

```text
count = 32
mean = 18.3892 ms
p50  = 18.3872 ms
p95  = 18.5706 ms
range = 18.1209–18.5772 ms
```

This is valid same-interval CUDA graph trace evidence, but it is not substituted for the required production kernel-family accounting.

## Same-interval kernel/component accounting status

The exact interval contains 608 rows in `CUPTI_ACTIVITY_KIND_KERNEL`, but after resolving `demangledName` through `StringIds`, those rows contain only short setup/elementwise/scatter-like activity. The expected production Marlin and BF16/CUTLASS GEMM families are absent from the interval's kernel rows. The resulting raw activity totals are therefore not a valid representation of the steady decode operation:

```text
kernel-row union: 2.629798 ms / 0.44699% of marker interval
Marlin: not recovered
other BF16/CUTLASS GEMM: not recovered
Mamba: 0.111806 ms raw, 64 calls — not accepted as complete composition
Attention: 0.076287 ms raw, 32 calls — not accepted as complete composition
norm/elementwise: 0.992827 ms raw, 384 calls — incomplete
misc: 1.448878 ms raw, 128 calls — incomplete
```

This discrepancy means the kernel activity table and graph trace table are not being joined/represented in a way that supports the requested exact component attribution for this serving capture. In particular, the 99.45% graph-trace coverage must not be mislabeled as GPU kernel busy percentage, and the 0.447% kernel-row union must not be interpreted as actual GPU utilization.

Required fields consequently remain unavailable:

```text
GPU kernel busy %: unavailable
GPU idle/runtime gap %: unavailable
Marlin %: unavailable
other GEMM %: unavailable
complete Mamba/Attention/misc composition: unavailable
```

## Production state

The temporary R3 marker was fully removed after capture. The marker source file has an empty git diff. No scheduler, CUDA graph policy, Marlin, Mamba, Attention, quantization, or serving behavior change remains.

## Final classification

```text
SYSTEM-LEVEL ROOT CAUSE:
NOT YET RESOLVED
```

The capture proves the marker interval and graph replay cadence, but does not provide defensible same-interval GPU kernel/component accounting under the current Nsight serving capture representation.

## Next recommendation

Authorize one offline Nsight schema/correlation investigation on the finalized `server.sqlite`—without rerunning the workload—to identify the correct graph-node/kernel activity join; do not change production behavior or classify the root cause until that join yields complete same-interval Marlin/GEMM/Mamba/Attention accounting.
