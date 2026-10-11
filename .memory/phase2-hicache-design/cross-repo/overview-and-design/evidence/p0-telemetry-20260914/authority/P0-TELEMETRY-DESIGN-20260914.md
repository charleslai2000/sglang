# P0 Telemetry minimal design audit

- Task: `LOCAL-P0-TELEMETRY-DESIGN-AUDIT-20260914`
- Date: 2026-09-14
- Role: architect (recommendation; not self-approval)
- Source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- HEAD: `993ef8e5c3a6448aff2e752cf66cc45deadab59a`
- Branch: `3060-12g-qwen35-4b`
- Mode: read-only audit. No source edit, GPU/server start, workload interruption, or telemetry activation was performed.

## 1. Decision

**Recommend one bounded P0 implementation packet, subject to orchestrator acceptance.** The implementation can reuse scheduler-owned request state, existing HiCache terminal facts, existing Prometheus collectors, and the opt-in request metrics file exporter. It does not require a new thread, queue, service, storage format, request authority, GPU synchronization, or request-ID Prometheus label.

The packet is bounded only if it obeys these constraints:

1. The telemetry is observational and cannot influence Ready Horizon (RH), admission, transfer, restore, eviction, or retry decisions.
2. Prometheus receives only process/rank labels already owned by the collectors plus bounded enums named below. It receives no `rid`, request/session/build/attempt ID, cache key, node ID, storage key, or free-form reason.
3. Per-request identity and exact timestamps live only in the already opt-in request JSONL export. No new JSONL writer, marker file, producer thread, or `/tmp` probe is introduced.
4. Tier counts are logical prompt-token coverage. Mamba state units are never added to KV token counts.
5. Percentiles are queried from cumulative Prometheus histograms; the runtime does not publish p50/p95/p99 gauges or maintain quantile windows.
6. A durable-prefix value is reported only from same-request, same-attempt, same-generation authoritative storage-query/finalize state. Unknown is `null`, never zero and never inferred from global L3 events.

If preserving the current response `meta_info` byte-for-byte even when `--export-metrics-to-file` is enabled is a hard requirement, the per-request JSONL part is **BLOCKED pending a separate internal-output-envelope design**. Adding a nested opt-in `hicache_telemetry` field to `meta_info` is the smallest closure, but it is an opt-in public-output change and must be explicitly accepted.

## 2. Observed facts

### 2.1 RH and admission ownership

- `ready_horizon.py` is a pure scheduler collaborator. It defines strict READY membership as `RestoreState.READY`, `staged_tokens > 0`, and full-prefix residency. It does not own mutable request telemetry.
- The scheduler owns request enqueue order, prefetch attempt identity/origin, restore-state transitions, READY consumption, and successful admission.
- `scheduler.py::_add_request_to_queue` appends the request and calls the optional P2-A enqueue mark.
- `scheduler.py::_feed_restore_terminal` emits `ready_host` after an accepted finalize and already carries attempt/origin and completed KV/aux material.
- `scheduler.py::get_new_batch_prefill` consumes `pop_prefetch_loaded_tokens`, sets `storage_hit_length`, calls `Req.init_next_round_input`, invokes `PrefillAdder.add_one_req`, and emits `admission.v2` only when the request is actually accepted (`AddReqResult.CONTINUE`). This is the authoritative join point for READY versus admission.
- Existing RH logs use `time.monotonic_ns()` for `ready_stage`, `ready_host`, and `admission.v2`. Some older P2-A logs use wall milliseconds and are not safely subtractable from these marks.

### 2.2 HiCache transfer/restore facts

- `UnifiedRadixCache.prefetch_from_storage` creates the storage operation, records requested prompt span, and owns the issue-to-controller handoff.
- `HybridCacheController._storage_hit_query` owns the L3 existence query. It returns a contiguous KV hit in pages and performs sidecar query alignment for hybrid layouts.
- `UnifiedRadixCache._handle_prefetch_result` owns accepted/discarded finalization, commits host material, records completed KV and sidecar units, and publishes loaded tokens for scheduler consumption.
- Hybrid SWA/Mamba restores are all-or-nothing; DSA-style KV-derived sidecars can clamp to the minimum common prefix. Therefore a KV hit alone is insufficient evidence of reusable hybrid state.
- Existing `p2a_timing_probe.py` is environment-gated and default-off. Existing `trace_context.py`/`_t38c_*` JSONL paths are experiment/durability mechanisms with marker files and separate schemas. They are not suitable as the P0 production aggregation owner.

### 2.3 Tier and Mamba/KV accounting facts

- `split_cached_prefix_by_tier(prefix_len, host_hit_len, storage_hit_len)` already defines the exclusive logical split:
  - storage = `min(host_hit_len, storage_hit_len)`;
  - host = `host_hit_len - storage`;
  - device = `max(0, prefix_len - host_hit_len)`.
- `ScheduleBatch.prepare_for_extend` freezes that split once on the first chunk into `cached_tokens_device`, `cached_tokens_host`, and `cached_tokens_storage`; this avoids counting earlier chunks as later cache hits.
- `PrefillAdder` already aggregates first-attempt device/host/storage hits and input compute and excludes reprocessed values from effective metrics.
- Output already exposes `cached_tokens` and optional `cached_tokens_details`. The detail path survives PD metadata transport, detokenizer/tokenizer forwarding, and the request file exporter.
- Mamba allocation is slot/state accounting, not prompt-token accounting. The admission budget may convert a Mamba slot to full-token-equivalent capacity, but that conversion must not be used in a request tier conservation equation.

### 2.4 Existing metrics/export semantics

- `SchedulerMetricsCollector` owns scheduler/request Prometheus metrics. `StorageMetricsCollector` owns storage-thread counters/histograms.
- Prometheus histograms are already the project convention for request stages. Existing `sglang:per_stage_req_latency_seconds{stage=...}` uses a bounded stage label.
- `FileRequestMetricsExporter` writes one JSON object per finished request, appends to hourly files, serializes `meta_info`, skips health checks, and uses an asyncio lock plus `asyncio.to_thread` for file I/O.
- `SchedulerMetricsReporter.reset_metrics()` resets interval/log accumulators. Prometheus counters and histograms themselves are process-lifetime series and are not reset by `/flush_cache`.

## 3. Proposed contract

### 3.1 Clock and join invariants

- All subtractable marks are integer `time.monotonic_ns()` from the same scheduler process.
- Wall time may be exported separately for correlation but must never participate in formulas.
- Join key inside the process: `(rid, session_generation, prefetch_attempt_id)`. `rid` alone is insufficient after retries or session reuse.
- A READY mark is valid only for accepted material (`finalize_result == "accepted"`) and the terminal attempt matching the request's active/last attempt.
- Admission is marked once, only after `AddReqResult.CONTINUE`.
- Retraction/requeue does not overwrite the first admission or tier snapshot. A new prefetch retry may replace an active attempt only through existing scheduler claim ownership.

### 3.2 Required per-request fields

Store a nested `hicache_telemetry` object with schema `hicache_request.v1` in the opt-in request JSONL record:

| Field | Type/unit | Owner / exact meaning |
|---|---|---|
| `schema` | string | Constant `hicache_request.v1`. |
| `rh_eligible` | bool | Scheduler snapshot: RH enabled and request entered RH staging funnel. |
| `prefetch_origin` | bounded string/null | Existing `HiCachePrefetchOrigin` name for the joined attempt. |
| `prefetch_attempt_id` | string/null | Scheduler-owned attempt identity; JSONL only. |
| `enqueue_mono_ns` | int ns/null | First unified-mode queue append; never overwritten. |
| `prefetch_issue_mono_ns` | int ns/null | Immediately after the controller accepts the joined operation and before it is exposed as ongoing. |
| `storage_query_start_mono_ns` | int ns/null | Entry to the joined `_storage_hit_query`. |
| `storage_query_end_mono_ns` | int ns/null | Immediately after all KV/sidecar existence calls return. |
| `ready_mono_ns` | int ns/null | Scheduler consumes accepted terminal completion and transitions the joined attempt to READY. |
| `admission_mono_ns` | int ns/null | Successful `AddReqResult.CONTINUE` for first prefill admission. |
| `prefill_finish_mono_ns` | int ns/null | Existing first prefill completion converted/stored on the same monotonic domain. |
| `prompt_tokens` | int tokens | Terminal prompt-token count already exported. |
| `l1_tokens` | int tokens | Frozen `cached_tokens_device`. |
| `l2_tokens` | int tokens | Frozen `cached_tokens_host`, excluding L3 by existing split. |
| `l3_tokens` | int tokens | Frozen `cached_tokens_storage`, i.e. L3-restored coverage consumed by this request. |
| `newly_prefilled_tokens` | int tokens | `max(0, prompt_tokens - l1_tokens - l2_tokens - l3_tokens)`. Logical distinct prompt positions, not repeated execution work. |
| `durable_reusable_prefix_tokens` | int tokens/null | Longest contiguous same-generation prompt prefix proven reusable in L3 with required hybrid sidecars before admission. Unknown is null. |
| `avoidable_recompute_tokens` | int tokens/null | Formula below; null if durable coverage is not authoritative. |
| `completed_kv_tokens` | int tokens/null | Finalizer-owned joined completion. |
| `required_aux_pools` | bounded string array | Finalizer-owned hybrid requirements. |
| `completed_aux_units` | object<string,int>/null | Sidecar completion in native pool units; never summed into token totals. |
| `hybrid_restore_complete` | bool/null | True iff KV and every required sidecar satisfy that layout's accepted/clamped contract. |
| `rh_prefetch_lead_seconds` | float s/null | Formula below. |
| `rh_ready_slack_seconds` | float s/null | Formula below. |
| `stage_latency_seconds` | object<string,float> | Bounded stages below, present only when both endpoints exist and order is valid. |
| `invalid_reason` | bounded string/null | `attempt_mismatch`, `generation_mismatch`, `clock_order`, `tier_nonconservation`, or `durable_unknown`; never a free-form exception string. |

No token IDs, prompt text, hash, storage key, cache node ID, or raw request payload is added by this telemetry object.

### 3.3 Exact formulas

Let:

- `E` = enqueue monotonic ns;
- `I` = joined prefetch issue monotonic ns;
- `Q0`, `Q1` = storage-query start/end monotonic ns;
- `R` = accepted READY monotonic ns;
- `A` = first successful admission monotonic ns;
- `F` = first prefill-finished monotonic ns;
- `P` = prompt tokens;
- `L1`, `L2`, `L3` = exclusive tier coverage;
- `C = L1 + L2 + L3`;
- `D` = authoritative contiguous durable reusable prefix at the last query/finalize before admission.

Then:

```text
newly_prefilled_tokens = max(0, P - C)
rh_prefetch_lead_seconds = (A - I) / 1e9              if I <= A
rh_ready_slack_seconds = (A - R) / 1e9                if R <= A
storage_query_seconds = (Q1 - Q0) / 1e9               if Q0 <= Q1
prefetch_to_ready_seconds = (R - I) / 1e9             if I <= R
ready_to_admission_seconds = (A - R) / 1e9            if R <= A
admission_to_prefill_finish_seconds = (F - A) / 1e9   if A <= F
avoidable_recompute_tokens = max(0, min(P, D) - C)    if D is authoritative
```

`avoidable_recompute_tokens` is the distinct prompt-prefix overlap that was durably reusable but was not in the admitted cached prefix and therefore had to be freshly prefetched by the model. It is a subset of `newly_prefilled_tokens`. It does not count repeated execution caused by later retraction. If such an execution-cost metric is later required, it must be a separately named counter and must not break the conservation equation.

Required invariants:

```text
0 <= each token field
L1 + L2 + L3 + newly_prefilled_tokens == P
0 <= avoidable_recompute_tokens <= newly_prefilled_tokens
for a successful RH restore: I <= R <= A <= F
hybrid_restore_complete == true before L3 is credited for hybrid state
```

For the normal model path, the unavoidable last-token/page-alignment behavior remains represented in `newly_prefilled_tokens`; do not subtract a magic page or one-token constant.

### 3.4 Prometheus surface (low cardinality)

Add only these series, using existing collector labels. Never add request identity labels.

1. `sglang:hicache_prompt_tokens_total{source="l1|l2|l3|newly_prefilled|avoidable_recompute"}` — Counter, tokens, scheduler collector. `source` is a fixed five-value enum. Observe once per finished request (or once at first stable accounting snapshot with an idempotence flag).
2. `sglang:hicache_rh_prefetch_lead_seconds` — Histogram, seconds, scheduler collector; observe only joined RH attempts with `I <= A`.
3. `sglang:hicache_rh_ready_slack_seconds` — Histogram, seconds, scheduler collector; observe only accepted RH restores with `R <= A`.
4. `sglang:hicache_stage_latency_seconds{stage="storage_query|prefetch_to_ready|ready_to_admission|admission_to_prefill_finish"}` — Histogram, seconds. One metric owner must register the name. Recommended owner is `SchedulerMetricsCollector`; storage query duration is carried as a scalar terminal fact to the scheduler rather than registered by a second collector.
5. `sglang:hicache_telemetry_records_total{outcome="complete|partial|invalid"}` — Counter, records, scheduler collector. Fixed three-value enum; used to prevent silent denominator loss.

Recommended histogram buckets (seconds), shared by the four stage/lead histograms:

```text
0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1,
0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 80
```

Do **not** publish separate p50/p95/p99 metric names. Compute over the requested range, grouped only by bounded existing labels and stage:

```promql
histogram_quantile(0.50, sum by (le, stage) (rate(sglang:hicache_stage_latency_seconds_bucket[5m])))
histogram_quantile(0.95, sum by (le, stage) (rate(sglang:hicache_stage_latency_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le, stage) (rate(sglang:hicache_stage_latency_seconds_bucket[5m])))
```

The exporter may normalize `:` to `_` depending on the Prometheus client exposition; dashboards must use the actual exposition name already followed by this deployment.

### 3.5 Aggregation and reset semantics

- Prometheus counters/histograms: cumulative for one scheduler process lifetime. Process restart is the only reset. `/flush_cache`, RH refill, storage attach/detach, and `SchedulerMetricsReporter.reset_metrics()` must not clear them.
- Multi-process aggregation: retain existing rank/process labels and prometheus-client behavior. Do not aggregate in application code.
- JSONL: exactly one final record per request, append-only, existing hourly rotation. Health-check exclusion remains. Missing lifecycle endpoints are null and make the record `partial`; they are not synthesized.
- Retraction/chunking: tier coverage is frozen on first cache-breakdown computation. JSONL emits once at terminal completion. No chunk-level duplicate records.
- Percentiles: query-window semantics only (for example 5 minutes). No server-side rolling window or percentile reset.

## 4. Ownership and dependency boundaries

| Concern | Owner | Dependency rule |
|---|---|---|
| Attempt/generation join, enqueue/READY/admission marks | Scheduler / `Req` | Cache returns facts; it does not decide joins or admission. |
| Query duration and authoritative durable prefix candidate | `HybridCacheController` operation | Record scalar facts on the existing operation; no direct scheduler mutation from worker threads. |
| Accepted KV/sidecar completion | `UnifiedRadixCache` finalizer | Existing completion handoff remains authoritative. |
| Exclusive L1/L2/L3 split | `split_cached_prefix_by_tier` and first `ScheduleBatch.prepare_for_extend` | One canonical formula; no second splitter in metrics code. |
| Per-request derived object | Output streamer from frozen `Req` facts | No storage/cache lookup during output. |
| Prometheus registration/observation | `SchedulerMetricsCollector` | One registration owner; bounded labels only. |
| JSONL persistence | Existing `FileRequestMetricsExporter` | No new writer/thread/path/rotation policy. |

## 5. Smallest implementation closure

### Required source symbols

1. `python/sglang/srt/managers/schedule_batch.py`
   - `Req.__init__`: bounded telemetry marks/facts and idempotence flags.
   - `split_cached_prefix_by_tier`: reuse unchanged as the canonical tier formula.
   - first cache-breakdown block in `ScheduleBatch.prepare_for_extend`: freeze tier counts; no Mamba-slot addition.
2. `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
   - `PrefetchOperation`: query timestamps/duration and query-result facts.
   - `HybridCacheController._storage_hit_query`: capture one monotonic start/end around existing KV+sidecar query; no logs/files.
3. `python/sglang/srt/mem_cache/unified_radix_cache.py`
   - `prefetch_from_storage`: issue timestamp on the accepted operation and requested span.
   - `_handle_prefetch_result` / `_host_alloc_hybrid_completion`: carry accepted KV/sidecar/query facts through the existing terminal completion.
4. `python/sglang/srt/managers/scheduler.py`
   - `_add_request_to_queue`: first enqueue mark under the production telemetry gate.
   - `_feed_restore_terminal`: validate attempt/generation and freeze READY/finalizer facts.
   - `get_new_batch_prefill`: successful admission mark and prefill accounting observation.
5. `python/sglang/srt/observability/metrics_collector.py`
   - `SchedulerMetricsCollector`: register the five bounded metric families and expose idempotent observation methods.
6. `python/sglang/srt/managers/scheduler_components/output_streamer.py`
   - one pure builder adjacent to `get_cached_tokens_details`; attach the nested object only for the accepted opt-in export behavior.
7. `python/sglang/srt/observability/request_metrics_exporter.py`
   - preserve nested field serialization and document opt-in output behavior; do not add a writer.

### Conditional source symbols

- `python/sglang/srt/observability/req_time_stats.py`: only if `prefill_finish_mono_ns` cannot be copied from the existing first-prefill timestamp without adding a second clock read. Prefer reusing the existing timestamp.
- `python/sglang/srt/managers/io_struct.py` and PD metadata buffers: only if the implementation must support the new RH timing object end-to-end in PD mode in P0. The tier fields already traverse PD. RH itself is unified-mode here; therefore RH timing across PD is structural N/A for this packet.
- `python/sglang/srt/managers/tokenizer_manager.py`: no logic change expected because it already forwards `meta_info` to the exporter. Touch only if an explicitly accepted private exporter-only envelope is chosen.

### Focused test closure

1. New pure CPU test for derivation/join helper (recommended `test/registered/unit/observability/test_hicache_request_telemetry.py`):
   - exact tier conservation and L3 exclusion from L2;
   - Mamba sidecar units do not enter token equation;
   - formula vectors for all-L1, all-L2, all-L3, cold, mixed, final-token/page remainder;
   - avoidable recompute zero/full/partial/unknown and upper bound;
   - valid `I <= R <= A <= F`, missing endpoints, negative ordering, attempt mismatch, generation mismatch;
   - chunk/retraction idempotence.
2. Extend `test/registered/unit/mem_cache/test_p2a_timing_probe.py` only if old probe marks are deliberately reused; recommended packet does not depend on the probe, so leave it unchanged.
3. New/extended HiCache finalizer unit test near existing unified-radix HiCache tests:
   - query scalar facts survive accepted terminal handoff;
   - all-or-nothing Mamba/SWA shortfall yields no L3 credit and no READY observation;
   - DSA clamp credits only common contiguous prefix;
   - stale attempt terminal cannot populate a new attempt.
4. Extend metrics collector DI test with fake Counter/Histogram:
   - exact metric names and bounded label sets;
   - no request ID label;
   - one observation per request; partial/invalid denominator counter;
   - `/flush_cache` reporter reset does not recreate/reset collectors.
5. Extend `test_request_metrics_exporter.py`:
   - nested schema serializes as one JSONL line;
   - nulls and bounded invalid reason are stable;
   - health checks remain excluded;
   - no raw prompt/cache key is introduced by the telemetry builder.

No GPU/server/e2e test is required to validate formulas, registration, ownership, or serialization. A later performance acceptance run may validate representativeness, but it is not part of this implementation packet.

## 6. Risks and mitigations

| Risk class | Assessment | Mitigation / gate |
|---|---|---|
| Public/default behavior | **Conditional material risk.** A nested `meta_info` field changes opt-in output bytes and may become visible to API clients. | Explicitly accept opt-in field behavior, or reroute to a separate private envelope design. Default with file export off must be unchanged. |
| Persistence/format | **Yes, bounded.** JSONL gains versioned fields; append/rotation semantics remain unchanged. | Schema `hicache_request.v1`, additive fields, golden serialization test, no reader migration required. |
| Authority | **No new authority.** Telemetry reads scheduler/cache facts only. | No metric result is read by scheduling or cache policy. |
| Concurrency | **No new concurrency if operation-local facts are used.** Storage query executes off scheduler thread. | Worker writes only its operation; scheduler reads after existing terminal queue/handoff. No shared dict or new lock. |
| Failure semantics | **Must remain unchanged.** Metrics/export failures cannot fail requests or alter restore. | Follow existing collector/export error behavior; derivation returns partial/invalid rather than raising in serving path. |
| Cardinality | Request identity could explode Prometheus. | IDs only in JSONL; fixed `source`, `stage`, `outcome` enums in Prometheus. |
| Double counting | Chunked prefill/retraction and retries can observe repeatedly. | Freeze first tier snapshot and add explicit `prometheus_observed`/terminal emission idempotence. |
| False avoidable recompute | Global L3 publish or KV-only hit can overstate reusable hybrid prefix. | Same-attempt/same-generation `D`; require hybrid completeness; unknown -> null, not zero. |
| Unit confusion | Mamba slots/full-token-equivalent capacity can be mistaken for tokens. | Keep `completed_aux_units` in native units; token equation uses KV prompt positions only. |
| Clock mismatch | Existing wall-ms P2-A lines cannot be subtracted from monotonic ns. | New production fields all use monotonic ns; wall values correlation-only. |
| Collector duplication | Registering one metric name in scheduler and storage collectors fails. | Single registration owner (`SchedulerMetricsCollector`), carry storage duration as operation fact. |

## 7. Rejected alternatives

1. **Request ID Prometheus labels** — rejected for unbounded cardinality and privacy/operational cost.
2. **Runtime p50/p95/p99 gauges** — rejected because process-local quantiles are not mergeable and require a new window/reset owner. Histograms plus PromQL are standard and reversible.
3. **Reuse `_t38c_log`, durable trace, or marker files as production telemetry** — rejected because they add separate persistence paths, marker authority, experimental schemas, and file writes on cache paths.
4. **Reuse wall-ms P2-A log parsing** — rejected because clocks/precision differ and logs do not provide a stable typed request record.
5. **Count Mamba state slots as tier tokens** — rejected because slots and logical prompt tokens are different dimensions and would violate conservation.
6. **Derive durable coverage from global `l3_publish` or `BlockStored` events** — rejected because unrelated chains/generations can advance them; they are not per-request reusable-prefix proof.
7. **Create a new telemetry thread/queue/writer** — rejected as unnecessary new concurrency and persistence ownership; the existing request exporter suffices.
8. **Put all exact request fields in Prometheus** — rejected; per-request JSONL and aggregate metrics have distinct ownership and cardinality requirements.

## 8. Structural N/A and reopen conditions

- **GPU synchronization/timing:** N/A. P0 measures CPU-visible lifecycle boundaries, not kernel time. Reopen only if the claim changes to GPU transfer/kernel latency.
- **New server/GPU test:** N/A for formula/schema/ownership tests. Reopen only for a performance/effectiveness acceptance claim.
- **Distributed cross-host clock subtraction:** N/A. RH staging and admission are scheduler-process-local in this packet. Reopen if PD/disaggregated lead is required.
- **New transaction/recovery protocol:** N/A. Metrics are non-authoritative; JSONL follows existing best-effort exporter semantics. Reopen if records become billing/SLO authority or require exactly-once recovery.
- **New locks/shared registry:** N/A if facts stay operation-local and request-local. Reopen if implementation introduces cross-operation shared state.
- **Mamba token conversion:** N/A by invariant; sidecars remain native units. Reopen only if a separately named capacity-equivalent metric is requested.
- **Existing modified worktree files:** N/A to this closure. `qwen3_5_text.py` and `test_extent_g1_metadata_unit.py` were already modified and were not touched or relied upon.

## 9. Migration and reversibility

1. Additive schema `hicache_request.v1`; consumers ignore unknown fields.
2. Gate collection on existing metrics/file-export enablement; default-off path does no clock reads or request-field writes beyond any explicitly accepted low-cost metrics gate.
3. Dashboards first consume histogram/counter families; no policy reads them.
4. Rollback removes observations and the nested JSON object without cache-state migration.
5. If future schema changes semantics/units, publish `hicache_request.v2`; do not silently redefine v1.

## 10. Uncertainty and acceptance decision

### Confirmed

- Current code has authoritative seams for query, accepted finalize, READY, admission, first-tier split, and final request export.
- A no-ID low-cardinality Prometheus design and one-record JSONL design fit the bounded P0.
- No new instrumentation mechanism is needed beyond implementing the explicitly authorized telemetry later.

### Assumption requiring implementation review

- The accepted operation/terminal handoff can carry query timestamps and durable contiguous prefix without touching a serialized cross-process protocol in unified mode. Current object ownership indicates yes; the coder/reviewer must verify all selected HiCache controller variants.

### Orchestrator decision required

- Accept **Option A (recommended):** additive `meta_info.hicache_telemetry` only when the existing request-file export is enabled. Smallest closure; opt-in output bytes change.
- Or choose **Option B:** preserve response `meta_info` exactly. This requires a fresh architecture dispatch for an exporter-only internal envelope and expands the interface closure; do not silently implement it in P0.

Subject to Option A acceptance, issue one implementation packet for the source/test closure in §5, followed by one independent terminal review of final bytes and focused CPU test evidence.
