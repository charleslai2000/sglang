ENTRY: ACCEPT

# P0 trace-context V3 independent gate review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V3`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Review verdict: **REJECT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Revision and scope

Reviewed the dirty worktree at commit `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` on
branch `3090-24g-opt` (`origin/3090-24g-opt`). The tracked product diff is dirty;
the new helper has SHA-256
`259bbfbd55ada64e6816c4e3e9f9dd3aa14d71a578497eef09889a94d50bc7cb`.

Reviewed product files:

- `python/sglang/srt/mem_cache/trace_context.py` (new)
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
- `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`

Authoritative inputs reviewed:

- `plan-rh-durability.md`
- `ARCH-20260908-P0-SCOPE-CLOSURE.md`
- `SCOUT-20260908-P0-SESSION-JOIN.md`
- `COD-20260908-P0-TRACE-CONTEXT-V3.md`

The untracked `3090-dev/` vehicle/driver files were not reviewed, per the dispatch
boundary. No product, memory, vehicle, or remote process was modified or run.

## Evidence commands and results

- `git status --short --branch`, `git rev-parse HEAD`, and `git diff --stat`:
  confirmed the dirty identity above, five tracked HiCache files modified, and
  the new helper untracked. Additional unrelated untracked vehicle files remain
  in the worktree.
- `git diff --check`: **PASS**.
- AST parse of all six reviewed Python files: **PASS**.
- Marker helper probe with `os.path.exists` forced on/off: **PASS**; active
  `/tmp/t38c-durable-trace` was present and was not changed.
- Static signature/call-site check: **FAIL**. The reviewed
  `append_host_mem_release` definition has parameters `self, host_indices,
  extra_pools`, while the new call at `unified_radix_cache.py:4132-4140` passes
  `trace_context=`.
- Focused test command
  `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q`:
  **BLOCKED before collection** (`No module named pytest`). No dependency was
  installed.
- Remote engine/vehicle execution: **not run**, as explicitly prohibited.

## Blocking findings

### F-1 — Critical: unconditional prefetch completion `TypeError`

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:4132-4140` and
`python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:409-450`.

`_drain_ack_prefetch()` calls
`cc.append_host_mem_release(..., trace_context=...)`, but the concrete method
accepts only `host_indices` and `extra_pools`. The call is unconditional; it is
not guarded by the trace marker. Any completed storage prefetch ACK that reaches
this branch raises `TypeError` before host-release cleanup. This is a normal-path
runtime regression and also violates the required marker-off compatibility.

Acceptance impact: merge-blocking. The focused static checks pass because the
call is syntactically valid, but the method/call signature check fails.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4-PREFETCH-API` —
repair the interface/call consistently, then add a focused completed-prefetch
regression test with the marker absent and present.

### F-2 — High: retroactive frontier promotion can omit the required durability barrier

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:4214-4279`.

The code emits `durability_barrier` only inside the loop where
`promoted_id == node_id`. `advance_storage_persisted(node_id)` is explicitly
allowed to return descendants that become persisted retroactively when a parent
ACK completes. If a child operation ACKs (including its Mamba sidecar) before
its parent chain is persisted, that child produces no barrier because its first
promotion returns no node. When the parent later promotes the child, the
condition is false for the child and the parent operation's sidecar result cannot
prove the child's operation. The child therefore has `storage_persisted` evidence
but no `durability_barrier`.

Acceptance impact: merge-blocking for the P0 trace contract; a full session may
never acquire the required keyed barrier even though its write completed. This
prevents the vehicle from proving the barrier-before-lookup edge.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4-FRONTIER-JOIN` —
retain per-node operation/sidecar completion evidence and emit a barrier for each
retroactively promoted node only from that node's own complete KV+Mamba chain.

### F-3 — High: session/build context is not authoritative across generation reuse

Location: `unified_radix_cache.py:643-675, 761-771, 4947-4954`.

`_t38c_session_contexts` is keyed only by `session_id`; lookup ignores
`session_generation`, and `_t38c_record_node_context` uses `setdefault` for the
first tuple. Closing/reopening the same session updates the session-ref tracker
generation but does not clear these trace maps. The next build can therefore be
tagged with the old `session_generation` and old `build_rid`; later warm events
inherit that stale tuple. The implementation report also explicitly admits that
multi-build reuse of one session is not disambiguated.

Acceptance impact: merge-blocking for the exact keyed-join requirement. The
trace can falsely join a new build or warm lookup to an earlier build, so a
vehicle cannot treat `build_rid`/`warm_rid` as authoritative for session reuse.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4-SESSION-LIFECYCLE` —
scope context by the authoritative session generation and build identity, clear
or retire it on close/reopen, and add reuse/multi-build fixture coverage.

### F-4 — High: the durability barrier omits operation identity

Location: `unified_radix_cache.py:4219-4278`.

The code checks an in-memory `operation` while constructing the barrier, but the
emitted `durability_barrier` record contains only the trace context, `node_id`,
and `final_kv_hash`; it does not include `operation_id` or `attempt_id`. The
authoritative design requires the combined fact to join the same expected
session/node/operation and requires the event schema to preserve operation
identity where known. Repeated writes for the same session/node/hash cannot be
distinguished by the barrier record itself.

Acceptance impact: blocking scope/correctness issue. A collector can observe a
true barrier-shaped event but cannot prove which storage attempt's KV/Mamba
ACKs, extent commits, and frontier it represents. This is not an exact keyed
join.

Fresh task recommendation: include the operation and attempt identity in the
barrier context and add a repeated-write/duplicate-attempt fixture that rejects
cross-attempt joins.

### F-5 — Medium/High: residency completion state is not lifecycle-scoped

Location: `trace_context.py:12-13,47-63` and
`unified_radix_cache.py:293-330`.

`_T38C_DURABLE_COMPLETED` and `_SLOT_CONTEXTS` are process-global and retain
completion/context entries indefinitely. Their key is only `(pool, tier,
slot_digest)`; it has no node, run, allocator generation, or detach sequence.
Slot indices can be reused, so a later detach with an identical digest can match
a prior lifecycle's completion. The barrier's `completed` set therefore is not
an exact lifecycle join. The maps are also not cleared by cache reset or session
release.

Acceptance impact: the `cold_residency=true` evidence can be stale or associated
with the wrong context, so the residency barrier cannot be accepted as the
authoritative prerequisite for warm lookup until the key includes lifecycle
identity or entries are retired safely.

Fresh task recommendation: add run/node/generation-scoped ownership and cleanup
for slot-digest records, then test slot reuse and repeated cache reset/restart
scenarios.

## Non-blocking questions/open issues

- The focused unit test was not executable because `pytest` is unavailable; the
  implementer’s reported dependency blocker is independently reproduced.
- The product patch does not add vehicle-side request/session wiring or enforce
  a warm lookup gate. The live vehicle must still provide a stable session ID,
  enable the marker before build insertion, observe both keyed barriers, and
  issue warm only after those barriers. Missing context must remain
  `NOT_VERIFIED`, not inferred from timestamps.
- The current V2/remote evidence references cannot establish V3 context
  propagation or P0 acceptance. No live S=25 RH-off vehicle evidence was
  available or permitted in this review.
- The existing `storage_query`/`pc_mamba_query` paths still require a vehicle
  join to preserve raw KV frontier, queried Mamba key, write key set, and exact
  invalidation/generation evidence. This review did not accept a timestamp-only
  join.

## P0 decision

Residual vehicle and product join gaps **block P0**. Independently of the
product verdict, the absence of the authorized live S=25 RH-off vehicle means
there is no evidence of 25/25 builds, eligible full KV+Mamba restores,
barrier-before-lookup ordering, exact `s00002` A-E classification, cleanup, or
runtime health. A fixed settle or prior V2 result cannot substitute for that
evidence.

The additive product patch is **REJECTED** for merge until F-1 through F-4 are
resolved and focused tests establish the marker-off path, barrier joins, session
reuse, and residency lifecycle. F-5 remains a required correctness follow-up
before any P0 PASS claim. No scale task is eligible.

## Followups

- Route the fresh narrow tasks listed above to the implementation/test owners;
  do not silently repair this review artifact or the product diff under this
  Task ID.
- After those tasks, dispatch a new independent reviewer task with a new
  revision and the focused evidence bundle.
- Only after an independent product gate is accepted may the separate authorized
  P0 vehicle task run; its live result still requires a separate P0 gate.

## Open issues

- `pytest`/focused runtime environment unavailable.
- No live vehicle evidence or remote engine execution was authorized.
- Vehicle files and the vehicle/product join implementation remain outside this
  review scope.

Artifacts: this report only.
Evidence: dirty-tree identity, static AST/signature checks, marker helper probe,
diff check, focused-test blocker, and source-level barrier/context inspection.
Summary: the submitted additive trace is not mergeable; it contains one
unconditional runtime regression and multiple non-authoritative barrier/context
joins. P0 remains blocked without live vehicle evidence.
Extra work outside this review requires a fresh Task ID.
