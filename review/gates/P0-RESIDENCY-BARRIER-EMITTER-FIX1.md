ENTRY: ACCEPT

# P0 residency-barrier emitter FIX1 independent gate review

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Scope and inputs

Reviewed the current dirty opt worktree directly, with the requested product
scope:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
- `3090-dev/test_p0_residency_barrier_emitter.py`

Also reviewed the implementation report
`COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md`, the authoritative
`ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`, the debugger report
`DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md`, the prior accepted gates, and
the existing trace-context/host-release support used by this path.

The requested gate file was absent before this review and is the only gate
artifact written here. No product file, test, vehicle, launcher, or remote
process was modified or run. No live claim is made.

The worktree has no task-specific commit boundary and contains pre-existing
dirty product and test changes. The implementation report states that the
Mamba changes were pre-existing; the current aggregate diff nevertheless
contains Mamba instrumentation, so this review distinguishes task attribution
from current behavior rather than treating the whole dirty diff as FIX1.

## Verdict summary

The nominal retry is product-owned: `_t38c_poll_residency_barriers(self)` is
called at the end of the product storage-control drain, after queued KV and
extra-pool host releases have been freed and their exact tokens completed.
The fold also checks V3 context, build identity, durability readiness, a
device detach, absent FULL/Mamba values, exact expected-token completion,
forced-miss/root suppression, and successful logging before recording its
barrier key. The focused nominal and fail-closed cases pass.

The gate is nevertheless **REJECTED** because the implementation does not
establish a unique logical residency barrier per exact build identity and its
retry state is module-global rather than cache/lifecycle-owned. These are
blocking under the explicit exact-identity, idempotency, and no cross-node/
session-join requirements.

## Blocking findings

### F-1 — BLOCKING: duplicate cold cycles can emit multiple barriers for one build identity

Location: `unified_radix_cache.py:398-418`.

`barrier_key` is `(node_id, tuple(sorted(expected)), identity)`, so the
duplicate guard changes when a later detach/free cycle receives new lifecycle
tokens. The implementation then removes the old expected set, allowing a
reloaded and re-evicted node with the same
`(session_id, session_generation, build_rid, node_id, final_kv_hash)` to emit a
second `residency_barrier` for the same logical build. The contract and
acceptance criterion require exactly one logical strict V3 residency barrier;
the supplied test only repeats polling against the same expected token set and
therefore misses this boundary.

Independent AST-extracted probe: after a valid first barrier, replaced the
expected detach set with a second set carrying a distinct lifecycle token and
marked both new tokens complete. The current function emitted two records and
held two barrier keys while the identity tuple remained unchanged.

Acceptance impact: repeated eviction/reload churn can produce duplicate cold
transitions for one build, weakening the vehicle's exact one-barrier evidence
and violating the required idempotent logical lifecycle.

Required follow-up: suppress publication by the full logical identity (or use
an explicitly lifecycle-scoped state machine whose contract proves one
accepted barrier per build), and add a focused repeated detach/recycle probe.
Do not fix this by accepting duplicate event IDs or by changing the vehicle.

### F-2 — BLOCKING: module-global retry state permits cross-cache/node joins and is not concurrency-safe

Locations: `unified_radix_cache.py:143-147`, `:378-418`, and `:425-430`.

`_T38C_DURABLE_DETACHED` is keyed only by `str(node_id)` and is shared by all
`UnifiedRadixCache` instances in the process. `_t38c_poll_residency_barriers`
iterates that global node set and invokes the current cache's
`tree_core.node_by_id(node_id)`, while completion and barrier sets are mutated
without a common lock. The token itself carries session/generation/build/node
fields, but the fold does not require every expected key to belong to the
current cache/context before using it. This leaves the retry boundary dependent
on a process-global numeric node namespace and on serialized callers.

Independent AST-extracted probe: seeded a completed detach set for cache A at
`node-a`, then called the barrier through cache B with the same node ID but a
different session/generation/build identity and B's own build/durability
readiness. The current function emitted a barrier for B using A's global
expected completion set; no B detach was seeded. A concurrent poll/detach can
also race the unsynchronized global iteration/mutation and either miss a retry
or observe a mixed set.

Acceptance impact: a product-authored event can be formed from another cache's
or another lifecycle's completion evidence, violating exact identity and the
explicit no cross-node/session-join requirement. This is a correctness and
potential fail-open issue, not merely a cleanup concern.

Required follow-up: move the fold ledger into the owning cache or key every
ledger entry by an authoritative run/session/generation/build/node/hash scope;
make registration, completion, poll, publication, and retirement atomic under
one lock; and add independent multi-cache/node-collision plus concurrent
poll/release probes. The repair must remain product-owned and fail closed on
ambiguous ownership.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Product-owned bounded retry after release-queue drain | PASS structurally | Product drain calls `_t38c_poll_residency_barriers(self)` after `_drain_release` and `_drain_extra_release`; no vehicle synthesis is present. |
| Exact keyed detach completion, live-value absence, forced-miss/root suppression | PASS for nominal fixture paths | `_t38c_residency_barrier` checks exact expected/completed tokens, FULL/Mamba device/host values, root/tombstone, build identity, durability readiness; focused fixture passes. |
| Exactly one strict V3 barrier and idempotency | **REJECT** | F-1: new lifecycle tokens for the same identity bypass the `(node, expected-set, identity)` duplicate key. |
| Missing/ambiguous/host-only/partial/stale generation fail closed | PASS in supplied fixture; lifecycle scope incomplete | Fixture passes these cases; F-2 prevents acceptance of the broader ownership boundary. |
| Exact V3 payload fields | PASS structurally | The emitted record carries V3 context, exact node/hash, `result=True`, and `cold_residency=True`; `attach_trace_context` supplies session/generation/build/run fields. |
| Existing durability/ACK semantics | PASS by source scope | Retry is placed after existing drain operations; no live/runtime regression claim is made. |
| Focused proof and static checks | PASS | Independent focused test, trace fixture, `py_compile`, AST parse, and `git diff --check` all pass. |
| No global-state leak or cross-node/session join | **REJECT** | F-2 and independent cross-cache probe fail this criterion. |

## Evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — **PASS**:
  `P0 residency-barrier emitter focused checks: PASS`.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4.3 focused checks: PASS`.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-review-pycache python3 -m
  py_compile` over both authorized product files and the focused fixture —
  **PASS**.
- Independent `ast.parse` over both authorized product files and the focused
  fixture — **PASS**.
- `git diff --check` over the authorized product/test paths — **PASS** with no
  whitespace diagnostics.
- Independent AST-extracted repeated-lifecycle probe — **FAIL for acceptance**:
  two distinct expected token sets for one exact identity produced two barrier
  records.
- Independent AST-extracted cross-cache probe — **FAIL for acceptance**:
  cache B published with a different identity using cache A's global expected
  completion set.
- No pytest, engine, remote, launcher, or live S=25 run was performed.

## Followups

- Fresh coder Task ID: repair the logical-identity deduplication and
  cache/lifecycle ownership/locking issues in the product emitter.
- Fresh reviewer Task ID: rerun the focused proof plus repeated recycle,
  node-ID collision, multi-cache isolation, and concurrent poll/release
  probes.
- Fresh tester Task ID may perform live S=25 RH-off acceptance only after this
  unit gate is accepted; this review does not authorize that run.

## Open issues

1. Gate remains **REJECTED** on F-1 and F-2; no product acceptance is granted.
2. Fresh live residency and warm/restore evidence remains unverified and was
   intentionally not attempted.
3. Aggregate dirty-worktree attribution remains a process caveat; prior dirty
   changes were not silently included in this FIX1 verdict.

## Status packet

- Status: `done`
- Artifacts: this gate file; assigned memory report at
  `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md`.
- Evidence: source inspection, focused/static checks, repeated-lifecycle probe,
  and cross-cache isolation probe.
- Summary: product-owned retry exists and nominal guards pass, but exact
  one-barrier lifecycle and global ownership/concurrency boundaries fail.
- Followups: implement F-1/F-2 under fresh Task IDs, then obtain a fresh
  independent review before any live run.
- Open issues: F-1, F-2, no live evidence, dirty attribution boundary.
