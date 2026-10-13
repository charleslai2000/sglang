# T002 CUDA 12.9 CUPTI Range profiler

This optional profiling-only extension vendors the NVIDIA CUDA 12.9 CUPTI sample `profilerhost_util` sources (`Metric.cpp`, `List.cpp`, `Eval.cpp` and their headers) and calls CUPTI Range Profiling APIs against the current CUDA context. NVIDIA retains copyright in those files; see their source headers. The extension is not imported unless `SGLANG_T002_CUPTI=1`.

Build in the repo's active Python environment with CUDA 12.9 installed:

```bash
cd python
python -m sglang.srt.utils.cupti_range.build build_ext --inplace
```

The service process needs NVIDIA profiling permissions (GA102 test host used sudo). CUPTI is initialized only after graph capture, from the worker's current PyTorch primary context. Sampling is capped at 8192 user ranges. The isolated Falcon harness requires one process and one fresh CUPTI profiling window per workload/trial; do not reuse a stopped profiler object/counter image. Core metric configuration is single pass; UserReplay submits each real forward once. `finalize()` is explicit end-of-window operation: it performs the bounded measurement-finalization device synchronization, decodes CUPTI data and reports range/drop/pass counts and per-range values. It is used only by the offline Harness, never by the ordinary online inference path.
