ENTRY: ACCEPT

# P0 trace-context V4.2 independent gate review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V4.2`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Product trace-gate verdict: **REJECT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Revision identity and scope

Reviewed the dirty worktree at commit `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`
on branch `3090-24g-opt`, compared with
`review/gates/P0-TRACE-CONTEXT-V4.1.md`. Current hashes are:

- `trace_context.py`: `3cac886656314ca3736e67ac0eb29dcc7eed3c991c91cd5a9e901308db67ede7`
- `unified_radix_cache.py`: `4b6b70ee847edaa4b811155ceda82afc6fa3bb21937e4c39c52e68bddb1dfc88`
- `hybrid_cache_controller.py`: `440c75cf24803f7ac695a9432c96176170a72f3c4bb3223ab7466fe5f76903ec`
- `mamba_component.py`: `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f`
- `test_p0_trace_context_v4.py`: `5054e8180e7914de2553e4d3c90bbd88802228d748f864d6f28e18a3ad5d3da8`

The worktree also has tracked changes in `extent_allocator.py` and
`extent_file_backend.py`, plus untracked vehicle/tool files. The V4.2 coder
report declares only four authorized product/test files, so those extra changes
remain attribution/scope open issues and are not silently accepted here.

## Evidence

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-rev-v42 python3 -m py_compile` on
  trace, unified, controller, Mamba, extent allocator/backend, and the focused
  fixture — **PASS**.
- Independent `ast.parse` on trace, unified, controller, Mamba, and the fixture
  — **PASS**.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4.2 focused checks: PASS`.
- `git diff --check` — **PASS**.
- Targeted `python3 -m pytest 3090-dev/test_p0_trace_context_v4.py -q` —
  **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
- Remote engine and vehicle — **not run**, as required.
- Direct helper probe — `complete_slot_context(..., token=None)` returned the
  registered token for the same digest, confirming the fallback described in
  F-1 below.

## Findings

### F-1 — High / blocking: marker-on release can still use digest fallback, and marker transitions can mispair queues

Locations: `hybrid_cache_controller.py:405-417,491-501`,
`unified_radix_cache.py:4719-4725,4771-4777`, and
`trace_context.py:99-100,185-227`.

The lock now correctly makes the page enqueue and token enqueue one producer
critical section, and the unified drain uses the pair helper. That fixes the
V4.1 producer/drainer race only when a real token exists and the marker state is
stable. It does not establish the required exact-token contract for all
marker-on releases:

1. `remember_slot_context` returns `None` when `trace_context` is absent.
2. `_append_host_mem_release_pages` still queues that `None` token.
3. The drain passes `token=None` to `_t38c_note_completion`.
4. `complete_slot_context` treats `token=None` as permission to search by
   digest, so a same-digest record can be completed by the wrong release.

There are live call paths with no context argument, including the SWA/Mamba
`FreeComponentHostSlot` paths (`swa_component.py:1142-1145` and
`mamba_component.py:1133-1136`) and the controller's newly-created tail
transfer (`hybrid_cache_controller.py:1305-1311`). The direct probe reproduced
the fallback: a registered token was completed by passing `token=None`.

Additionally, the producer always queues the real page, while the token is
queued only when its contemporaneous marker check is on; the drain chooses the
paired path using a later marker check. An off-to-on transition can therefore
pair an old marker-off page with a later marker-on token, and an on-to-off
transition leaves trace tokens stale. No marker epoch or trace-mode bit is
stored in the queue item.

Acceptance impact: **merge-blocking**. The release handoff is not universally
exact and can produce a false residency completion or cross-attempt/session
join. The focused fixture models a valid pair but does not exercise a `None`
token or marker transition.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.2-EXACT-RELEASE`.
Make missing-context releases diagnostic-only (never digest-completing), bind
the trace mode/token to the queue item, and add same-digest plus marker
transition coverage.

### F-2 — High / blocking: rank-sharded Mamba durability is still local, not an all-rank proof

Locations: `hybrid_cache_controller.py:1126-1146,1155-1229`,
`unified_radix_cache.py:4410-4503,4596-4648`.

The local Mamba count/digest check correctly rejects an empty transfer and a
zero-page or partial local result. However, `should_backup` explicitly sends
Mamba to every rank, while the ACK and candidate are built from only that rank's
`operation.pool_storage_result`. No code populates
`_t38c_expected_rank_set`; the only occurrences are `getattr` reads. The
candidate and barrier therefore carry `expected_rank_set=None` and
`rank_set_unavailable=True`, and the barrier condition does not reject that
state.

Consequently, one rank can emit `durability_barrier` after its local Mamba write
succeeds even if another rank's shard failed or never ACKed. The per-event
`rank` field is only the emitting process's rank; it is not an expected-rank
set or an all-rank completion proof. The key digest/count is propagated through
the ACK/candidate/barrier, but the rank metadata is not authoritative.

Acceptance impact: **merge-blocking** for the required Mamba durability proof;
the barrier can assert combined durability for an incomplete rank-sharded
sidecar. The fixture only checks zero keys and local counts and cannot detect
cross-rank failure.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.2-MAMBA-RANKS`.
Populate the expected rank set from the actual transfer topology, aggregate or
otherwise join all rank ACKs by operation/attempt/node/hash, and prohibit a
combined barrier when rank evidence is unavailable or incomplete.

### F-3 — Medium: session retirement still leaves completed queued-token state

Locations: `unified_radix_cache.py:747-769,780-788` and
`trace_context.py:230-260`.

V4.2 improves queued-token retirement by replacing tokens for the released
session with inert `None` values while preserving the real release FIFO. It
does not remove completed-token entries for queued releases from
`_T38C_DURABLE_COMPLETED`: session retirement derives `retired_tokens` only
from `_T38C_DURABLE_DETACHED`. A queued release can be completed and recorded by
`_t38c_note_completion` without ever being in the detached set. The source slot
record is then removed by `retire_slot_contexts(session_id)`, but the global
completion tuple survives until full reset.

Acceptance impact: **required lifecycle follow-up**, though secondary to F-1 and
F-2. It leaves stale process-global state and weakens release/reopen cleanup
guarantees. Reset does clear the set correctly.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.2-RETIRE-COMPLETIONS`.
Retire all session-owned completion tuples, including non-detach queue tokens,
under the same lifecycle helper and add release/reopen assertions.

### F-4 — Medium / compatibility acceptance open: marker-off query behavior remains inherited and unproven

Location: `hybrid_cache_controller.py:826-870`.

The V4.1 rejection already recorded that `_storage_hit_query` performs an
additional `batch_exists`, truncates hashes, and rewrites trailing transfers
even when the durable marker is absent. V4.2 does not add a marker gate around
that query behavior, so marker-off equivalence remains unproven. The trace
registration/logging itself is marker-gated, and the marker-off release drain
uses the original page-only FIFO path; I found no new V4.2-only trace branch
that changes those two facts.

This is therefore bounded as an inherited V4.1/V2 query compatibility issue,
not silently reclassified as fixed by V4.2. It still prevents claiming full
marker-off compatibility unless the intended query change is separately
accepted or covered by a baseline-equivalence test.

Acceptance impact: **compatibility evidence remains open**, but it is not the
blocking reason for this verdict.

## Positive checks and non-findings

- The old `_t38c_durability_current` selector is absent. Promotion selection is
  node-owned and returns no candidate when same-hash candidates are ambiguous.
- A `durability_barrier` is emitted only after `complete_trace_context` verifies
  session ID, session generation, build RID, node ID, and final KV hash.
- Empty/zero-page Mamba transfers make `mamba_durable` false locally; key digest,
  key count, expected/succeeded page counts, and rank fields are carried into
  the ACK/candidate/barrier records. F-2 explains why the rank portion is not
  sufficient for acceptance.
- Reset clears trace evidence, completion/barrier sets, slot contexts, and the
  trace-only handoff queues.

## Verdict and P0 distinction

The V4.2 product trace gate is **REJECTED** because F-1 and F-2 are blocking.
The focused fixture passing does not overcome the `None`-token digest fallback
or the missing all-rank Mamba proof. F-3 and F-4 remain required follow-ups.

P0 runtime acceptance remains **BLOCKED** independently of this product verdict.
Keep P0 blocked until the live **S=25 RH-off** vehicle provides the required
runtime evidence: barrier-before-lookup ordering, 25/25 build evidence, exact
`s00002` A-E classification, cleanup, and runtime health. This review did not
run that vehicle or any remote engine.

## Status packet

- Status: `done`
- Artifacts: this gate report only; no reviewed artifact, vehicle, memory file,
  or remote process was modified or run.
- Evidence: current dirty revision/hash capture, V4.1 comparison, source and
  concurrency-path inspection, direct fallback probe, py_compile PASS, AST PASS,
  focused fixture PASS, diff-check PASS, and pytest dependency blocker.
- Followups: fresh Task IDs are listed for each actionable finding; no extra
  work was accepted under this invocation.
- Open issues: F-3 lifecycle cleanup, F-4 inherited marker-off compatibility,
  the declared-versus-actual dirty scope, unavailable pytest dependencies, and
  the required live S=25 RH-off vehicle evidence.
