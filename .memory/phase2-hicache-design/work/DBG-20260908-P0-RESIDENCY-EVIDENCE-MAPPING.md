STATUS: done

# DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING

- Task ID: `DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING`
- Epoch: `phase2-hicache-design / 2026-09-08`
- Scope: read-only source and remote r12 evidence; this report is the only write.
- Snapshot boundary: r12 was still running. The remote trace was stable at approximately 1,386,369 r12 records when inspection stopped at the orchestrator's request.

## Conclusion

r12 does **not** provide valid cold-residency evidence for the strict vehicle gate. It proves that many individual allocator frees returned, but it contains no product-authored, exact-identity `residency_barrier` transition for any target. Under the frozen design, a client/vehicle must not synthesize that transition from `residency_free_complete` records. The minimal next action belongs to the **product emitter owner**: repair/complete product emission of the existing `residency_barrier` event after its authoritative keyed-detach/completion fold succeeds. A vehicle-only mapping change would both violate the frozen producer boundary and accept records that cannot make the required exact identity join.

## Observed facts

### Frozen gate and vehicle reducer

1. The authoritative contract requires the causal order
   `build_complete -> KV durable + Mamba durable -> durability_barrier(combined_durable=true) -> residency_barrier(cold_residency=true) -> warm`.
   It assigns residency to the product barrier, not to a client inference.
2. `p0_session_barrier_vehicle.py` accepts cold state only on exactly
   `evt == "residency_barrier"` with `cold_residency is True`, after its durable state is true. It has no mapping from `residency_free_complete` to `state["cold"]`.
3. The reducer requires every session-scoped admitted event to carry the exact identity tuple `(session_id, build_rid, node_id, final_kv_hash)`. A missing identity is an invalid join, not a weaker form of evidence.

### Product event semantics

4. The product emits `residency_detach` at the logical cache-node eviction boundary, with node ID, final KV hash, pool, tier, slot digest, and V3 trace context. It registers a keyed lifecycle token through `_t38c_note_detach`.
5. The product emits `residency_free_complete` only after the relevant allocator/host-pool free call returns. It carries `pool`, `tier`, `slot_count`, `slot_digest`, `result=true`, and request trace context. In the observed r12 examples its outer `node_id` and `final_kv_hash` are null; those records are therefore not direct vehicle identities.
6. Product function `_t38c_residency_barrier(cache, node_id)` is the only inspected authority that can fold the exact token lifecycle. It checks: an expected detach set exists; FULL and Mamba device/host values are both absent; relevant release queues are empty; every expected keyed token completed; and duplicate publication is suppressed. Only then does it emit `residency_barrier` with the node's V3 context, exact node/hash, and `cold_residency=true`.
7. The product calls that fold after `_free_values` from device-leaf eviction, demotion, storage-backed hollowing, and forced-miss paths. Thus the intended producer event already exists in source, but no such event was observed in r12.

### r12 snapshot (`run_id=p0-s25-v43-churn-fix1-live-r12`)

8. Raw event counts at the stable snapshot: 1,386,369 total; 34 `build_complete`; 25 `durability_barrier`; 1,994 `residency_free_complete`; 1,589 `residency_detach`; **0 `residency_barrier`**; and 0 product `warm_lookup_start`, `warm_request`, or restore events.
9. All 25 expected target session IDs (`p0-s25-s00000` through `p0-s25-s00024`) occur. Each has KV-device and Mamba-device `residency_free_complete` evidence; target counts vary because these are individual slot/component frees, not one target-level transition.
10. Exactly nine unique churn session IDs occur: `p0-s25-churn-00000` through `p0-s25-churn-00008`.
11. The snapshot has zero repeated `event_id` values (and zero duplicate records by event ID). This is a raw-log observation, not a final gate verdict.
12. 1,620 `residency_free_complete` records lack at least one required reducer identity field. The same snapshot also has 34 incomplete `residency_release_enqueued` and eight incomplete `storage_query` records. These records cannot independently enter the strict identity reducer as cold evidence.

## Causal reconstruction

```text
target/churn pressure
  -> product emits node-scoped residency_detach
  -> allocator/host pool returns individual slots
  -> product emits residency_free_complete (many records; often no node/hash)
  -> [missing in r12] product exact-token/node fold emits residency_barrier
  -> [correctly blocked] vehicle cannot set state[cold]
  -> no warm/restore phase observed
```

The competing hypotheses resolve as follows:

- **H1: vehicle mapping defect only — rejected.** The vehicle is intentionally strict and the contract assigns this assertion to the product. Mapping individual free completions would admit events that lack `node_id`/`final_kv_hash`, cannot establish that all expected frees for one node completed, and cannot verify that both component values are absent or release queues drained.
- **H2: product did not prove the cold transition — supported.** Product free-complete evidence is present at scale while its authorized aggregate event is absent for every target. This is precisely the causal gap between physical frees and node-level cold residency.
- **H3: r12 merely has not reached the transition — unresolved but non-exculpatory.** The vehicle process was still running at the snapshot boundary. However, current evidence is insufficient now; a later event cannot retroactively authorize an earlier warm. The next run/fix must make the product barrier observable before vehicle warm admission.

## Inference

It is not valid under the frozen design to derive a client-side `residency_barrier` from the ordered `residency_free_complete` stream. Ordering alone does not prove the product-only predicates: the exact detach-token set for one cache node, no remaining FULL/Mamba device or host values, and empty queued releases. The stream also lacks a direct exact node/hash join on many completion records.

The required producer evidence is the existing V3 event, emitted once per eligible target node:

```json
{
  "schema_version": "p0_durable.v3",
  "evt": "residency_barrier",
  "run_id": "<run>",
  "session_id": "<session>",
  "session_generation": "<scheduler generation>",
  "build_rid": "<response id>",
  "node_id": "<final target node>",
  "final_kv_hash": "<final target hash>",
  "cold_residency": true,
  "result": true,
  "reason": "all_detached_frees_complete"
}
```

No new client-side field or synthesized event is acceptable. If repair requires additional diagnostics, they must be product-local and cannot substitute for the event above.

## Recommendation and precise acceptance test

**Owner: product emitter/coder**, not vehicle. Fresh Task ID required.

Minimal authorized repair target: trace why `_t38c_residency_barrier` fails to publish after the observed detach/completion chain, then make its existing product-owned fold publish exactly one V3 `residency_barrier` only when its current keyed predicates are satisfied. Do not relax the predicates, manufacture the event in the vehicle, or convert partial free records to a barrier.

Acceptance test for the repair:

1. Focused product test: a target node with exact KV and Mamba detach tokens emits no barrier before any matching completion; emits none while either component remains device/host resident or a release queue remains non-empty; emits one barrier after all matching exact completions; a repeated poll is idempotent.
2. Fresh live run with a new `run_id`: preserve S=25 plus nine unique churn sessions. For each of 25 targets, require exactly one exact identity tuple across `build_complete`, accepted KV/Mamba durability, `durability_barrier`, and `residency_barrier`; require the product barrier to occur after durability and before any warm lookup/request.
3. Run the unmodified vehicle against that trace. Require zero reducer errors, zero conflicting/late identity evidence, zero duplicate `event_id`s, 25/25 cold states, and only then warm/restore acceptance. A missing or malformed product barrier remains `NOT_VERIFIED`, not a vehicle fallback condition.

## Missing evidence / open issues

- r12 had not completed, so there is no final vehicle `reducer-result.json`, verdict, or completed warm/restore evidence. No claim is made that r12 ultimately fails; it is insufficient at the declared snapshot.
- No final parser-derived count of `result=false` events was taken after the stop request. Therefore raw product error status is not established by this report.
- No target-level late-evidence claim can be made without a completed vehicle timeline. At the snapshot there were no warm/restore events, hence no observed early warm lookup; absence of later evidence is not evidence of absence.

## Artifacts and evidence

- Local vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`.
- Local producers: `python/sglang/srt/mem_cache/unified_radix_cache.py`, `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`, and `python/sglang/srt/mem_cache/trace_context.py` in the authorized opt worktree.
- Remote raw trace: `root@175.155.64.171:24052:/tmp/t38c-probe.log`, filtered by the stated r12 run ID.
- Remote live bundle: `root@175.155.64.171:24052:/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/vehicle`.

## Followups

- NEEDS_REROUTE: dispatch the minimal product-emitter diagnosis/fix to `coder` under a fresh Task ID.
- After that change, dispatch an independent fresh-run verification; do not reuse r12 as acceptance evidence.
