---
source: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/hicache_design.mdx
discovery: GitHub API directory listing (docs_new/ path in task spec no longer exists on main; corrected to docs/docs/advanced_features/)
library: sglang
topic: hicache-upstream-design-issue32724-session-radix-cache
fetched: 2026-08-30T01:54:02Z
http_status: 200
expires: 2026-09-06T01:54:02Z
official_docs: https://docs.sglang.ai/advanced_features/hicache_design
---

# SGLang HiCache upstream research — Phase-2 design reference

## 1. HiCache official design doc

Source: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache_design.mdx
(raw: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/hicache_design.mdx)

### 1.1 Tier hierarchy (L1/L2/L3)

| Tier | Medium | Scope | Shared across instances? |
|---|---|---|---|
| L1 | GPU memory (HBM) | One inference instance | No |
| L2 | Host memory (CPU DRAM) | One inference instance, own node | No (instance-private, node-local) |
| L3 | Storage backend (`file`, `mooncake`, `hf3fs`, `nixl`, `aibrix`, dynamic/custom) | Whatever the backend spans | Only if backend configured for it |

Verbatim: "L2 is node-local and instance-private. ... A KV cache produced by instance 0 becomes visible to instance 1 only after it reaches L3." Growing `--hicache-ratio`/`--hicache-size` only enlarges each instance's private L2; cross-instance reuse is L3's job.

Metadata: HiRadixTree extends RadixTree — each node records where KV lives (GPU/CPU/L3). L3 metadata is NOT stored/synchronized locally; queried from backend in real time.

### 1.2 Workflow: local match → prefetch (L3→L2) → write-back (L1→L2→L3)

- Local match: traverse HiRadixTree; page-granular when page_size>1; node split on mid-node match termination.
- Prefetch trigger: L3 hit length > threshold (default 256 tokens, configurable via `prefetch_threshold` in `--hicache-storage-backend-extra-config`).
- Prefetch policies: `best_effort` (terminate when GPU can run prefill), `wait_complete` (wait all), `timeout` (stop at completion or timeout).
- Timeout formula (verbatim):
```python
timeout = min(
    prefetch_timeout_max,
    prefetch_timeout_base + prefetch_timeout_per_ki_token * num_token_to_fetch / 1024,
)
```
  Defaults: base=2 s, per_ki_token=0.1 s per 1024 tokens, max=30 s.

### 1.3 Write-back policies — confirms write_back sinks only at eviction

- `write_through`: every access immediately written to next level.
- `write_through_selective`: written back only after access frequency exceeds a threshold (hot data only).
- `write_back`: verbatim — "Data is written back to the next level only when it is evicted from the upper level. This strategy alleviates storage pressure and is suitable for scenarios where storage capacity is limited but memory utilization must be maximized."

→ Directional consistency with observed behavior confirmed: with `write_back`, L1→L2→L3 sinking happens at eviction time, not at access time. L2→L3 only transfers data not already in L3.

### 1.4 Prefetch completion notification (scheduler side)

The design doc does NOT describe an explicit completion callback/event from storage to scheduler. From issue #32724 / PR #32725 (see section 2), the actual mechanism is poll-based:

- Request enqueue triggers `prefetch_from_storage()` → creates a `PrefetchOperation` in `ongoing_prefetch`, background threads transfer L3→host.
- Scheduler confirms completion by calling `check_prefetch_progress(rid)` → `can_terminate_prefetch()`.
- Completion predicate: `operation.completed_tokens == len(operation.hash_value) * page_size`.
- Today `check_prefetch_progress(rid)` is called only inside the FCFS waiting-queue scan when the scan reaches that rid — the coupling problem of #32724.
- Scheduler safe point `check_hicache_events()` (right after `drain_storage_control_queues()`) is where proactive finalization is proposed to hook.

### 1.5 Quota / capacity / concurrency control

- L2 capacity: `--hicache-ratio` (must be >1; L2 pool must exceed device pool) or `--hicache-size` (GB per rank, 1e9 bytes/GB).
- In-flight prefetch budget: `prefetch_tokens_occupied` (mentioned in #32724: un-finalized prefetches pin this budget and host memory, throttling subsequent prefetches).
- Concurrency: PR #31797 adds `prefetch_io_workers` (default 1) for storage→host transfers.
- No admission-control-class API documented (no per-tenant quota, no queue admission gate) in the design doc.

### 1.6 Multi-rank sync and transfer optimizations

- `all_reduce(op=min)` for L3-hit-count consensus (prefetch threshold judgment) and for final prefix-length consensus after prefetch ends.
- Zero-copy L2→L3 transfers (pass addresses/sizes); page-granular L3 layout (`layer_first` / `page_first` / `page_first_direct`).
- CPU→GPU: compute-transfer overlap (load layer N+1 while computing layer N); GPU-assisted I/O kernels (`--hicache-io-backend kernel`) up to 3x faster than cudaMemcpyAsync.
- MLA write-back: only one rank initiates write-back (data is replicated across TP ranks for MLA).

### 1.7 Other params

`--enable-hierarchical-cache` (required), `--page-size`, `--hicache-storage-prefetch-policy {best_effort,wait_complete,timeout}` (timeout recommended for production), `--hicache-write-policy {write_back,write_through,write_through_selective}`, `--hicache-io-backend {direct,kernel}`, `--hicache-mem-layout`, `--hicache-storage-backend {file,mooncake,hf3fs,nixl,aibrix,dynamic}`, `--enable-lmcache` (alternative). PD-disaggregation: HiCache can be enabled on prefill and decode nodes; decode output can also be written back to L3.

## 2. Issue #32724 — prefetch finalization delay under load

Source: https://github.com/sgl-project/sglang/issues/32724 (fetched via https://api.github.com/repos/sgl-project/sglang/issues/32724)

- Title: "[Perf] HiCache storage prefetch finalization delay can cause long TTFT under load"
- State: **open** (created 2026-07-29, 0 comments). Author: cfbdsirlijun-maker.
- Root cause (verbatim): "a storage prefetch for a waiting request is only finalized inside the scheduler's waiting-queue scan: the scheduler walks the waiting queue in FCFS order and calls `check_prefetch_progress(rid)` when it reaches that request." → the *scheduler_ready* confirmation is coupled to the request's FCFS position. When prefill token budget is saturated by earlier requests, the scan stops before reaching later rids, so an IO-completed prefetch stays unfinalized (host radix insertion, host memory release, `ongoing_prefetch` cleanup all pending) for seconds.
- Measured impact: 4P1D Mooncake: storage IO ~91 ms, scheduler-side finalization lag ~2.4 s (>95% of end-to-end prefetch latency was FCFS-scan wait). 4P2D: `io_done_to_scheduler_ready_ms` p95 8.53 s / p99 22.16 s, alone 56.2% of total HiCache scheduler-ready time (`io_ms` only 11.0%); `finalize_ms` itself is tiny (p50 3.36 ms). Un-finalized ops also pin host memory + `prefetch_tokens_occupied` budget, throttling subsequent prefetches.
- Proposed fix (in issue, verbatim summary): decouple finalization from FCFS position — "At the existing scheduler safe point `check_hicache_events()` (right after `drain_storage_control_queues()`), proactively scan `ongoing_prefetch` and, for operations that are locally ready — IO completed (`completed_tokens == len(hash_value) * page_size`), already terminated, host indices not yet committed, or timed out under the `timeout` policy — call the existing `check_prefetch_progress(req_id)`." Cross-rank: sort candidates by `req_id`, combine local readiness with MIN all-reduce over ATTN TP/CP groups so all ranks finalize the same set in the same order. Admission semantics unchanged.
- Fix PR: **#32725** "perf(hicache): proactively finalize completed prefetch at scheduler safe point" — open, unmerged (created 2026-07-29; +44 lines in `python/sglang/srt/mem_cache/hiradix_cache.py`; adds `_can_check_prefetch_progress_proactively(operation)` + `check_ready_prefetch_progress()` called from `check_hicache_events()` after `drain_storage_control_queues()`; reported result: io-done→scheduler-ready gap reduced from ~2.4 s to next `check_hicache_events()` round in 4P1D Mooncake).
- Related: #28047 (same symptom, Mooncake), #21880 (prefetch lifecycle / termination policy), vllm-project/vllm#41784 (analogous vLLM KV-connector late-completion observation). PR #34568 (open) fixes the related PP-prefill variant: fold HiCache readiness into the two-pass bootstrap consensus (`_pp_filter_hicache_ready_rids()`), so a request is admitted only when every PP stage is ready — avoids deadlock from per-stage readiness skew. Issue #30760: TP-only deadlock from mismatched `all_reduce` call counts in `can_terminate_prefetch` (rank divergence in loop exit).

## 3. Session-aware radix cache

Source: https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/session_radix_cache.mdx
(raw: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/session_radix_cache.mdx)

- Enables: `SGLANG_ENABLE_UNIFIED_RADIX_TREE=1 python3 -m sglang.launch_server --enable-session-radix-cache`. Implemented only by `UnifiedRadixCache`.
- Mechanism: app passes the same top-level `session_id` on every request; when a request finishes, SGLang automatically registers its reusable cache leaves under that session_id (reference-only; no `/open_session` needed; no context reconstruction — the full prompt must still be sent). `/close_session` removes references but does not free KV immediately — KV returns to normal eviction order.
- Eviction preference (verbatim): "unreferenced nodes first, then referenced nodes with fewer session references, then the configured policy such as LRU" (Full attention component; SWA/Mamba use two LRU passes: unreferenced first, then referenced). Same preference on device and host eviction.
- Soft vs hard pin (verbatim): "Session references are soft protection, not memory pins. Referenced KV can still be evicted when reclaiming unreferenced KV is insufficient." → No hard-pin semantics exist in this doc; soft references only affect eviction order.
- Component cascade rules still apply: evicting an internal Full node also evicts its SWA/Mamba data; SWA eviction also evicts Mamba; Mamba eviction affects only Mamba.

## 4. Phase-2 reusability judgments (P2-1 / P2-2 / P2-4)

- **P2-1 (prefetch completion notification)**: Upstream has no callback/event mechanism; completion is polled via `check_prefetch_progress(rid)` inside the FCFS scan. PR #32725's `check_ready_prefetch_progress()` at `check_hicache_events()` is the upstream-sanctioned pattern for decoupling; design should adopt safe-point proactive finalization with req_id-sorted MIN all-reduce for TP/CP/PP consistency (PP variant per #34568). Treat #32725 as reference design; do not rely on it as merged code (open, unmerged).
- **P2-2 (write-back timing)**: Design doc explicitly defines `write_back` as eviction-time sinking — consistent with observed behavior direction. `write_through_selective` (hit-count threshold) is the upstream primitive for hot-data-only sinking if a middle ground is needed.
- **P2-4 (fairness)**: Session radix cache is a viable upstream mechanism: soft-reference eviction preference (unreferenced → fewer session references → LRU) gives active sessions protection without reservations, and requires only `session_id` passthrough + `--enable-session-radix-cache` on `UnifiedRadixCache`. Caveats: (a) it is an eviction-order preference, not an admission/fairness scheduler — it does not bound a session's share of capacity or batch slots; (b) single top-level session_id per request (no multi-session token-scope granularity documented); (c) requires UnifiedRadixCache and client cooperation; (d) no hard pin exists — if P2-4 needs guaranteed retention, upstream has no mechanism; custom extension required.

## Sources

- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache_design.mdx (raw: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/hicache_design.mdx)
- https://github.com/sgl-project/sglang/issues/32724 (API: https://api.github.com/repos/sgl-project/sglang/issues/32724)
- https://github.com/sgl-project/sglang/pull/32725 (API: https://api.github.com/repos/sgl-project/sglang/pulls/32725)
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/session_radix_cache.mdx (raw: https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/session_radix_cache.mdx)
- https://github.com/sgl-project/sglang/pull/34568 (API: https://api.github.com/repos/sgl-project/sglang/pulls/34568)
- https://github.com/sgl-project/sglang/issues/30760
- https://docs.sglang.ai (official docs site root)

Not included: PR #9397 / #8372 / #23309 / #31797 details beyond one-line mentions (older race/cleanup/timeout/IO-worker changes, tangential); vLLM issue #41784 body (only referenced); hicache_best_practices.mdx and hicache_storage_runtime_attach_detach.mdx (not asked).
