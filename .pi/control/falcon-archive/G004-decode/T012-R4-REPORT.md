# G004 / T012-R4 — Offline Nsight Schema / Correlation Recovery

## Result

```text
T012-R4: PARTIAL
SAME-INTERVAL KERNEL TIMING: NOT RECOVERABLE FROM THIS CAPTURE
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

Analysis was offline-only. No workload, serving process, code change, profiler capture, or optimization was performed.

## Schema findings

Relevant tables in the finalized SQLite:

```text
CUPTI_ACTIVITY_KIND_RUNTIME
CUPTI_ACTIVITY_KIND_KERNEL
CUPTI_ACTIVITY_KIND_GRAPH_TRACE
CUDA_GRAPH_EVENTS
NVTX_EVENTS
StringIds
OSRT_API
```

Important fields:

- `CUPTI_ACTIVITY_KIND_RUNTIME`: `start`, `end`, `correlationId`, `nameId`
- `CUPTI_ACTIVITY_KIND_KERNEL`: `start`, `end`, `correlationId`, `graphNodeId`, `demangledName`, `shortName`, `launchType`
- `CUPTI_ACTIVITY_KIND_GRAPH_TRACE`: `start`, `end`, `correlationId`, `graphId`, `graphExecId`
- `CUDA_GRAPH_EVENTS`: `start`, `end`, `eventClass`, `nameId`, `graphId`, `graphExecId`
- `StringIds`: `id`, `value`

The capture contains 59,585 kernel rows and 289 graph-trace rows. Every kernel row has `launchType=1`, but `graphNodeId` is NULL for all 59,585 rows. There is no graph-node definition table in this exported SQLite schema.

`CUDA_GRAPH_EVENTS` contains graph creation/exec-creation events, but not graph node topology or per-node execution timestamps. `StringIds` resolves the runtime and kernel symbols, including `cudaGraphLaunch_v10000`, Marlin, CUTLASS, and Mamba symbols.

## Representative replay reconstruction

Representative graph replay:

```text
graph trace start = 59,186,787,030 ns
graph trace end   = 59,204,808,708 ns
correlationId     = 682300
graphId           = 1
graphExecId       = 2
```

The graph trace correlates to this runtime launch record:

```text
start=59,175,023,323 ns
end=59,175,295,748 ns
correlationId=682300
name=cudaStreamIsCapturing_v10000
```

The actual marked-interval graph launches use the same path. For example:

```sql
SELECT r.start, r.end, r.correlationId, r.nameId, s.value
FROM CUPTI_ACTIVITY_KIND_RUNTIME r
LEFT JOIN StringIds s ON r.nameId = s.id
WHERE s.value = 'cudaGraphLaunch_v10000'
  AND r.start < 59775508001
  AND r.end > 59187178779
ORDER BY r.start;
```

This returns 32 `cudaGraphLaunch_v10000` calls within/overlapping the marked interval, with graph-launch correlations such as 682827, 683353, 683873, etc. The graph traces identify `graphId=1`, `graphExecId=2`.

However, joining those graph-launch correlations to `CUPTI_ACTIVITY_KIND_KERNEL.correlationId` does not recover the graph's underlying kernels. The representative graph trace correlation has no matching kernel rows, and the kernel rows overlapping the representative replay are only six setup/index/scatter-like rows. None has a non-NULL `graphNodeId`.

## Kernel symbol validation

`StringIds` proves that the capture contains recognizable symbols elsewhere:

```text
Marlin symbols: present in full capture
CUTLASS/BF16 GEMM symbols: present in full capture
Mamba chunk_scan symbols: present in full capture
cudaGraphLaunch_v10000: present
```

For the exact marked interval `[59187178779, 59775508001]`, direct kernel rows recover only partial activity and no Marlin/CUTLASS production rows. This is not accepted as component accounting.

## Marked interval findings

The marker interval remains:

```text
BEGIN = 59,187,178,779 ns
END   = 59,775,508,001 ns
duration = 588,329,222 ns
```

The existing graph-trace reconstruction remains valid:

```text
32 cudaGraphLaunch runtime calls
33 overlapping graph traces
graph-trace union = 585.080870 ms
coverage = 99.4479%
```

But the graph trace is an aggregate replay envelope. It does not expose the underlying per-node kernel execution timing in this SQLite export.

## Accounting status

Not recoverable from this capture:

```text
GPU kernel busy %: NOT RECOVERABLE
GPU idle/runtime gap %: NOT RECOVERABLE
Marlin %: NOT RECOVERABLE
other BF16/CUTLASS GEMM %: NOT RECOVERABLE
Mamba %: NOT RECOVERABLE
Attention %: NOT RECOVERABLE
misc %: NOT RECOVERABLE
```

The following must not be substituted:

- graph-trace union as GPU kernel busy time;
- static/full-capture symbol presence as marked-interval execution;
- the approximately 2.63 ms direct kernel-row union as actual GPU utilization;
- graph topology inferred from the count or duration of graph traces.

## Decision

```text
T012-R4: PARTIAL
SAME-INTERVAL KERNEL TIMING: NOT RECOVERABLE FROM THIS CAPTURE
```

The schema/correlation path is partially established: NVTX → interval, graph trace → `(graphId, graphExecId, correlationId)`, and runtime → `cudaGraphLaunch` are recoverable. The missing link is graph-exec/node → per-replay underlying kernel activity with trustworthy timestamps. This export has neither graph-node metadata nor graph-node execution timing, and kernel `graphNodeId` is NULL throughout.

A new capture would be necessary for full same-interval component accounting, but only if it collects a representation that exposes graph-node/per-node kernel execution timing; merely repeating the same capture options is not sufficient.

## Next recommendation

Authorize one new capture-design review to identify an Nsight configuration/API trace that exposes CUDA graph node execution timing before any further workload run; do not rerun T012 or change production behavior until that capability is verified.
