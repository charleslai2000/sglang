# T007 sync attribution and short-context C32 diagnostic — 2026-11-26

## CUDA synchronization attribution

Run artifacts: `/data/sglang-hicache/gemma4/runs/20261126T-t007-sync-python-backtrace-c8/`. Source HEAD was `6fc0e153043e60fdd65ebae850343f5b5c8b2213`; no runtime source edits were made. Nsight captured 20 seconds from a full C-8 profile. The profiled run completed 800/800, zero failed at 553.09 official TPS, but this is **profiled and is not an acceptance measurement**.

Nsight's Python-backtrace payloads were decoded from the report JSON export and matched on the scheduler global thread/time to CUDA runtime sync calls and native CUDA callchains:

- 281 CUDA sync calls / 1.993 s in `at::native::(anonymous namespace)::_local_scalar_dense_cuda_impl<int>` map to `update_sliding_window_buffer` in `python/sglang/srt/layers/attention/triton_backend.py` (267 at line 2202, 14 at line 2184).
- 138 calls / 1.096 s in `at::native::nonzero_cuda_out_impl<bool>` map to `SWATokenToKVPoolAllocator.free_swa` in `python/sglang/srt/mem_cache/allocator/swa.py:382` (125), or `free_group_end:412` (13).

These two classes are 3.089 s of the 3.168 s host time in 508 CUDA sync calls with recorded callchains. The prior estimate that `get_cpu_copy()` was the prominent Python caller is disproven for this scheduler-thread sample: the captured owners are SWA window metadata length conversion and SWA padding filtering.

The first candidate reads the prefix-sum end from device to size/slice a variable-length SWA window. There is a possible CPU-length mirror in some batch paths, but the backend explicitly documents `seq_lens_cpu` can be stale for gpu-only graph batches; only a mode-matched authoritative mirror can safely replace this read. The second candidate's `>0` filter is required because zero is a reserved padding/tombstone mapping and freeing it corrupts the SWA free list. Do not remove either dependency by assumption. No runtime optimization is justified/implemented here.

## C32 continuous-load results

Run: `/data/sglang-hicache/gemma4/runs/20261126T-t007-steady-c32/`, wrapper exit 0, launched/cleaned its server on port 31406 and released the GPU lock. Frozen T007 service configuration reused; diagnostic prompts 1024 tokens, outputs 256 tokens, 32 continuously replenished clients. Source head `6fc0e15304`.

Initial harness report is **invalid for output TPS**: `/generate` returns decoded `text` without token usage in this path, and the driver accidentally counted response-character length as tokens. For rotating requests, JSON reported 3,891.19 “TPS” based on 1,216 chars/request; official request metrics show exactly 256 completion tokens/request. Corrected rotating-window count is 288 requests × 256 = 73,728 output tokens / 90 s = **819.2 output TPS**, with 0 errors (median latency 9.29 s, p95 9.91 s). The cached window had the same character-count defect; its reported 8,430.91 is not a valid output-TPS figure. Request telemetry and harness bug are preserved; do not present either initial TPS as token throughput.

The driver was corrected to count only an authoritative completion-token field or `output_ids`, otherwise record a failed sample rather than infer tokens from text. Syntax compilation passed. Re-measurement is pending; the slow model path/C32 requests are approximately 9–10 s each, so at least a complete 90 s rotating window plus cached window is required. Workload is diagnostic only and does not affect C-8 acceptance.

Wrapper defect corrected before launch so the run-intent file is allowed in the output directory. First launch had stopped before acquiring the lock or starting a GPU service because it required the intent-containing directory to be empty; the corrected invocation passed.
