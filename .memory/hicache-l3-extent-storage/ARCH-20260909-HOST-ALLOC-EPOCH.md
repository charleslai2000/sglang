ENTRY: ACCEPT

# ARCH-20260909-HOST-ALLOC-EPOCH specialist report

```yaml
status: done
task_id: ARCH-20260909-HOST-ALLOC-EPOCH
orchestration_epoch: 20260909-P4
role: architect
branch: 3060-12g-qwen35-4b
decision_authority: orchestrator/existing-gate-owners
```

## Artifacts

- Versioned proposed gate contract:
  `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md`
- This specialist report:
  `.memory/phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`

No product code, remote host, storage, or 3090 path was modified.

## Evidence inspected

- `DEBUG-20260909-HOST-ALLOC-WAKE.md`
- `TEST-20260909-CAPACITY-BUNDLE-LIVE.md`
- `CODE-20260909-ALLOC-FAILED-TERMINAL.md`
- `review/gates/REVIEW-20260909-ALLOC-FAILED-TERMINAL.md`
- `HANDOFF-2026-09-07.md`
- Current branch source around scheduler restore reconciliation,
  HOST_ALLOC wake, prefetch allocation/revoke/finalization, primary and
  auxiliary host-pool allocation/release, tree lock release, and host eviction
- Existing review/gate and Pattern Intake/Novel Mechanism conventions

Confirmed branch identity was `3060-12g-qwen35-4b`. Existing untracked gate
and storage artifacts were preserved.

## Summary

The proposed contract makes the cache mutation boundary the sole owner of a
monotonic primary-host allocability generation and separate required
auxiliary-pool generations. It requires bumps after successful direct KV
frees, completed queued KV release drains, and host lock releases that change
primary evictable leaves/amount; it explicitly forbids bumps on failed alloc,
reservation release, scheduler polling, or unrelated epochs.

A HOST_ALLOC waiter captures a post-cleanup generation vector with exact
failed resource domains and holds no prefetch reservation. A scheduler-owned
FIFO arbiter grants at most one global retry for each newly observed relevant
generation vector. The retry uses the existing bounded full-span
`alloc -> evict -> alloc` authority, never arbitrary crop, miss
classification, or lower-checkpoint inference. Failed retries snapshot all
self-generated frees before parking, preventing self-spin. KV and Mamba/other
auxiliary domains are independent, and hybrid READY still requires complete
all-or-nothing finalization.

The contract also defines request/attempt-correlated telemetry, 15
deterministic regression cases, migration/rollback boundaries, explicit
non-goals, and terminal acceptance criteria.

## Pattern Intake / Novel Mechanism result

The mechanism is classified `NOVEL_MECHANISM`, not EXEMPT, because it creates
a new boundary across tree evictability, host-pool free completion, scheduler
admission/fairness, and multi-pool failure attribution. The contract contains
the required task-local novelty rationale, atomic invariant set, failure
model, oracle, alternatives, and reversibility record.

It does not falsely claim a completed full Pattern Intake. The target
worktree lacks the complete pattern/testing corpus and conforming templates,
and the authorized write set did not permit the separately required intake
path. Under the project-level gate, G1/G2 implementation admission therefore
remains blocked pending a fresh Task ID that creates and pins the complete
Pattern Intake and separate Novel Mechanism artifacts. This is an admission
followup, not a defect in the delivered architecture contract.

## Risks and decisions for orchestrator acceptance

- Accept or revise the proposed one-global-grant-per-generation-vector FIFO
  policy. It minimizes stampede risk but can defer a later fit-capable waiter
  until another causal change; FIFO rotation and T13 bound that trade-off.
- Select the concrete generation owner at the lowest mutation boundary that
  can observe successful per-pool frees. Scheduler must remain read-only.
- Require an exact evictability-change result from the tree boundary; an O(N)
  scheduler scan or free-level inference is not acceptable.
- Require proof of owner-thread serialization or atomic visibility if release
  events can cross threads.
- Require typed/schema-versioned allocation-failure metadata so failed domains
  and post-cleanup cursors cannot be lost in a bare terminal string.

## Followups

All require fresh Task IDs:

1. Complete the repository-conforming Pattern Intake and separate Novel
   Mechanism artifacts, then obtain orchestrator/design-authority acceptance.
2. Dispatch coder implementation only after G1/G2 admission, with exact
   symbol mapping to the accepted contract.
3. Dispatch tester execution for HAE-01 through HAE-15 and request-correlated
   schema evidence.
4. Dispatch independent reviewer acceptance against the exact revision.
5. If source/unit gates pass, separately authorize a pinned live 3060 test.

## Open issues

- Pattern Intake stable-ID disposition and digest pinning are outstanding and
  block implementation admission.
- Concrete generation storage and tree delta interface await orchestrator
  acceptance of the implementation shape.
- No live post-design runtime claim is made.

Extra work requires a fresh Task ID.
