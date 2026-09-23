ENTRY: ACCEPT

# P0 trace-context V4.1 independent gate review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V4.1`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Product trace-gate verdict: **REJECT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Dirty revision identity

Reviewed the current dirty worktree at commit
`9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` on branch `3090-24g-opt`
(`origin/3090-24g-opt`). The worktree contains the V4.1 candidate plus other
uncommitted product and vehicle files. The relevant V4.1 file hashes are:

- `trace_context.py`: `e332e24f98f3da433c470cd264f167c8a88d8e50dbf0c961657c2cb510fc118b`
- `unified_radix_cache.py`: `46e1a74865a364a26f4305038373cf7a25c1a6022524349e865158e4a34b8dfd`
- `hybrid_cache_controller.py`: `26be7149a1b3e4470d417927910fcde0161e21152cff9dbcd54dd3850565b7a6`
- `test_p0_trace_context_v4.py`: `bbaf919c0e74c1b565137bd89184fb4e08b0b18f47c29693bbb9704aa01324d6`

## Reviewed scope

Reviewed the authoritative V3 gate, V4 and V4.1 implementation reports, and
the debugger findings. Reviewed code paths in:

- `python/sglang/srt/mem_cache/trace_context.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`

The extent and Mamba paths were inspected only for their interaction with the
V4.1 trace, durability, and residency contracts. No reviewed product file,
memory file, vehicle, or remote process was modified or run.

## Evidence commands and results

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `git status --short --branch` — **PASS / observed dirty worktree**; the
  tracked product files and untracked V4.1 fixture are present, along with
  unrelated vehicle/tools files.
- `git rev-parse HEAD`, `git diff --stat`, and `git diff --check` — **PASS**;
  `git diff --check` reported no whitespace errors.
- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4 focused checks: PASS (F1-F5/static durability contract)`.
  This is dependency-free and primarily AST/source plus small helper-model
  coverage; it does not instantiate the controller, storage backend, or queue
  threads.
- `python3 -m py_compile` on the six reviewed product Python files and the
  focused fixture — **PASS**.
- Independent `ast.parse` on the same files — **PASS**.
- `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q`
  — **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
  No dependency was installed.
- Remote engine/vehicle execution — **not run**, as explicitly prohibited and
  intentionally deferred.

## Findings

### F-1 — High / blocking: the exact release token is not atomically paired with the queued release item

Locations: `hybrid_cache/hybrid_cache_controller.py:401-410,469-478` and
`unified_radix_cache.py:4627-4639,4664-4679`.

`_append_host_mem_release_pages` first puts the real page into the release
queue, then computes/registers and puts its trace token into a separate FIFO.
The drain consumes the real queue before calling `_t38c_pop_host_mem_release_token`,
which checks `Queue.empty()` on that separate queue. This is not an atomic
enqueue/dequeue pair. The producer is not scheduler-only: the storage
prefetch IO thread reaches `_sync_trailing_keys` and calls
`append_host_mem_release` at `hybrid_cache_controller.py:1231`, while the
scheduler drains the release queues.

A scheduler drain can therefore observe the page before its token is queued,
return `None`, and complete by digest fallback. The late token then remains in
the metadata FIFO and can be consumed for the next page. Because
`complete_slot_context(..., token=...)` searches the token globally rather than
requiring the current page key, this can attribute completion and context to a
different page/node, including same-digest and reused-slot cases. The focused
fixture models an already-formed FIFO but does not exercise this producer/consumer
race.

Acceptance impact: **merge-blocking F5 failure**. The release drain does not
genuinely consume the exact enqueue token under concurrent production, so the
residency barrier can be missing or keyed to the wrong lifecycle.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.1-ATOMIC-RELEASE-TOKEN`.
Make the token part of the same queue item or otherwise establish an atomic
trace-only handoff, then add a concurrent producer/drainer fixture covering
same-digest reverse ordering and reset.

### F-2 — High / blocking: attempt records are keyed, but promotion still selects a mutable per-node pointer

Locations: `unified_radix_cache.py:4437-4469` and
`unified_radix_cache.py:4576-4589`.

The candidate dictionary is keyed by `(operation_id, attempt_id)`, but
`_t38c_durability_current[node_id]` is a single mutable pointer overwritten on
every ACK. Retroactive promotion then reads only that pointer and accepts it
when its final hash equals the currently promoted node hash. There is no
tree-owned write generation, frontier publication identity, or other binding
from the promoted node to the selected attempt. An older outstanding attempt
can remain in the dictionary while a later same-hash attempt is selected; the
hash check cannot distinguish those attempts. The code consequently retains
attempt records without making the promotion join exact.

The fixture's `_DurabilityFixture` has the same `current[node]` selector and
only proves that an older record remains in a model dictionary. It does not
prove that the promoted node selected the attempt whose write established that
frontier, nor does it test a same-hash repeated attempt with opposite ACK order.

Acceptance impact: **merge-blocking F2 failure**. The implementation can still
overwrite the effective outstanding candidate and cannot prove that a
retroactively promoted child barrier belongs to its own storage attempt.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.1-ATTEMPT-BINDING`.
Bind every candidate to a tree-owned write generation/attempt at submission,
select only that binding for each promoted node, and test child-before-parent,
same-hash repeated attempts, partial Mamba, and exactly-once retirement.

### F-3 — High / blocking: a combined barrier can be emitted without authoritative session/build context

Locations: `unified_radix_cache.py:4409-4414,4534-4558` and
`trace_context.py:31-44,47-54`.

`make_trace_context` correctly fails closed when session generation or build RID
is absent, but `_drain_backup` still stores a durable candidate when
`operation.trace_context` is `None`. The barrier condition checks only the KV
and Mamba booleans; it does not require a non-null context or exact
`session_id/session_generation/build_rid`. `_t38c_durable_log` removes a null
`trace_context` and emits the event without those fields.

Thus a marker-on write from a request without scheduler-owned generation, or a
node created before a valid trace context was recorded, can produce a
barrier-shaped event with operation/node/hash but no authoritative session or
build identity. Such an event cannot be joined to the required session and
should be `NOT_VERIFIED`, not accepted as a barrier.

Acceptance impact: **merge-blocking F4 failure**. The emitted barrier is not
the required exact operation/attempt/node/hash/context fact.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.1-BARRIER-CONTEXT`.
Require the complete context tuple before candidate/barrier publication and
add a missing-generation fixture that asserts no combined barrier is emitted.

### F-4 — High: Mamba durability is count-only and treats an empty Mamba transfer as durable

Locations: `unified_radix_cache.py:4428-4431`,
`hybrid_cache/hybrid_cache_controller.py:1150-1155`, and
`storage/extent/extent_file_backend.py:151-171`.

The barrier's Mamba proof is `bool(mamba_transfers) and
mamba_succeeded_pages == mamba_expected_pages`. A present transfer with zero
keys/pages therefore satisfies `0 == 0`. The same count-only rule is emitted
at ACK time. Extent commit logging is aggregated per extent and page count;
it does not preserve the exact Mamba key set or commit-event references that
the barrier can join. No expected rank set is included for rank-sharded Mamba
ACKs.

Acceptance impact: **blocking F4 durability-evidence gap**. An omitted/empty
sidecar or incomplete rank/key chain can be represented as explicit-looking
`mamba_durable=true`, and the barrier does not independently prove the exact
KV+Mamba commit chain.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.1-MAMBA-EVIDENCE`.
Require non-empty expected Mamba keys/ranks, preserve the operation/attempt
binding through per-key or keyed-set commit evidence, and reject zero/partial
sidecar evidence from combined barriers.

### F-5 — Medium: session retirement leaves completed records for non-detach queue tokens

Locations: `unified_radix_cache.py:747-780` and
`trace_context.py:202-233`.

`_t38c_retire_session_trace` derives `retired_tokens` only from
`_T38C_DURABLE_DETACHED`. Queued prefetch-release tokens registered by the
controller are not necessarily in that set, so their entries in the global
`_T38C_DURABLE_COMPLETED` set survive session release even after
`retire_slot_contexts(session_id)` removes the source records. Reset clears the
set, but ordinary release/reopen does not retire all session-owned completion
state. The monotonic token prevents an immediate false match, but this violates
the stated lifecycle-retirement contract and leaves stale process-global
state.

Acceptance impact: **non-blocking follow-up after the blocking F1-F4 repairs**;
it is still required before claiming complete lifecycle closure.

Fresh task recommendation: include all session-owned completion tokens in the
same retirement helper used for detached tokens and add release/reopen cleanup
assertions.

### F-6 — Medium / compatibility risk: marker-off execution is not behavior-preserving in the storage query path

Locations: `hybrid_cache/hybrid_cache_controller.py:796-823,875-890` and
`hybrid_cache/hybrid_cache_controller.py:1205-1239`.

With the trace marker absent, `_storage_hit_query` still performs an additional
KV `batch_exists`, truncates the hash list, rewrites trailing sidecar keys, and
then calls `batch_exists_v2`. This is unconditional product-path behavior; the
baseline called `batch_exists_v2` directly with the original hash/transfer set.
The same path can enqueue tail releases from the storage IO thread. No
marker-off runtime fixture compares release counts, sidecar hit results, or
backend call behavior against the baseline. The dependency-free test only
checks the trace API and source contracts.

Acceptance impact: **compatibility acceptance is not established**. This must
be isolated to the intended hybrid query fix or covered with marker-off and
marker-on equivalence tests before the trace gate can be accepted.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.1-MARKER-OFF-REGRESSION`.
Prove identical allocator/release and storage-query semantics with the marker
absent; keep any intentional sidecar alignment change separately scoped and
tested.

## Positive checks and non-findings

- F1 API shape is now statically compatible: `append_host_mem_release` accepts
  `trace_context`, and the completed-prefetch call supplies it.
- Session context maps include session generation/build RID, and public open,
  radix release, streaming release, and full reset call retirement helpers.
- The barrier record includes operation ID, attempt ID, node ID, final KV hash,
  and explicit KV/Mamba booleans when it is emitted.
- No broad exception was found around the normal storage ACK result that would
  convert a failed write into a successful product ACK. Broad catches are
  confined to diagnostic logging/state publication, but they can hide trace
  observability failures and do not replace runtime evidence.

## Verdict and P0 distinction

The product trace gate is **REJECTED** because F1, F2, and F3 are blocking and
F4 leaves the required exact KV+Mamba evidence unproven. The focused fixture
passing does not overcome the concurrent queue race or the missing runtime
attempt/context bindings.

P0 runtime acceptance remains **BLOCKED** independently of this product verdict.
Even after a future product-gate ACCEPT, P0 must remain blocked until the live
S=25 RH-off vehicle passes with the required barrier-before-lookup ordering,
25/25 build evidence, exact `s00002` A-E classification, cleanup, and runtime
health. This review did not run that vehicle or any remote engine.

## Status packet

- Status: `done`
- Artifacts: this gate report only; no reviewed artifact, vehicle, or memory
  file was modified.
- Evidence: dirty identity/hash capture, AST/py_compile PASS, focused fixture
  PASS, `git diff --check` PASS, and pytest dependency blocker reproduced.
- Followups: fresh Task IDs listed per blocking finding; no extra work accepted
  under this invocation.
- Open issues: live runtime behavior, project pytest coverage, and the P0
  S=25 RH-off vehicle remain intentionally deferred.
