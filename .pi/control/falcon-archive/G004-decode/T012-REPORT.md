# G004 / T012 — Steady-Decode Timeline Closure

## Verdict

```text
T012: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

The corrected capture finalized and is readable, but the expected `T012_*` NVTX marker strings are absent from the extracted Nsight Systems SQLite. Therefore no same-marker-interval gap or component accounting is claimed.

## Prior failure diagnosis

The previous attempt retained only `marked.json` and no `.nsys-rep`. Its orchestration used a background capture that was terminated/cleaned up before Nsight Systems completed report conversion. There was no evidence of a completed `.qdstrm` conversion or readable report, so the prior `code null`/workload completion could not establish profiler success.

## Corrected capture

Run artifact:

```text
runs/t012-r1/B16/server.nsys-rep
runs/t012-r1/B16/server.sqlite
runs/t012-r1/B16/marked.json
```

Capture finalization evidence:

- workload: B=16, 48/48 requests, 0 errors, 12,288 output tokens
- serving logs show `Generating '/tmp/nsys-report-97ef.qdstrm'`, conversion reaching 100%, and `Generated: .../server.nsys-rep`
- finalized report size: approximately 15 MiB
- offline `nsys stats --report cuda_gpu_kern_sum` succeeded and generated SQLite/CSV output
- no matching serving or Nsight process remained after completion

The wrapper command returned 137 during the subsequent stats/export stage, after report generation. This does not invalidate the already generated report; offline stats was rerun independently and succeeded.

## Marker/accounting status

The temporary marker was installed only for this run under the existing condition:

```text
actual batch size = 16
waiting queue = empty
```

However, searching the finalized SQLite's NVTX/string tables found no `T012_*` marker text. Consequently:

```text
marked interval start/end: unavailable
same-interval GPU kernel busy: unavailable
same-interval GPU idle/runtime gap: unavailable
same-interval CUDA graph cadence: unavailable
same-interval component accounting: unavailable
```

The report is valid as a whole-process capture, and its aggregate kernel summary is consistent with prior evidence (main Marlin approximately 48.1% of listed GPU kernel time; the next BF16/CUTLASS GEMM approximately 12.2%; Mamba scan/state kernels are also prominent). Because this is not a marked steady interval, it is not used to close T011 or classify the system-level root cause.

## Production changes

```text
NONE
```

The temporary marker was reverted after the run. `git diff` for the marker source is empty. No scheduler, CUDA graph, kernel, model, quantization, or runtime behavior change remains.

## Final status

```text
T012: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

## Next recommendation

Do not optimize or change production behavior. If runtime-gap attribution is still required, authorize one follow-up instrumentation-only capture that uses a marker representation verified in a tiny Nsight smoke test before the full workload; otherwise close G004 with the already established GPU-kernel-distributed/Marlin-dominant whole-process evidence while explicitly leaving the steady-decode gap unquantified.
