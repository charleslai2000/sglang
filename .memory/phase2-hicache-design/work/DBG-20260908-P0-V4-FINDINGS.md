ENTRY: ACCEPT

Task: DBG-20260908-P0-V4-FINDINGS
Epoch: E20260908-P0P1P2
Role: debugger-deep
Status: done

## Scope and evidence

Read-only diagnosis of F-1--F-5 and the KV/Mamba durability chain. No product,
vehicle, review, or remote-engine action was taken. Evidence is the current dirty
`sglang-3090-24g-opt` tree, the V3 gate report, and the durability plan. The tree
contains a concurrent, uncommitted candidate V4 remediation; it is not treated as
accepted proof.

Observed causal chain: `_write_backup_storage_node()` builds KV + sidecar transfers
and submits one `StorageOperation` (`unified_radix_cache.py:2774-2877`);
`HybridCacheController.backup_thread_func()` executes sidecar `batch_set_v2` plus KV
write and enqueues the ACK (`hybrid_cache_controller.py:946-1132`);
`_drain_backup()` owns completion, advances the persisted frontier, and emits the
barrier (`unified_radix_cache.py:4271-4524`). Extent durability is pwrite success
plus allocator index commit (`extent_file_backend.py:1124-1160`; documented at
lines 17-20). This is the only safe place to call a write durable.

## Minimal repair guidance

### F-1: completed-prefetch API and marker-off runtime

The safe interface is additive: make
`HybridCacheController.append_host_mem_release(host_indices=None,
extra_pools=None, trace_context=None)` accept the optional keyword and pass it only
to trace-only bookkeeping. Keep the existing positional two-argument behavior
unchanged. The completion call at `unified_radix_cache.py:4261-4269` may then pass
`operation.trace_context` unconditionally; marker-off must turn that context into
no trace records, not a different cleanup path.

The current candidate has this compatible signature at
`hybrid_cache_controller.py:409-450`; static AST inspection confirms its caller
matches. It still needs behavioral coverage. With the marker absent, completed
prefetch must (a) call the same release path without `TypeError`, (b) enqueue/free
exactly the unconsumed KV and sidecar slots, and (c) produce no trace file/write.
With the marker present, those allocator/release observations must be identical,
with additive trace records only. Do not gate the API call itself on the marker:
that would create two cleanup semantics.

### F-2/F-4: retroactive promotion must select each node's own complete attempt

The V3 failure is causal, not cosmetic. A descendant can ACK first; its
`advance_storage_persisted(descendant)` returns no promotion. A later parent ACK
can return both parent and already-ACKed descendant. A parent operation cannot
prove the descendant's KV/Mamba write.

Maintain pending evidence per *node and attempt*, not one mutable node value:

```
attempt_key = (run_id, rank, node_id, operation_id, attempt_id)
node_pending[node_id][attempt_key] = {
  trace_context=(session_id, session_generation, build_rid),
  final_kv_hash, kv_submit/ack/commit evidence,
  mamba_expected keys/pages, mamba_submit/ack/commit evidence,
  write_generation or other tree-owned attempt binding
}
```

On every successful operation ACK, record its own candidate before
`advance_storage_persisted`. For every returned `promoted_id`, select only that
node's candidate whose tree-owned write generation/attempt binding is still current
for the promoted node. Emit exactly one barrier for that selected candidate, then
retire only that candidate. Never substitute the triggering parent candidate, and
never select by node/hash/timestamp alone. A partial/omitted Mamba candidate is
retired/recorded as non-durable; it cannot later pair with another attempt's KV.

The candidate code moves in the right direction by storing evidence before advance
and looking it up by each `promoted_id` (`unified_radix_cache.py:4380-4524`), and
now carries `operation_id`/`attempt_id` into the barrier
(`:4482-4516`). It remains insufficient if multiple attempts for a node can exist
before promotion: `_t38c_durability_evidence[str(node_id)]` overwrites rather than
selects a tree-bound attempt. Either prove duplicate submission is impossible over
the whole interval, or use the attempt-keyed structure above. The latter is the
safe minimal diagnostic repair because the gate explicitly requires a
duplicate-attempt rejection fixture.

Barrier invariants:

- `barrier.node_id`, `operation_id`, `attempt_id`, `run_id`, and `rank` identify
  one candidate; `session_id`, `session_generation`, `build_rid`, and final KV hash
  equal that candidate's context.
- KV ACK covers all requested KV pages and follows the KV submit; Mamba is present,
  expected pages/keys are non-empty, and its ACK/commit covers that exact set.
- The persisted/frontier publication is for `barrier.node_id`, occurs after those
  two ACK/commits, and is the event that made this node queryable. Record its
  `storage_version`, `l3_publish_epoch`, and an event-id predecessor set.
- `warm lookup` joins this exact tuple and occurs after the barrier. A missing
  candidate or any mismatch is `NOT_VERIFIED`, never a barrier.

Focused assertions: child-ACK then parent-ACK emits child and parent barriers once,
each with its own operation/attempt and sidecar result; repeated writes on one node
cannot join KV from attempt A to Mamba from attempt B; partial/zero-Mamba, failed
sidecar, and missing pending evidence emit no combined barrier.

### F-3: authoritative session/build lifecycle

Use `(session_id, session_generation, build_rid)` as the context key; a request
without scheduler-owned `session_generation` must produce no context. A warm request
can add `warm_rid`, but must retain the exact build tuple. The candidate uses this
shape in `unified_radix_cache.py:665-784`, which corrects the original
session-id-only lookup.

Lifecycle hooks must retire all trace-only state on every reuse boundary:

- full cache reset: node/session/request/attempt maps, residency tokens, completed
  tokens, and emitted-barrier dedupe state;
- `open_radix_session(session_id)`: retire the old session records before opening;
- `release_radix_session(session_id)`: retire after the scheduler/ref tracker has
  completed the release;
- `release_session(session_id)`: also retire, or document and prove it cannot end a
  radix lifecycle. The current candidate omits retirement here
  (`unified_radix_cache.py:5209-5211`), so this hook remains open;
- any lower-level close/reset path that bypasses these public wrappers must route
  through the same retirement helper.

Retirement by `session_id` is acceptable only at a true close/reopen boundary. Do
not retire a live different generation merely because its ID matches during an
overlap; otherwise in-flight valid evidence is erased. Fixture: build A/generation
1, close, reopen same ID as generation 2/build B, then warm B. Assert no event can
carry build A or generation 1; include overlapping old ACK arriving after reopen
and require it to be retired/rejected rather than attributed to B.

### F-5: lifecycle-scoped slot completion

A digest is a lookup hint, never lifecycle identity. Current helpers create a
monotonic token and retire tokens (`trace_context.py:57-183`), and reset clears
global sets (`unified_radix_cache.py:870-887`), but the release enqueue at
`hybrid_cache_controller.py:390-406` registers only a digest/context (no node or
allocator/detach generation). Later drain resolves the first incomplete same-digest
record (`trace_context.py:105-149`). Thus identical/reused slots can still be
mis-associated when two lifecycles are outstanding; thread-local lookup does not
prove producer/consumer identity across queue delay/concurrency.

Attach the exact token to the queued release item at enqueue time and complete that
same token at drain time. The token should contain at least
`(run_id, pool, tier, node_id, session_generation, build_rid, detach_seq)` and,
where available, allocator/extent generation. Do not re-find it from
`(pool,tier,slot_digest)`. Retire the token only after its barrier has consumed it,
or on node removal/session close/reset; clear any queue-attached metadata on
controller reset. If changing queue payloads is risky, use a trace-only parallel
FIFO metadata queue with the same atomic enqueue/dequeue ownership, not a global
digest map.

Focused assertions: two outstanding same-digest detach records completed in reverse
order retain their own context/tokens; slot reuse after completion cannot satisfy a
new detach; reset, node deletion, release, and reopen leave no selectable token;
the residency barrier refuses a node until each exact queued token completes.

### Explicit KV/Mamba durable evidence without semantic weakening

Keep the existing all-or-nothing restore/min-fold untouched. Diagnostic evidence
must make an existing successful write observable; it must not make an absent Mamba
checkpoint acceptable.

Emit an attempt-keyed evidence bundle:

1. At submission (`unified_radix_cache.py:2841-2869`), record KV key-set digest and
   count, Mamba transfer-present boolean, ordered Mamba key-set digest/count, and
   expected rank set. `mamba_expected_pages == 0` is explicit omission, not success.
2. In KV v1 and Mamba/sidecar v2 write paths, emit per-key (or privacy-safe ordered
   key-set digest plus per-key extent refs) commit evidence only after pwrite and
   allocator commit. Existing extent commits aggregate only by extent
   (`extent_file_backend.py:151-171`) and cannot by themselves prove which KV or
   Mamba key committed. Preserve `operation_id`, `attempt_id`, node, pool, rank,
   storage key/key digest, `extent_id`, generation, and commit event-id.
3. At the controller ACK, reference the KV and Mamba commit event IDs and state
   requested/succeeded counts. Controller aggregate booleans at
   `hybrid_cache_controller.py:1099-1130` are useful summaries but are not a keyed
   durable proof without these references.
4. The frontier/barrier references both ACK chains plus its own publication event.
   The vehicle admits warm lookup only after an exact join; absent/failed/key-mismatch
   evidence selects A/B/C/D/E/F from the durability plan, with F blocking.

For rank-sharded Mamba, record one Mamba acknowledgement per expected rank and make
the barrier/collector require the declared expected set. Do not let a KV-only rank,
or a count-only `all()` result, stand in for an absent rank/key. This is
instrumentation only; the cache's current restore eligibility and min-fold remain
the authority.

## Verification evidence and gaps

- Static AST inspection: current `append_host_mem_release` declares
  `trace_context`, and the completed-prefetch call supplies it. This disproves the
  original current-snapshot TypeError, but not marker-off runtime behavior.
- Current focused file `3090-dev/test_p0_trace_context_v4.py:28-111` is primarily
  AST/string checking. It does not instantiate the controller/queue, simulate
  retroactive parent-child ordering, prove attempt binding, or test concurrent slot
  reuse; it is insufficient as acceptance evidence.
- No local pytest execution: the V3 reviewer recorded `pytest` unavailable, and no
  dependency installation is authorized. No remote engine was run.

## Followups

- NEEDS_REROUTE: a fresh `coder` task should implement only the selected minimal
  trace-contract repair; a separate `tester` task should execute the focused
  behavioral fixtures and marker-off regression.
- Re-review the resulting diff independently before any P0 vehicle run.

## Open issues

- The exact tree-owned storage write-generation API that binds a promoted node to a
  particular operation was not identified in this read-only pass; if none exists,
  the implementing task needs a narrow trace-only monotonically increasing attempt
  generation at submission.
- The current dirty tree has concurrent V4 edits, so line anchors and conclusions
  apply to the inspected snapshot only.
