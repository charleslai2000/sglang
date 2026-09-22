# G004 / T012-R2 — NVTX Marker Representation Smoke Test

## Result

```text
T012-R2: PASS
MARKER OBSERVABILITY: PASS
```

No full B=16 workload, serving run, attribution, optimization, or production behavior change was performed.

## Marker mechanisms tested

All three minimal forms were tested independently with the same CUDA workload:

1. `torch.cuda.nvtx.mark("G004_T012_SMOKE_BEGIN")` followed by `torch.cuda.nvtx.mark("G004_T012_SMOKE_END")`
2. `torch.cuda.nvtx.range_push("G004_T012_SMOKE_BEGIN")` / `torch.cuda.nvtx.range_pop()`
3. `torch.cuda.nvtx.range_start("G004_T012_SMOKE_BEGIN")` / `torch.cuda.nvtx.range_end(id)`

No explicit NVTX domain was needed. The simplest working form is the original marker form, `torch.cuda.nvtx.mark`, with separate begin/end text marks.

## Nsight capture

Command/options used for each short capture:

```text
nsys profile --force-overwrite=true \
  --output=<run>/smoke \
  --trace=cuda,nvtx,osrt \
  --sample=none --cpuctxsw=none --cuda-event-trace=true \
  /home/ubuntu/venv/bin/python /tmp/t012_marker_smoke.py <form>
```

Reports and exported SQLite files:

```text
runs/t012-r2/mark/smoke.nsys-rep
runs/t012-r2/mark/smoke.sqlite
runs/t012-r2/pushpop/smoke.nsys-rep
runs/t012-r2/pushpop/smoke.sqlite
runs/t012-r2/startend/smoke.nsys-rep
runs/t012-r2/startend/smoke.sqlite
```

All three native reports finalized successfully and all three were readable by offline `nsys stats --report cuda_gpu_kern_sum`, which generated the corresponding SQLite and CSV output. Report sizes were 427,078 bytes (`mark`), 429,111 bytes (`pushpop`), and 431,559 bytes (`startend`).

## SQLite representation

The working and recommended representation is direct text in `NVTX_EVENTS.text`:

```sql
SELECT start, end, eventType, text, globalTid, domainId
FROM NVTX_EVENTS
WHERE text IN ('G004_T012_SMOKE_BEGIN', 'G004_T012_SMOKE_END')
ORDER BY start;
```

Recovered `mark` rows:

```text
(start=2857397278, end=NULL, eventType=34,
 text='G004_T012_SMOKE_BEGIN', globalTid=317582685034235, domainId=0)
(start=3134839967, end=NULL, eventType=34,
 text='G004_T012_SMOKE_END', globalTid=317582685034235, domainId=0)
```

The `range_push/pop` form was recovered as one `NVTX_EVENTS` row with `start=2801653459`, `end=3064703914`, `eventType=59`, and `text='G004_T012_SMOKE_BEGIN'`. The `range_start/end` form was recovered as one row with `start=2843946839`, `end=3108819712`, `eventType=60`, `rangeId=1`, and `text='G004_T012_SMOKE_BEGIN'`.

`StringIds` exists with columns `(id, value)`, but these smoke markers were stored directly in `NVTX_EVENTS.text`; no string-table join is required for the validated form. `CUDA_GRAPH_EVENTS` was present in the exported schema but was not needed for marker recovery.

## Exact conclusion

The original marker API is observable in this Nsight Systems configuration. The T012-R1 absence was therefore not a fundamental NVTX/Nsight limitation; it remains specific to the serving capture path, marker emission context, or capture/report data path and must be checked in a subsequent authorized capture.

## Production state

No production source was modified by this smoke test. No scheduler, CUDA graph, kernel, serving, or attribution behavior was changed.

## Recommendation

Run one final authorized T012-R3 B=16 marked capture using the validated `torch.cuda.nvtx.mark` begin/end form and the same finalized-report lifecycle. Do not execute T012-R3 as part of this stage.
