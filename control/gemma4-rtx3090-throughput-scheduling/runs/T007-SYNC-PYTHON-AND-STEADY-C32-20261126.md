# T007 synchronization attribution and C32 diagnostics — 2026-11-26

## Earlier valid sync capture

The first bounded full-tier C-8 capture, `/data/sglang-hicache/gemma4/runs/20261126T-t007-sync-python-backtrace-c8/`, is the valid source for Python callsite attribution: 281 CUDA sync calls / 1.993 s map to `update_sliding_window_buffer` scalar-length reads; 138 / 1.096 s map to necessary SWA padding/tombstone filtering in `free_swa`/`free_group_end`. Details and line locations are retained in that run's `sync-python-findings.txt`. No production synchronization was removed.

## Follow-up native callchain capture (incomplete benchmark)

Run `/data/sglang-hicache/gemma4/runs/20261126T-t007-sync-callsite-python-sampling-r2/`; source HEAD `cb0132a6f6b0875b07eea6a911e02ef053d87f83` (same as origin at launch), full-tier C-8 workload, `--cudabacktrace=sync --python-backtrace=cuda --python-sampling=true`, profiling window 02:38:22–02:40:29 UTC. CPU IP/backtrace sampling was explicitly unsupported and disabled by Nsight; no Python sampling tables were emitted. Thus native callchains and scheduler NVTX are usable, but this run does not provide Python-level attribution.

The benchmark did **not** complete the requested 800 queries: it exited 0 after its bounded 7200-second timeout, with 424 complete, 40 failed, and a reported 622.42s benchmark duration / 157.94 profiled TPS. Do not use its TPS as acceptance or as a matched C-8 outcome. The wrapper terminated; GPU returned to 1 MiB/0%, port 31401 is clear, Nsight sessions/processes are absent, and the lock is free.

The preserved Nsight report and SQLite export have SHA256 `0d3ca549925fd99cf0755b92f91c8c866ca54c45d1196cf75844c06dcf025ad8` and `19923d13b02ec51a267c60efe9c97f92f447a47ae0081b7b951c9f69da1a6870`, respectively. In the 127s capture window, all 1,423 scheduler-thread `cudaStreamSynchronize` calls (11.93s accumulated API wall) align with scheduler NVTX ranges: 956 calls / 6.628s inside `scheduler.run_batch`, 56 / 4.529s inside `scheduler.process_batch_result`, 411 / 0.773s inside `scheduler.get_next_batch_to_run`. Native callchain signatures divide the calls into:

- `_local_scalar_dense_cuda_impl<int>`: 956 / 6.628s, all in `run_batch`.
- `nonzero_cuda_out_impl<bool>`: 467 / 5.302s, split across `process_batch_result` and `get_next_batch_to_run`.

There were also 1,489 `cudaEventSynchronize` calls / 2.991s; native stack is `THCPEvent_synchronize`. CPU sampling was unavailable, so these cannot be mapped to Python source lines by this capture. These are inclusive API-wait totals, not additive GPU busy time or proof that removing the calls is safe. The earlier valid Python capture identifies the same broad SWA scalar-read and padding-filter classes. Preserve CPU length authority constraints (graph-batch CPU mirrors may be stale), slot-0 tombstone protection, and stream/WAR dependencies. No runtime optimization is justified by this evidence alone.

`control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh` has a minimal uncommitted addition to pass optional Nsight start-time flags (`T007_NSYS_START_EXTRA`), used for this capture. `bash -n` passed; this worktree change is retained for review and is not a runtime optimization.

## C32 diagnostics

Run `/data/sglang-hicache/gemma4/runs/20261126T-t007-steady-c32-tokenfix/`, wrapper exit 0, server on port 31406 cleaned up and GPU lock released. Frozen T007 service configuration reused; diagnostic prompts 1024 tokens, outputs 256 tokens, 32 continuously replenished clients. Source head `6fc0e15304`.

Initial harness report is invalid for output TPS: `/generate` returns decoded `text` without token usage in this path, and the driver accidentally counted response-character length. For rotating requests, JSON reported 3,891.19 “TPS” based on 1,216 chars/request; official request metrics show exactly 256 completion tokens/request. Corrected rotating-window count is 288 requests × 256 = 73,728 output tokens / 90 s = **819.2 output TPS**, with 0 errors (median latency 9.29 s, p95 9.91 s). The cached window had the same character-count defect; its reported 8,430.91 is not a valid output-TPS figure. Request telemetry and harness bug are preserved; do not present either initial TPS as token throughput.

The driver was corrected to count only an authoritative completion-token field or `output_ids`, otherwise record a failed sample rather than infer tokens from text. Syntax compilation passed. Token-corrected rerun `/data/sglang-hicache/gemma4/runs/20261126T-t007-steady-c32-tokenfix/` completed both windows, 0 errors, wrapper exit 0, cleanup confirmed:

- Rotating-suffix short-context, 1024 input / 256 output, 32 continuously replenished clients: 288 complete requests, 73,728 output tokens in 90 s = **819.20 output TPS**, request rate 3.20/s, latency p50/p95 9.20/9.87 s, mean in-flight 28.9.
- Fully cached prompt, same request lengths/clients: 416 complete requests, 106,496 output tokens in 60 s = **1,774.92 output TPS**, request rate 6.93/s, latency p50/p95 4.68/5.18 s, mean in-flight 31.18.

These are short-context diagnostic rates under a different request shape, not a ceiling directly transferable to the original C-8 workload and not official C-8 acceptance. Workload is diagnostic only and does not affect C-8 acceptance.
