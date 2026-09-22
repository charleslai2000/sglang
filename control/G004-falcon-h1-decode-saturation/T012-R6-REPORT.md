# G004 / T012-R6 — Final Falcon-H1 Node-Level Steady-Decode Capture

## Result

```text
T012-R6: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

The workload, report finalization, marker gate, and non-NULL graph-kernel correlation succeeded. The required node-timing gate did not: `CUDA_GRAPH_NODE_EVENTS` exists, but it contains no events whose timestamps overlap the marked steady interval. Per-kernel rows do carry non-NULL replay-qualified `graphNodeId` values, but under the requested acceptance gate this is not sufficient to claim closure.

## Capture

Workload:

```text
B=16
48/48 completed
0 client errors
12,288 output tokens
wall_s=26.5044436379103
```

Artifacts:

```text
runs/t012-r6/B16/server.nsys-rep
runs/t012-r6/B16/server.sqlite
```

Report size:

```text
15,247,248 bytes
```

The wrapper returned `NSYS_EXIT=137`, but the report was generated and independently readable. `nsys stats --report cuda_gpu_kern_sum` completed successfully and generated the SQLite export. No serving or Nsight process remained after cleanup.

Capture options included:

```text
--trace=cuda,nvtx,osrt
--cuda-graph-trace=node
--sample=none
--cpuctxsw=none
--cuda-event-trace=true
```

## Marker gate

Query:

```sql
SELECT start, end, eventType, text, globalTid, domainId
FROM NVTX_EVENTS
WHERE text IN ('G004_T012_BEGIN', 'G004_T012_END')
ORDER BY start;
```

Result: exactly one BEGIN and one END:

```text
BEGIN = 59,126,004,394 ns
END   = 59,721,443,468 ns
```

Marker gate: PASS.

Marked interval:

```text
duration = 595,439,074 ns = 595.439074 ms
actual batch = 16
waiting queue = 0
CUDA graph = true
```

The marker condition required batch size 16, empty waiting queue, and `can_run_cuda_graph=True`; serving logs confirmed full decode batches and CUDA graph execution.

## Node timing gate

SQLite contains:

```text
CUDA_GRAPH_NODE_EVENTS rows: 24,879
CUPTI_ACTIVITY_KIND_KERNEL rows: 79,933
```

However:

```text
CUDA_GRAPH_NODE_EVENTS rows overlapping marked interval: 0
```

The node-event records are zero-duration graph/node metadata events outside the replay interval. Therefore the required condition “marked interval 内有 node events” failed.

The kernel table does contain replay-qualified graph-node IDs:

```text
marked-interval kernel rows with graphNodeId IS NOT NULL: 29,286
marked-interval kernel rows with graphNodeId IS NULL: 418
```

Representative recovered kernel rows include:

```text
Marlin kernel, graphNodeId=8589934620
start=59125960328, end=59126013511

CUTLASS/BF16 GEMM kernel, graphNodeId=8589934628
start=59126059302, end=59126079046
```

Kernel symbol resolution through `StringIds` succeeded. This proves that node-level mode materially improved the export and exposed graph-node IDs on kernel activity, but the explicit node-event overlap gate remains unmet.

## Exploratory same-interval numbers (not accepted as closure)

For diagnostic completeness only, direct kernel rows with non-NULL `graphNodeId` produced:

```text
kernel interval union: 406.291281 ms
marked wall interval: 595.439074 ms
apparent union ratio: 68.2339%
apparent uncovered ratio: 31.7661%
```

Graph-launch runtime records in the marker interval:

```text
21 cudaGraphLaunch calls
start-to-start gap mean: 18.6169 ms
p50: 18.6739 ms
p95: 19.0260 ms
range: 18.0094–19.0291 ms
```

These numbers are not promoted to final accounting because the required `CUDA_GRAPH_NODE_EVENTS` interval gate failed, and node events cannot be used to validate the replay-to-kernel mapping for this exact interval.

The exploratory symbol-family totals were:

```text
other GEMM: 190.660317 ms raw, 6,841 calls
Marlin:      82.934446 ms raw, 1,943 calls
Mamba:       71.525519 ms raw, 1,942 calls
Attention:   26.936551 ms raw, 1,942 calls
norm/elem:   23.153539 ms raw, 11,741 calls
misc:        11.909823 ms raw, 4,877 calls
```

They are retained as diagnostic evidence only, not as the requested closure.

## Production state

The temporary R6 marker was fully removed. The marker source file has an empty git diff. No scheduler, CUDA graph policy, Marlin, Mamba, Attention, quantization, or serving behavior change remains.

## Final classification

```text
SYSTEM-LEVEL ROOT CAUSE:
NOT YET RESOLVED
```

## Next recommendation

Continue attribution with one offline review of the node-mode semantics—specifically whether `CUDA_GRAPH_NODE_EVENTS` is static graph-node metadata while `CUPTI_ACTIVITY_KIND_KERNEL.graphNodeId` is the authoritative per-replay timing—and obtain owner authorization before any further capture; do not change production behavior.
