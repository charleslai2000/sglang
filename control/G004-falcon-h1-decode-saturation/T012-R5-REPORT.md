# G004 / T012-R5 — CUDA Graph Node Timing Capture-Design Review

## Result

```text
T012-R5: PASS
CUDA GRAPH NODE TIMING: CAPTUREABLE
```

This was a tool-capability review only. No Falcon-H1 serving, B=16 workload, production-code modification, or new serving capture was performed.

## Environment

```text
Nsight Systems: 2025.1.3.140-251335620677v0
CUDA runtime:   12.9 (PyTorch 2.13.0+cu129)
Driver:         580.178.04
GPU:            NVIDIA GeForce RTX 3090
```

The requested 2025.2.1 tool was not installed; the actual local binary is 2025.1.3. The review and conclusion apply to this installed version.

`nsys status --environment` reported CPU sampling restrictions (`perf_event_open` unavailable / paranoid level 4), but CPU sampling was disabled for these probes and this did not prevent CUDA tracing.

## Nsight capability

The local `nsys profile --help=cuda` explicitly supports:

```text
--cuda-graph-trace=<granularity>[:<launch origin>]
```

Supported granularity values:

- `graph`: collect graph replay envelopes; node activities are not collected.
- `node`: collect node activities; whole-graph traces are not collected.

The tested control configuration used:

```text
--cuda-graph-trace=graph
```

The node configuration used exactly one additional graph option:

```text
--cuda-graph-trace=node
```

Both used the T012-R2 tracing baseline:

```text
--trace=cuda,nvtx,osrt
--sample=none
--cpuctxsw=none
--cuda-event-trace=true
--export=sqlite
```

## Synthetic graph probe

The independent probe created one CUDA graph containing three recognizable operations:

```text
input initialization outside graph
CUDA graph:
  a + b
  relu
  multiply by scalar
5 graph replays
NVTX begin/end around the replay loop
```

### Control: graph granularity

Artifact:

```text
runs/t012-r5/control/probe.nsys-rep
runs/t012-r5/control/probe.sqlite
```

Observed behavior:

- graph replay envelope: available
- node activity table: absent
- kernel `graphNodeId`: NULL
- underlying kernel timing: not correlated to graph nodes

This reproduces the T012-R3 limitation.

### Node: node granularity

Artifact:

```text
runs/t012-r5/node/probe.nsys-rep
runs/t012-r5/node/probe.sqlite
```

The exported SQLite contains a new table absent from the control export:

```text
CUDA_GRAPH_NODE_EVENTS
```

Schema:

```text
start
end
eventClass
globalTid
nameId
graphNodeId
originalGraphNodeId
```

The probe produced 10 node events, including graph-node IDs:

```text
4294967296
4294967297
4294967298
8589934592
8589934593
8589934594
8589934595
```

The kernel table contained 17 rows. Kernel rows for graph replay had non-NULL `graphNodeId`, for example:

```text
kernel graphNodeId = 8589934592
kernel start/end = 2902173245 / 2902185053
kernel symbol = vectorized_elementwise_kernel<...CUDAFunctor_add<float>...>
```

The node events table contains the corresponding node IDs, and `StringIds` resolves the node event `nameId`. The probe also recovered the NVTX markers in `NVTX_EVENTS.text`:

```text
G004_T012_R5_BEGIN
G004_T012_R5_END
```

Thus the node-granularity export exposes both:

```text
replay/node metadata: CUDA_GRAPH_NODE_EVENTS
underlying kernel timing: CUPTI_ACTIVITY_KIND_KERNEL.start/end
join key: CUPTI_ACTIVITY_KIND_KERNEL.graphNodeId
```

The graph node IDs are replay-qualified (the high 32-bit portion changes between graph executions), while `originalGraphNodeId` provides the corresponding original graph node identity where available. This is sufficient to distinguish repeated node executions and join them to kernel rows.

## Exact recovery path

For a future capture, the intended offline joins are:

```sql
-- graph-node activity and node identity
SELECT start, end, graphNodeId, originalGraphNodeId, nameId
FROM CUDA_GRAPH_NODE_EVENTS
ORDER BY start;
```

```sql
-- underlying kernel execution and graph node
SELECT start, end, correlationId, graphNodeId, demangledName, shortName
FROM CUPTI_ACTIVITY_KIND_KERNEL
WHERE graphNodeId IS NOT NULL
ORDER BY start;
```

Resolve kernel names with:

```sql
SELECT k.start, k.end, k.graphNodeId, s.value AS kernel_name
FROM CUPTI_ACTIVITY_KIND_KERNEL k
LEFT JOIN StringIds s ON k.demangledName = s.id
WHERE k.graphNodeId IS NOT NULL
ORDER BY k.start;
```

The validated relationship is:

```text
NVTX interval
  → CUDA_GRAPH_NODE_EVENTS.start/end
  → graphNodeId / originalGraphNodeId
  → CUPTI_ACTIVITY_KIND_KERNEL.graphNodeId
  → kernel start/end + StringIds.demangledName
```

## Final classification

```text
CUDA GRAPH NODE TIMING:
CAPTUREABLE
```

The prior T012-R3 limitation was caused by using graph-level tracing. The local Nsight version supports node-level tracing, and the node-level synthetic probe proves that finalized SQLite can expose graph-node IDs and per-kernel execution timestamps.

## Next recommendation

Run one final authorized Falcon-H1 T012 capture with the exact additional option `--cuda-graph-trace=node` while retaining the validated T012-R2 options; do not execute that capture in this stage.
