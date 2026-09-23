# G004 / T012-R7 — Node-Mode Semantics Review

## Result

```text
T012-R7: PASS
T012-R6 accounting recoverable
```

This review was offline-only. No workload, serving process, code modification, or capture was performed.

## Exact semantics

### `CUDA_GRAPH_NODE_EVENTS`

In the local Nsight Systems node-mode export, `CUDA_GRAPH_NODE_EVENTS` is graph-node metadata/event information. It is not the authoritative per-replay GPU kernel timing stream for the Falcon-H1 capture. Its records are sparse/zero-duration node events and do not repeat as timestamped records for every graph replay in the marked interval.

The absence of node-event rows overlapping the R6 marker interval is therefore not evidence that the graph replay had no node execution. The prior R6 acceptance requirement that this table overlap the marker interval was invalid.

### `CUPTI_ACTIVITY_KIND_KERNEL.graphNodeId`

In node mode, `graphNodeId` on `CUPTI_ACTIVITY_KIND_KERNEL` is the replay-qualified graph-node identity. `CUPTI_ACTIVITY_KIND_KERNEL.start/end` are the per-kernel GPU execution timestamps. `StringIds` resolves `demangledName` to the actual kernel symbol.

The decisive operational representation is:

```text
CUPTI_ACTIVITY_KIND_KERNEL.start/end
+ CUPTI_ACTIVITY_KIND_KERNEL.graphNodeId
+ StringIds.demangledName
```

## Synthetic R5 proof

R5 node-mode artifact:

```text
runs/t012-r5/node/probe.sqlite
```

Known probe structure:

```text
one CUDA graph
three graph kernel nodes
five graph replays
```

Observed kernel rows:

```text
non-NULL graphNodeId kernel rows: 15
unique graphNodeId values: 3
rows per graphNodeId: 5, 5, 5
```

The three stable replay-qualified node IDs each recur five times at distinct timestamps. For example, each of the three graph nodes has five kernel executions spanning the five known replays. This establishes:

```text
graphNodeId = stable identity for the replay-qualified graph node
kernel start/end = per-replay kernel execution timing
```

R5 also contains `CUDA_GRAPH_NODE_EVENTS`, but that table has only sparse node metadata/event rows and does not provide the five per-node execution records. The repeated kernel rows, not node-event overlap, carry the replay timing.

## R6 validation

R6 node-mode artifact:

```text
runs/t012-r6/B16/server.sqlite
```

Marked interval:

```text
BEGIN = 59,126,004,394 ns
END   = 59,721,443,468 ns
duration = 595,439,074 ns = 595.439074 ms
```

Within the interval:

```text
kernel rows with graphNodeId != NULL: 29,286
kernel rows with graphNodeId == NULL:    418
```

The non-NULL graph rows resolve to production symbols including Marlin, CUTLASS/BF16 GEMM, Mamba, Attention/FlashInfer, norm/elementwise, and miscellaneous kernels. Repeated replay-qualified graphNodeIds occur across the capture. The runtime table contains 21 `cudaGraphLaunch_v10000` calls in the interval, with cadence consistent with the observed steady decode workload:

```text
mean: 18.6169 ms
p50:  18.6739 ms
p95:  19.0260 ms
range: 18.0094–19.0291 ms
```

The R6 node-event overlap gate was therefore invalid and is retired. The authoritative interval gate is now the presence of timestamped kernel rows with non-NULL `graphNodeId`, symbol resolution, and consistent repeated graph-launch cadence.

## Recomputed marked-interval accounting

Accounting uses only kernel rows satisfying:

```text
start < END
end > BEGIN
graphNodeId IS NOT NULL
```

Kernel intervals are clipped to the marker interval and unioned to avoid double-counting overlap.

```text
marked wall interval: 595.439074 ms
recovered kernel rows: 29,286
kernel union:          406.291281 ms
GPU busy:              68.2339%
uncovered wall time:   31.7661%
```

The uncovered percentage is the wall-time complement of the recovered kernel union. It is reported as uncovered/runtime-or-gap time, not as a claim that every uncovered nanosecond is host runtime.

### Component accounting

Family classification uses the established symbol mapping. Per-family times are unioned within each family; family percentages are shown against recovered kernel union and against the marked wall interval. Since the families are disjoint by classifier, family union overlap is not used as a substitute for the global union.

| Family | Calls | GPU time (ms) | Share of recovered kernel time | Share of marked interval |
|---|---:|---:|---:|---:|
| Other BF16/CUTLASS GEMM | 6,841 | 190.607773 | 46.9141% | 32.0113% |
| Main GPTQ-Marlin | 1,943 | 82.934446 | 20.4126% | 13.9283% |
| Mamba | 1,942 | 71.525519 | 17.6045% | 12.0122% |
| Attention / FlashInfer | 1,942 | 26.874121 | 6.6145% | 4.5133% |
| Norm / elementwise | 11,741 | 23.029221 | 5.6682% | 3.8676% |
| Misc | 4,877 | 11.909823 | 2.9314% | 2.0002% |

The sum of family times is not used as global GPU busy time; the global 406.291281 ms value is the cross-family interval union.

## Final classification

The kernel rows are authoritative for the node-mode per-replay execution timing, so R6 is recoverable without a new capture. The marked interval has a substantial 31.77% uncovered wall-time complement, while the kernel workload is distributed across other GEMM, Marlin, Mamba, and supporting families. Main Marlin is not the largest single family in this exact interval; other BF16/CUTLASS GEMM is larger.

```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU + RUNTIME/GRAPH-GAP
```

This is not classified as `GPU-KERNEL-DISTRIBUTED, MARLIN-DOMINANT` because the exact interval's Marlin share is approximately 20.4% of recovered kernel time versus approximately 46.9% for other GEMM, and the uncovered wall-time complement is approximately 31.8%.

## Next recommendation

Close G004 attribution with the final classification `MIXED GPU + RUNTIME/GRAPH-GAP`; do not run another capture, and move only to separately authorized optimization selection.
