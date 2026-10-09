ENTRY: ACCEPT

# ARCH-20260909-PATTERN-INTAKE specialist report

```yaml
status: done
task_id: ARCH-20260909-PATTERN-INTAKE
orchestration_epoch: 20260909-P4
role: architect
source_branch: 3060-12g-qwen35-4b
source_revision: 1e6a82194e7f5d071823e4abb68514c6d421e4b3
implementation_admission: BLOCKED
decision_authority: orchestrator_and_existing_gate_owners
```

## Artifacts

- `review/gates/PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md`
  (`PI-HOST-ALLOC-EPOCH-20260909-01`, SHA-256
  `85120575ae9e21be689e31d36d911972093cf58dadce8f5fd45b3d73f7d4d82c`)
- `review/gates/NOVEL-MECHANISM-20260909-HOST-ALLOC-EPOCH.md`
  (`NM-HOST-ALLOC-EPOCH-20260909-01`, SHA-256
  `8c0b7758f02d0016a5cc836466ad7c659aaa9e41ef7d442e33a076b9b223ccfb`)
- This report:
  `.memory/phase2-hicache-design/work/ARCH-20260909-PATTERN-INTAKE.md`

The two versioned gate paths are in the `sglang-3090-24g-opt` worktree. This
report is in the separately designated `sglang-3090-24g-hicache` memory tree.
No product code, remote host, storage content, deployment, or 3090 behavior
was modified.

## Evidence

- Confirmed target branch and revision:
  `3060-12g-qwen35-4b` at
  `1e6a82194e7f5d071823e4abb68514c6d421e4b3`.
- Read the architecture gate and report, debugger report, and handoff; their
  SHA-256 pins are recorded in the Pattern Intake.
- Searched gate, storage, memory, source, test, and reachable Git-history
  namespaces with the exact commands recorded in intake section 3.
- Found no full Pattern Intake template/corpus or separate Novel Mechanism
  declaration. The only pattern-intake-area artifact is the narrow
  `EXEMPT-3060-RUNTIME-COMPAT.md`, which cannot supply a full schema.
- Pinned eight relevant implementation/test files by Git blob and dispositioned
  stable implementation, anti-pattern, bug-derived, harness/test, benchmark,
  deferred, and missing IDs.
- Produced 15 atomic invariant-to-pattern-to-test mappings covering the
  architecture contract's HAE-01 through HAE-15 acceptance matrix.

## Summary

The intake adopts the existing full-span allocator/reclaimer, non-miss
HOST_ALLOC state, T13 clock, and hybrid all-or-nothing finalization. It adapts
Ready Horizon's causal-cursor concept, demand issue accounting, FIFO ordering,
tree lock mutation reporting, and successful release drains. It explicitly
rejects the free-full-span scheduler predicate, periodic/generic retry,
retained cache-mode reservations, scalar KV-only wake for hybrid failures, and
arbitrary crop/lower-frontier inference.

The separate Novel Mechanism declaration records why those patterns do not
compose without a new boundary, 13 atomic invariants, the failure model,
observable oracle, alternatives, dependency direction, migration, rollback,
removal, risks, and non-goals. Both artifacts link to the pinned architecture
contract and reserve acceptance authority to the orchestrator and existing
gate owners.

## Admission decision

G1/G2 implementation admission is **BLOCKED**, for two concrete reasons:

1. The pinned architecture artifact and Novel Mechanism declaration have not
   been accepted by the orchestrator/design authority; neither may
   self-approve.
2. The project contract requires a full intake conforming to
   `storage/review/gates/pattern-intake/`, but the repository has no full
   template/corpus and this dispatch permits writes only under
   `review/gates/`. The delivered intake uses the closest observed gate schema
   and explicitly does not claim canonical conformance.

These are governance/admission prerequisites, not product-code blockers. The
orchestrator may resolve the second by explicitly accepting the documented
closest-schema substitute, or by issuing a fresh Task ID with the canonical
schema/corpus and required write authority. After both are resolved, coder,
tester, and independent reviewer gates remain required.

## Followups

- Orchestrator/design authority: accept, revise, or reject the pinned
  architecture contract, Pattern Intake substitution, and Novel Mechanism.
- If canonical conformance is required, dispatch a fresh Task ID supplying the
  missing full schema/corpus and authorizing its required path.
- Only after admission, fresh Task IDs may cover implementation, deterministic
  HAE-01..15 verification, independent review, and separately authorized live
  3060 evidence.

## Open issues

- Acceptance decision IDs are not yet available.
- Canonical full-template/corpus availability and path authority are unresolved.
- Concrete generation owner, exact tree delta interface, and cross-thread
  visibility remain implementation-shape proof obligations under the accepted
  architecture gate.

Extra work requires a fresh Task ID.
