# Novel Mechanism declaration — host allocability generation and FIFO wake

```yaml
schema_version: closest-existing-gate-schema-1
artifact_id: NM-HOST-ALLOC-EPOCH-20260909-01
mechanism_id: NM-HOST-ALLOC-EPOCH-1
task_id: ARCH-20260909-PATTERN-INTAKE
orchestration_epoch: 20260909-P4
target_revision: 1e6a82194e7f5d071823e4abb68514c6d421e4b3
classification: NOVEL_MECHANISM
status: PROPOSED_FOR_ORCHESTRATOR_ACCEPTANCE
architecture_contract: review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md
architecture_contract_sha256: 9bdee4894eec0a6319d390ab0e92e5c7ca8e9e2885e3a16eb594fd3626c6a058
pattern_intake: review/gates/PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md
approval_authority: orchestrator_and_existing_architecture_gate_owner
implementation_authority: none_granted
```

## 1. Novelty trigger and known-pattern fit

No known local pattern fits the whole mechanism. The proposed composition
creates a new authority and failure boundary across:

```text
successful host free / lock-to-evictable tree mutation
  -> cache-owned per-pool generation vector
  -> typed post-cleanup request cursor
  -> scheduler-owned one-vector/one-grant FIFO arbiter
  -> existing full-span allocator/reclaimer
  -> existing all-or-nothing hybrid finalizer
```

Ready Horizon provides a causal cursor pattern, demand restore provides
bounded issue accounting, buffer mode provides FIFO ordering, and the cache
already owns full `alloc -> evict -> alloc`. None reports lock-derived host
evictability, attributes multi-pool allocation failure, or globally limits
HOST_ALLOC retries per relevant generation vector. Reusing Ready Horizon's
free-level-derived `_ready_host_release_epoch` would preserve the confirmed
circular wait. Retaining buffer-mode operations would change reservation and
lifecycle ownership. The exact evidence and dispositions are pinned in
`PI-HOST-ALLOC-EPOCH-20260909-01`.

## 2. Atomic invariants

| ID | Invariant |
| --- | --- |
| `NM-INV-001` | Generation is monotonic per cache instance and pool; reset changes instance identity. |
| `NM-INV-002` | Successful non-empty direct free bumps its pool exactly once after completion; no-op or failed free does not. |
| `NM-INV-003` | Queue enqueue does not bump; successful non-empty release drain bumps the affected pool once per completed batch. |
| `NM-INV-004` | Host unlock bumps a pool iff the completed tree mutation exposes a new relevant evictable candidate/amount. |
| `NM-INV-005` | Failed alloc/reclaim, reservation release, scheduler polling, elapsed time, restore state changes, and unrelated epochs never bump. |
| `NM-INV-006` | Failed-attempt cleanup and unlock/free effects complete before the waiter captures its cursor; the waiter holds no reservation. |
| `NM-INV-007` | Eligibility requires a newer generation for every actually blocked domain; a generation is opportunity, never fit proof. |
| `NM-INV-008` | One newly observed relevant vector grants at most one global FIFO retry; budget denial does not consume the grant. |
| `NM-INV-009` | One grant executes one complete-frontier allocation with at most one existing reclaim and one re-allocation; no internal retry loop. |
| `NM-INV-010` | Failed retry cleans up, captures its post-attempt vector, and rotates to FIFO tail, preventing same-vector/self-generated spin. |
| `NM-INV-011` | Allocation pressure remains non-miss HOST_ALLOC; no crop or lower-frontier inference is introduced. |
| `NM-INV-012` | Hybrid READY requires complete KV and every required sidecar from the same attempt; per-pool generations are independent. |
| `NM-INV-013` | With no relevant generation change, HOST_ALLOC issues zero retries and preserves the original T13 clock. |

## 3. Failure model

Precondition: a positive, sidecar-complete L3 query reaches full-span staging
allocation and one or more required host domains cannot allocate. Concurrent
requests can compete for capacity, while frees and lock releases can occur
between scheduler passes.

Unsafe outcomes are permanent wait despite newly reclaimable material;
thundering-herd retries; same-request self-spin; a parked reservation blocking
its own progress; false miss; arbitrary crop; lower-frontier invention;
cross-pool false wake; KV-only hybrid READY; stale cursor comparison after
cache reset; and timeout extension through retries.

The safe degraded outcome is to remain in HOST_ALLOC without a reservation
until a relevant causal change or unchanged T13 timeout. A failed retry must
atomically release all partial staging and capture the resulting vector.

## 4. Observable oracle and evidence chain

The authoritative oracle is the conjunction of:

- tree/pool before-after state at each mutation;
- per-pool generation before/after and cache-instance identity;
- allocator/reclaimer call history and complete requested span;
- request cursor, blocked-domain set, FIFO sequence, and last-granted vector;
- reservation ledger and unchanged restore timeout start;
- restore event/miss evidence; and
- complete KV plus sidecar transfer/finalization for one RID and attempt.

Telemetry and tests observe these owners and cannot become fit or wake
authority. The deterministic cases are HAE-01 through HAE-15 in the pinned
architecture contract and the atomic mappings `PI-MAP-001..015` in the linked
intake. A separately authorized live 3060 reproduction is required for a
runtime-liveness claim; the pre-change q/x/w bundle is bug evidence only.

## 5. Alternatives considered

| Alternative | Disposition and reason |
| --- | --- |
| Full-free-level scheduler polling | Rejected: cannot see lock-to-evictable change and suppresses the reclaim call needed for progress. |
| Retry every pass or every N passes | Rejected: non-causal, amplifies load, permits same-state repetition. |
| Wake every waiter on any release | Rejected: stampede and no blocked-domain correctness. |
| Scalar KV generation | Rejected for hybrid scope: auxiliary pressure can remain unresolved. |
| Hold/reserve capacity while parked | Rejected: can block the causal capacity transition. |
| Retain cache operation in buffer FIFO | Not adopted: changes cache-mode lifecycle and reservation ownership. |
| Search or crop to lower frontier | Rejected: no sidecar-complete lower checkpoint authority exists. |
| Per-pool mutation generation + post-cleanup cursor + one FIFO grant | Proposed: causal, bounded, independently observable, and preserves allocator/finalizer authority. |

## 6. Interfaces, ownership, and dependencies

- The lowest common cache/pool mutation boundary owns generation state and
  post-success bumps. Tree lock release reports exact changed pools/deltas.
- `UnifiedRadixCache` exposes a read-only, cache-instance-qualified snapshot.
- Allocation failure crosses to scheduler as typed/schema-versioned failed
  domains, requested units, positive-hit facts, and post-cleanup snapshot.
- Scheduler owns request FIFO sequence and grant consumption, never generation
  mutation, eviction, allocation, or fit truth.
- Existing allocator/reclaimer and hybrid finalizer remain authoritative.
- There is no host-pool callback into scheduler request objects and no durable
  or cross-process state.

If mutation and observation are not proven owner-thread serialized, the
implementation must provide atomic/locked visibility. That proof is an
implementation-gate prerequisite, not authority to redesign this declaration.

## 7. Migration, rollback, and removal

Migration is source-local and non-durable:

1. Add cache-instance identity and per-pool counters at the mutation owner.
2. Add exact tree delta reporting and post-success bump sites.
3. Add typed failure/snapshot transfer atomically across producer and consumer.
4. Add scheduler cursor/FIFO arbiter behind the accepted HOST_ALLOC path.
5. Replace only the HOST_ALLOC free-full-span admission predicate after static
   coverage and deterministic tests pass.

During migration, missing or mismatched typed metadata fails closed by leaving
the request bounded by T13; it must not fall back to free-level fit as proof of
the new contract. No persisted data migration or mixed-process protocol is
claimed.

Removal is the reverse source change. Counters, cursors, and arbiter have no
durable residue. Rollback restores the known pre-change circular-wait risk and
must be recorded as such. The architecture seam allows an accepted future
arbiter policy to replace FIFO without changing mutation or allocator
authority, but that is fresh design work.

## 8. Scope, non-goals, risks, and decision request

Scope and non-goals are those in the linked Pattern Intake and architecture
contract. In particular, no 3090, remote, storage, persistence, HiRadix,
lower-frontier, performance, deployment, or product-code change is approved.

Principal trade-off: one global grant can defer a later fit-capable waiter
after an insufficient head attempt. FIFO tail rotation and T13 make this
bounded, but acceptance of that fairness/load trade-off belongs to the
orchestrator/design authority. Exact lock delta computation and cross-thread
visibility also remain implementation proof obligations.

Decision requested: accept, revise, or reject
`NM-HOST-ALLOC-EPOCH-20260909-01` together with the pinned architecture
contract. This declaration does not approve itself. Until that decision and
the Pattern Intake governance prerequisite are resolved, G1/G2 implementation
admission remains **BLOCKED**.

Extra corpus, research, design, implementation, test, deployment, remote,
storage, or 3090 work requires a fresh Task ID.

Status: `done` for the authorized Novel Mechanism declaration;
implementation admission: `BLOCKED`.
