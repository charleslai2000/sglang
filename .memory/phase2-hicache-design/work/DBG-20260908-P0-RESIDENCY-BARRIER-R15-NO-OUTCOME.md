# DBG-20260908-P0-RESIDENCY-BARRIER-R15-NO-OUTCOME

- Task ID: `DBG-20260908-P0-RESIDENCY-BARRIER-R15-NO-OUTCOME`
- Epoch: `phase2-hicache-design / 2026-09-08`
- Role/admission: `debugger-deep`, accepted.
- Invocation status: `done`.
- Scope: read-only local/remote evidence and source inspection; this report is
  the only write.  No product file, remote process, marker, or vehicle was
  changed.

## Causal diagnosis

The r15 target residency lifecycle has a deterministic **six-field in-memory
identity construction failure**.  `_t38c_record_node_context()` stores only
the request context returned by `make_trace_context()`, but never binds the
node ID or final KV hash into that stored context.  Thus the later strict
identity helper always rejects the node sidecar, even though the emitted
`build_complete` and `durability_barrier` records carry those fields at their
top level.

The exact missing state is:

```text
_t38c_trace_context_for_node(node_id)
  == {schema_version, run_id, session_id, session_generation, build_rid, warm_rid}
  # missing: node_id, final_kv_hash
```

`_t38c_residency_identity()` requires all of those omitted fields and also
requires `complete_trace_context(context, node_id, final_kv_hash)`.  It returns
`None`; it does not create a target identity.

### Code chain (remote source hash verified)

1. `trace_context.py:59-81` (`make_trace_context`) creates request context
   without `node_id` or `final_kv_hash`.  `_t38c_trace_context_for_req` adds
   the run ID at `unified_radix_cache.py:1089-1120`, but it also does not bind
   a node or final hash.
2. `unified_radix_cache.py:1397-1437`
   (`_t38c_record_node_context`) copies that context verbatim into
   `_t38c_node_contexts`; it does not enrich it with the current node's ID or
   `get_last_hash_value()`.
3. `unified_radix_cache.py:146-181` requires `node_id` and `final_kv_hash`
   in the stored context (as well as the present run ID), then calls
   `complete_trace_context`, which itself requires the stored node/hash at
   `trace_context.py:44-56`.  Therefore it returns `None` for every r15
   target sidecar.
4. The `build_complete` event is still written with explicit *record* fields
   at `unified_radix_cache.py:1670-1684`, but the immediately following
   `_t38c_residency_identity(context, node_id, final_kv_hash)` at `:1685-1690`
   fails, so no target enters `_t38c_build_identities`.
5. Target Mamba/KV detach paths call `_t38c_note_detach` (`:332-355`; Mamba
   component `:440-495`; radix detach `:776-805`).  Its same identity attempt
   fails, so it inserts no target in `_t38c_residency_detached` and remembers
   no expected completion token.
6. A durability event is emitted first at `:5606-5656`.  The subsequent
   `durability_identity = _t38c_residency_identity(...)` at `:5658-5662`
   likewise returns `None`; consequently the conditional body at `:5663-5669`
   performs neither `_t38c_durability_ready.add(...)` nor the canonical
   `_t38c_residency_barrier(...)` invocation.
7. Scheduler polling (`:5796-5801`, helper `:758-773`) sees an empty
   `_t38c_residency_detached` map.  No canonical retry exists.

This is both parts of the observed zero:

- **No canonical residency-barrier invocation:** the durability path reaches
  the 25 `durability_barrier` logs but its identity-gated call at `:5663-5669`
  is skipped for all 25.
- **Diagnostic suppression on any incidental direct fold:** eviction methods
  can call `_t38c_residency_barrier(node_id)` without `expected_identity`
  (`:2307-2310`, `:2316-2319`).  With the malformed sidecar it reaches
  `invalid_identity`, but `_t38c_residency_outcome` refuses `identity=None`
  at `:443-457`.  Hence absence of an outcome is not evidence that no direct
  call occurred; it is an expected blind spot of FIX6 under the same missing
  identity.

## Observed r15 evidence

Remote artifact:
`/data/evidence-gate3-parked/p0-s25-v43-residency-diagnostic-fix6-live-r15/raw/trace-post-stop.jsonl`
SHA-256: `1b72152496f2d2dd5640873833fbae0c2b04132e2a8acfdde5557915b8bf8f92`.

- Local and remote `unified_radix_cache.py` both hash to
  `aaae7bd08135b4ee4e26e15398297b5882ae94541bd56fbc9028bd6155cefafc`.
  The source deployed to r15 therefore contains the cited FIX6 code.
- Both `/tmp/t38c-durable-trace` and `/tmp/t38c-on` existed before launch and
  still existed at final audit.  The shared durable logger wrote 9,697 scoped
  records, disproving a missing marker or global trace-write failure.
- Counts: 25 target `build_complete`; 25 target `durability_barrier` with
  complete top-level six-field identity; zero `residency_barrier`; zero
  `residency_barrier_outcome`; zero warm request/lookup; zero restore.
- For targets specifically: 1,398 detach records, 25 queued host-release
  enqueues, and 25 matching `queued_release_drain_returned` completions.
  Queue draining is therefore not the r15 cause, consistent with r14.
- Each target's final node has build then Mamba-device/KV-device detach about
  1.79--1.96 s before its durability barrier.  Example `p0-s25-s00000`:
  build node 84 at `1788854003762422255`; Mamba-device/KV-device detach at
  `1788854051776699015` / `1788854051777050111`; durability at
  `1788854053591261933`; Mamba-host detach at `1788854251599082605`.
  The ordering supplies opportunities to construct/poll a pending identity;
  none was constructed.
- The monitor continued through the final 30-second stable interval with
  `build=34 durability=25 outcome=0 residency=0 warm=0 restore=0`.

## Competing hypotheses

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| FIX6 was not deployed | Rejected | Remote/local product hashes match and remote contains the outcome helper/call sites. |
| Marker disabled or durable logger failed globally | Rejected | Both markers were present; 9,697 durable records, including all 25 durability events, were written. |
| Host release queue remained undrained | Rejected | Target queue evidence is 25 enqueue / 25 matching drain completion; r14 independently established the same result. |
| A strict predicate (queue/live value/token) returned and emitted its outcome | Rejected | Any valid identity reaching those predicates would emit an outcome.  There are zero records because no valid in-memory identity was formed. |
| Node lookup alone is the root cause | Not supported as primary cause | It may occur on incidental calls, but the deterministic identity failure precedes and skips the canonical durability-triggered invocation. |
| Sidecar omits node/hash binding | Confirmed | Direct source path from `make_trace_context` through `_t38c_record_node_context` to both identity-gated call sites. |

## Vehicle state

The vehicle waiting is **expected fail-closed behavior**, not a scheduler or
lock deadlock.  `p0_session_barrier_vehicle.py:364-378` requires a product
`residency_barrier` to set `cold` before it issues warm work.  With this source
shape, `cold` is permanently unreachable for r15 targets, so the watchdog
waits and no warm/restore can legitimately appear.  The run is therefore a
product lifecycle/liveness failure (and a diagnostic blind spot), but there
is no evidence of a process deadlock: scheduler-backed durability and free
events continued until the authorized stop.

## Narrow next action

**NEEDS_REROUTE — owner: `coder`, fresh Task ID.**  Implement only the
authoritative node-sidecar binding required by the existing identity contract:
when `_t38c_record_node_context` records a node, derive and store an immutable
context retaining the existing run ID plus that exact node ID and final KV
hash, and preserve conflict/ambiguity fail-closed behavior.  Do not relax
`_t38c_residency_identity`, fabricate vehicle evidence, or alter queues,
barrier predicates, or remote launch state.  An independent `tester` task
should then assert that one real six-field target passes build registration,
detach registration, durability-triggered fold, and a first diagnostic
outcome (or barrier), including mismatch/ambiguity rejection.

## Evidence gaps

- r15 cannot retrospectively expose the erased in-memory maps; the engine was
  stopped under the run protocol.  The causal conclusion is nevertheless
  source-deterministic and independently corroborated by every zero outcome.
- Exact counts of incidental non-canonical direct fold calls are not logged;
  FIX6 cannot emit their `invalid_identity` outcome when its identity argument
  is `None`.

## Status packet

- Status: `done`.
- Artifacts: this report; r15 raw trace/reducer/source-hash artifacts named
  above.
- Evidence: remote/local source-hash match, marker audit, immutable event
  counts and target timelines, source call-chain inspection, and r14 queue
  evidence.
- Summary: all 25 durability records are real, but their sidecars cannot form
  the six-field identity.  That skips the canonical residency fold and also
  suppresses its diagnostic outcome.
- Followups: fresh narrow coder task, then independent tester verification and
  a new live run.
- Open issues: no prospective runtime map snapshot; do not treat any current
  telemetry/free-complete record as PASS.
