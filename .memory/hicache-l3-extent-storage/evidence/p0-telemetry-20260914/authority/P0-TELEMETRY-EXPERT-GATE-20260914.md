# P0 Telemetry Expert Gate — single normative resolution

- Task: `LOCAL-P0-TELEMETRY-EXPERT-GATE-20260914`
- Role: architect / Expert Gate recommendation; orchestrator acceptance remains required
- Date: 2026-09-14
- Decision: **EXPERT-GATE-RESOLVED**
- Execution boundary: documentation/evidence only. No product code was changed, no GPU/server was started, and no workload or test was rerun.

## 1. Scope and effect of this decision

This gate resolves the three architecture blockers identified by the final-byte review:

1. the causal position and authority of `prefetch_issue_mono_ns`;
2. the proof required before matched prompt coverage may be called L3-durable;
3. the conflict between Performance Baseline Specification v2 and the telemetry conservation equation.

The resolved contract below supersedes conflicting P0 design language and the v2 cache-accounting equation for all future telemetry repair and baseline validation. It does **not** approve the current implementation bytes and does **not** authorize performance reruns. FR1 and FR2 still require a code repair, focused CPU production-seam evidence, fresh byte identity, and independent correction-and-revalidate review.

## 2. Observed facts

### 2.1 Queue publication

- `HybridCacheController.prefetch` constructs and annotates the operation, then publishes it through `prefetch_queue.put(operation)` before returning.
- The reviewed implementation assigns `operation.prefetch_issue_mono_ns` in `UnifiedRadixCache.prefetch_from_storage` only after that return.
- `_storage_hit_query` timestamps query start after the worker dequeues the operation. Therefore a legal interleaving can produce query-start before issue, or expose a null issue value.

### 2.2 Current cache authority

- Scheduler `matched_len = len(req.prefix_indices) + req.host_hit_length` combines device- and host-resident coverage. Residency is reusable material but is not L3 durability proof.
- `prefetch_gate_ok` accepts a host-`backuped` anchor, root, an L3-durable anchor, or a buffer-mode hash anchor. Passing this gate therefore does not prove that the matched prefix is durable.
- `is_storage_persisted(anchor)` means KV write ACK plus a contiguous persisted parent chain. `is_l3_durable(anchor)` is broader: it is true for either persisted KV or a successfully restored node, and the restored branch does not itself prove an arbitrary matched parent chain.
- Current tree-node L3 predicates are KV predicates. In a hybrid layout, KV durability alone does not prove that every required sidecar/state component is durably reusable for the same prefix.
- Accepted suffix finalization has operation-local KV and sidecar completion facts. DSA-like layouts clamp to a common prefix; SWA/Mamba-like layouts are all-or-nothing.

### 2.3 Formula conflict

- The telemetry design and implementation define `newly_prefilled_tokens = prompt_tokens - (L1 + L2 + L3)` and define avoidable recompute as a subset of newly-prefilled tokens.
- Performance Baseline Specification v2 currently adds `avoidable_recompute_tokens` again in prompt conservation. Any positive avoidable-recompute value therefore fails one of the two oracles.

## 3. Normative contract

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

### 3.1 Event and timestamp authority

`prefetch_issue_mono_ns` means **controller acceptance/publication time**, not scheduler call time and not post-publication acknowledgement time.

The controller that owns `prefetch_queue` MUST perform this order on the producer thread:

1. construct the accepted `PrefetchOperation`;
2. populate telemetry enablement, session generation, and operation-local join fields;
3. if telemetry is enabled, assign exactly one `time.monotonic_ns()` value to `prefetch_issue_mono_ns`;
4. publish that same operation with `prefetch_queue.put(operation)`;
5. never overwrite the issue timestamp in `UnifiedRadixCache`, scheduler, worker, or finalizer code.

The authoritative event is step 3 immediately before step 4. Queue publication is the release/handoff boundary. A worker may assign `storage_query_start_mono_ns` only after dequeue. For every joined queried operation:

```text
prefetch_issue_mono_ns <= storage_query_start_mono_ns <= storage_query_end_mono_ns
```

The older P2-A log timestamp is diagnostic only and MUST NOT populate or override this field. A declined operation that is never published has `prefetch_issue_mono_ns = null`; no synthetic issue event is emitted.

This is an ownership relocation of an observational clock read, not new scheduling authority or concurrency.

### 3.2 L3 durable matched-prefix authority

Define:

- `M` = matched prompt-prefix token count before the new suffix query;
- `Md` = the contiguous prefix within `M` proven L3-reusable for all model state required by the active layout;
- `S` = accepted suffix length proven by this operation's storage query and finalizer, after cross-rank and sidecar clamp/all-or-nothing rules;
- `D` = authoritative total contiguous L3-reusable prompt prefix before admission.

#### Required proof tuple

No positive matched-prefix value may be classified as L3-durable without one operation-local `matched_prefix_l3_proof` snapshot containing or unambiguously binding all of:

```text
(request/rid lineage, prefetch_attempt_id, session_generation,
 prompt/hash lineage, selected anchor, matched token boundary M,
 required component set, per-component durable/common boundary,
 proof kind, proof observation point)
```

The proof is captured before queue publication and carried on the existing operation/finalizer handoff. Scheduler accepts it only when attempt and generation match the request. It is observational and MUST NOT alter the prefetch gate.

Allowed proof kinds are:

1. `persisted_contiguous`: the selected live anchor corresponds exactly to the first `M` prompt tokens; KV satisfies `is_storage_persisted(anchor)` at the issue snapshot; and every required hybrid component has an authoritative durable group/member proof covering the same prefix. For pure-KV layouts, the KV predicate is sufficient.
2. `joined_restore`: an earlier or current accepted L3 query/finalize fact, bound to the same request lineage, attempt, generation, prompt/hash lineage, and required component set, proves a common contiguous prefix of at least `Md`.
3. `root_zero`: the selected anchor is root and `M == 0`; this authoritatively proves `Md = 0`, not a positive durable prefix.

The following are never sufficient alone: `matched_len`, device indices, `host_hit_length`, `backuped`, `storage_written`, global `l3_publish_epoch`, anchor storage-version change, a cache key/hash without a positive storage result, or broad `is_l3_durable(anchor)` without contiguous-prefix and component proof.

#### Classification and null rules

- `matched_prefix_authority = "l3_durable"` only when an allowed proof establishes `Md == M` for the required component set.
- `matched_prefix_authority = "device_reusable"` or `"host_reusable"` records known residency only. It MUST NOT contribute a positive value to `Md` or `D`.
- `matched_prefix_authority = "none"` is valid only for the authoritative `root_zero` case.
- `matched_prefix_authority = "unknown"` applies when the selected anchor is stale, prompt/hash lineage cannot be bound, a KV-only predicate is used for a hybrid layout, component/group durability is unavailable, or the proof is mixed/partial across `M`.
- For `device_reusable`, `host_reusable`, or `unknown`, `matched_prefix_l3_tokens` and total `durable_reusable_prefix_tokens` MUST be `null`, except `root_zero`, which yields zero. Null means “not authoritatively classifiable”; it MUST NOT be converted to zero.

#### Suffix and total-prefix rule

Suffix `S` is authoritative only after accepted finalization of the same operation and matching attempt/generation:

- pure KV: accepted, cross-rank-clamped KV completion;
- DSA/KV-derived page-aligned sidecars: minimum common contiguous prefix across KV and every required sidecar;
- SWA/Mamba/trailing-window or other all-or-nothing layouts: full accepted completion only when every required sidecar contract is complete; otherwise no positive suffix credit.

Then:

```text
D = min(prompt_tokens, Md + S)
```

only when `Md` is authoritative (including `root_zero`) and the suffix finalizer is accepted and joined. Otherwise `D = null`. Device/host reuse remains represented exclusively by L1/L2 accounting.

### 3.3 Token conservation versus optimization opportunity

These are separate equations with separate meanings.

#### Conservation equation (exclusive partition)

```text
C = L1_tokens + L2_tokens + L3_tokens
newly_prefilled_tokens = prompt_tokens - C
prompt_tokens = L1_tokens + L2_tokens + L3_tokens + newly_prefilled_tokens
```

All four right-hand components are non-negative logical prompt-token positions and mutually exclusive. `L2_tokens` excludes L3-restored positions. Mamba slots and other auxiliary native units MUST NOT enter this equation. A negative remainder or unequal sum is `tier_nonconservation` and invalid; production derivation MUST NOT hide bad inputs with `max(0, ...)` and then claim conservation.

#### Optimization-opportunity metric (derived subset)

When `D` is authoritative:

```text
avoidable_recompute_tokens = max(0, min(prompt_tokens, D) - C)
0 <= avoidable_recompute_tokens <= newly_prefilled_tokens
```

When `D` is not authoritative, `avoidable_recompute_tokens = null`. This metric annotates the subset of newly-prefilled prompt positions that authoritative L3 state could have avoided recomputing. It is **not** an additive conservation component and MUST NOT be included in `prompt_tokens`, `actual_prefill_tokens`, or throughput denominators a second time. A future repeated-execution cost metric requires a separate name and equation.

#### Required correction to Performance Baseline Specification v2

Replace the v2 cache equation with the exclusive partition above and rename the contract key from `cache_prompt_accounting` to:

- `cache_prompt_conservation`: `prompt_tokens=L1+L2+L3+newly_prefilled`; and
- `cache_optimization_opportunity`: `avoidable_recompute=max(0,min(prompt_tokens,durable_reusable_prefix)-cached_coverage); null_without_authority; subset_of_newly_prefilled`.

This is a normative erratum to v2, not a new performance version. Existing raw runs are unchanged; any validator/runner MUST bind to this expert-gate artifact (or a corrected v2 artifact whose hash is recorded) before a telemetry-enabled run can be accepted.

## 4. Fixed telemetry interface

### 4.1 Prometheus

One registration/observation owner: `SchedulerMetricsCollector`. Existing process/rank labels are retained. The only added labels are the bounded enums below. No request, session, attempt, cache-key, node, storage-key, proof-kind, reason, or free-form label is permitted.

| Metric | Type | Added labels | Observation rule |
|---|---|---|---|
| `sglang:hicache_prompt_tokens_total` | Counter | `source=l1|l2|l3|newly_prefilled` | Observe the four exclusive partition values once per terminal request with valid conservation. |
| `sglang:hicache_avoidable_recompute_tokens_total` | Counter | none | Observe once only when authoritative and valid; never fold into the source metric. |
| `sglang:hicache_rh_prefetch_lead_seconds` | Histogram | none | Joined RH request with `issue <= admission`. |
| `sglang:hicache_rh_ready_slack_seconds` | Histogram | none | Joined accepted RH restore with `ready <= admission`. |
| `sglang:hicache_stage_latency_seconds` | Histogram | `stage=storage_query|prefetch_to_ready|ready_to_admission|admission_to_prefill_finish` | Observe each independently valid/applicable joined interval. |
| `sglang:hicache_telemetry_records_total` | Counter | `outcome=complete|partial|invalid` | Exactly once per terminal observed request. |

Histogram buckets remain:

```text
0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1,
0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 80
```

Counters/histograms reset only on process restart. No runtime percentile gauges are added. Prometheus exposition may normalize `:` according to the existing client convention.

### 4.2 JSONL schema

Because `hicache_request.v1` has not passed final acceptance, repair its meaning before baseline use rather than publishing conflicting accepted semantics. The opt-in existing request exporter remains the sole writer and emits at most one terminal record per non-health-check request.

Required public object fields are fixed as follows:

```text
schema: "hicache_request.v1"
outcome: "complete" | "partial" | "invalid"
partial_reason: null | "lifecycle_inapplicable" | "lifecycle_missing" | "durable_unknown"
invalid_reason: null | "attempt_mismatch" | "generation_mismatch" |
                "clock_order" | "tier_nonconservation" | "durable_contradiction"
rh_eligible: bool
prefetch_origin: bounded enum | null
prefetch_attempt_id: string | null                 # JSONL only
enqueue_mono_ns: int | null
prefetch_issue_mono_ns: int | null
storage_query_start_mono_ns: int | null
storage_query_end_mono_ns: int | null
ready_mono_ns: int | null
admission_mono_ns: int | null
prefill_finish_mono_ns: int | null
prompt_tokens: int
l1_tokens: int
l2_tokens: int
l3_tokens: int
newly_prefilled_tokens: int | null
matched_prefix_tokens: int | null
matched_prefix_authority: "l3_durable" | "device_reusable" |
                          "host_reusable" | "none" | "unknown"
matched_prefix_l3_tokens: int | null
durable_reusable_prefix_tokens: int | null
avoidable_recompute_tokens: int | null
completed_kv_tokens: int | null
required_aux_pools: bounded string array
completed_aux_units: object<string,int> | null      # native units
hybrid_restore_complete: bool | null
rh_prefetch_lead_seconds: float | null
rh_ready_slack_seconds: float | null
stage_latency_seconds: object<fixed-stage,float>
```

No prompt text, token IDs, cache hash, storage key, node ID, raw payload, or proof tuple is exported. The proof stays operation/request-local; JSONL exports only its bounded classification and token result.

### 4.3 Outcome and null semantics

- `invalid`: a contradiction or failed invariant exists. `invalid_reason` MUST be non-null; `partial_reason` MUST be null. Invalid reason precedence is: `attempt_mismatch`, `generation_mismatch`, `clock_order`, `tier_nonconservation`, `durable_contradiction`.
- `partial`: no contradiction exists, but at least one applicable lifecycle or durable-authority field is unavailable. `partial_reason` MUST be non-null; `invalid_reason` MUST be null. `durable_unknown` is partial, never invalid and never complete.
- `complete`: all fields applicable to the request path are authoritative and all invariants pass; both reason fields are null.
- A non-RH request may use `lifecycle_inapplicable` for RH-only READY/lead/slack fields. Inapplicable nulls are not synthesized as zero and do not invalidate independent token accounting.
- An independently valid stage interval MAY be observed even when the overall record is partial. No interval may be observed across an attempt/generation mismatch or with reversed endpoints.

## 5. Minimum repair set

Only these dependency-local changes are required; no adjacent cleanup is authorized.

1. **Controller publication seam:** assign issue time in `HybridCacheController.prefetch` before `prefetch_queue.put`; remove later assignments from unified/HiRadix callers so there is one owner and no overwrite.
2. **Matched-prefix proof:** replace `stats_matched_prefix_tokens = len(all matched tokens)` with an operation-local proof/result from the selected anchor. Use the proof rules in §3.2. If existing state cannot prove all required hybrid components, emit unknown/null rather than infer.
3. **Finalizer calculation:** compute `D` only from authoritative `Md` plus accepted/clamped `S`; preserve attempt/generation checks. Rejected, stale, component-incomplete, or unproven completion yields null.
4. **Accounting helper:** validate raw non-negative exclusive inputs and exact conservation; do not use clamping to convert nonconserving input into a valid record. Keep avoidable recompute separate.
5. **Metrics contract:** remove `avoidable_recompute` from `HICACHE_PROMPT_SOURCES`; add the separately named counter; preserve one-observation idempotence and fixed labels.
6. **JSONL contract:** export public `outcome`, `partial_reason`, matched-prefix classification fields, and the fixed null semantics above through the existing exporter only.
7. **v2 documentation/runner binding:** correct the Markdown and JSON names/equations and ensure the future validation runner references the corrected spec/expert-gate hash. No workload rerun is part of this repair.

These changes MUST NOT add or alter a writer, thread, queue, lock, storage persistence format, scheduling/cache authority, retry behavior, or default telemetry enablement. Telemetry failures remain best-effort and cannot fail or influence serving.

## 6. Minimum focused CPU tests and acceptance invariants

No GPU/server test is needed for this correction. The next implementation packet must run dependency-local production-seam tests, not only pure helper tests.

### T1 — queue-publication seam

- Invoke the real controller `prefetch` with a queue fake whose `put` inspects the operation synchronously.
- At `put`, issue time is non-null and join fields are populated.
- Simulate/execute immediate dequeue/query and prove `issue <= query_start <= query_end`.
- Prove caller return does not overwrite issue time.
- Disabled telemetry leaves issue/query fields null and behavior unchanged.

### T2 — matched-prefix L3 authority and finalizer handoff

Through the actual selected-anchor -> operation -> finalizer fact path, cover:

- root with `M=0` -> authoritative zero;
- device-only matched prefix -> `device_reusable`, durable fields null;
- host-only/`backuped` matched prefix -> `host_reusable`, durable fields null;
- KV `storage_written` but unacked -> unknown/null;
- pure-KV `storage_persisted` contiguous anchor -> positive `Md=M`;
- broad restored/durable flag without same-lineage contiguous proof -> unknown/null;
- accepted full and partial suffix -> `D=Md+S`, bounded by prompt;
- DSA sidecar shortfall -> minimum common prefix;
- SWA/Mamba sidecar shortfall or rejected finalizer -> null, no positive total;
- stale attempt and generation -> invalid with all dependent durable/timing facts null;
- component/group durability unavailable -> unknown/null, never zero or inferred positive.

### T3 — formulas, schema, and metrics DI

- all-L1, all-L2, all-L3, cold, mixed, final-page/remainder vectors satisfy the exclusive equation;
- negative/oversummed raw inputs become `tier_nonconservation`, not clamped success;
- known avoidable values satisfy the subset bound; unknown durable authority yields null;
- exact Prometheus names and label enums match §4.1; no identity labels;
- the four conservation sources sum to prompt tokens across valid observed records; the separate avoidable counter is not included in that sum;
- complete/partial/invalid count exactly once; partial records may emit only independently valid intervals;
- JSONL serializes exactly one line with public outcome/reason fields and stable nulls; health checks remain excluded;
- token, string, and applicable embedding multi-tokenizer paths preserve the object;
- rejecting derivation/collector/export behavior does not affect serving.

### Acceptance invariants

```text
queue publication observes a fully initialized immutable issue timestamp
issue <= query_start <= query_end for every queried joined operation
prompt = L1 + L2 + L3 + newly_prefilled
0 <= avoidable_recompute <= newly_prefilled, or avoidable_recompute is null
positive matched-prefix L3 credit has an allowed same-lineage/component proof
unknown is null; host/device residency is never L3 credit
hybrid positive credit satisfies common-prefix or all-or-nothing layout policy
no Prometheus identity/free-form labels
one terminal record/observation per applicable request
telemetry has no serving or cache-policy authority
```

After these tests pass, capture fresh identities for all dependent changed bytes and request one independent terminal correction-and-revalidate review. Only that review/orchestrator may authorize telemetry-enabled performance reruns.

## 7. Rejected alternatives

1. **Timestamp after queue publication:** rejected because it cannot establish causal order and permits worker-visible null state.
2. **Scheduler call-entry as issue:** rejected because call entry precedes controller acceptance and may count declined/unpublished work.
3. **Treat all `matched_len` as durable:** rejected because it combines L1/L2 residency and the gate accepts non-L3 anchors.
4. **Use `is_l3_durable` alone:** rejected because it does not by itself prove the entire matched prompt lineage or all required hybrid components.
5. **Treat unknown durable coverage as zero:** rejected because it converts missing authority into a false negative optimization claim.
6. **Make avoidable recompute an additive partition:** rejected because the current meaning is overlap within newly-prefilled positions; an additive version would require redefining `newly_prefilled` as an unavoidable-only quantity and would obscure actual prefill work.
7. **Keep avoidable recompute under the partition metric's `source` label:** rejected because summing sources would double count and make metric naming misleading.
8. **Add a new writer/thread/lock/persistence protocol:** rejected as unnecessary and outside the authorized boundary.

## 8. Migration, risk, and reversibility

- **Migration:** correct the not-yet-accepted `hicache_request.v1` schema and v2 documentation before any accepted telemetry run. Consumers/validators must record the corrected artifact hash. No raw-run rewrite is allowed.
- **Authority risk:** the proof is observational only. Reopen architecture review if any telemetry proof is used by admission, restore, retry, eviction, or durability decisions.
- **Hybrid uncertainty:** current code visibly exposes KV durable predicates and accepted sidecar completion, but a generic durable matched-prefix predicate for all component layouts was not confirmed. The safe required behavior is unknown/null until a dependency-local implementation trace proves the component group.
- **Concurrency risk:** assigning fields before the existing queue handoff is reversible and adds no concurrency. Reopen if implementation introduces shared registries or mutation after publication.
- **Format risk:** additive/corrective JSONL fields are bounded and opt-in. Reopen if `hicache_request.v1` has already been consumed as an accepted external schema; then publish `hicache_request.v2` instead of silently changing it.
- **Rollback:** telemetry fields and observations can be removed without cache-state or storage migration because no policy consumes them.

## 9. Gate disposition

**EXPERT-GATE-RESOLVED** means the three requested architecture questions now have one executable normative answer. It does not mean implementation approval.

- Current implementation: **changes still required** for FR1/FR2 and contract alignment.
- GPU/server/performance reruns: **not authorized by this artifact**.
- Next actionable step: one bounded implementation correction plus the focused CPU tests in §6, followed by one independent final-byte correction-and-revalidate review.
