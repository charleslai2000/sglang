ENTRY: ACCEPT

status: blocked
task_id: REVIEW3060-RH-PREADMISSION-20260909
orchestration_epoch: 20260909-rh-ab24
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: 3785c99759d4026ebc4364ee46edb07987ed3b1a
gate_artifact: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260909-RH-PREADMISSION.md

## Artifacts

- Gate acceptance artifact:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260909-RH-PREADMISSION.md`
- This report.

## Evidence

- Read all mandatory architecture, Novel Mechanism, Pattern Intake, coder,
  tester, and debugger inputs named in the dispatch.
- Reviewed commits `3ddc39c223` and
  `3785c99759d4026ebc4364ee46edb07987ed3b1a`, including the implementation
  range and fix-only diff.
- Ran the committed dependency-free regression with bytecode writes disabled:
  `Ran 2 tests ... OK`.
- Independently ran in-memory AST parse/compile on six changed files: PASS.
- Ran `git diff --check`: PASS.
- Independently inspected all six scheduler prefetch call sites and the
  request-local claim, terminal, RH pass, enqueue, abort, and admission paths.
- Confirmed focused dependency-backed tests remain unavailable because
  `orjson` is missing, as recorded by the current tester.

## Summary

The first tester BLOCK is resolved by the target fix: the gate-skip branch no
longer reads an unassigned `outcome`, and the exact no-I/O regression passes.
The RH-ON queue-first/RH-OFF call-order split and explicit origin plumbing are
also structurally present.

The target remains blocked. The successful storage-gate path returns
`DECLINED` after applying `PREFETCH_ISSUED`, so `_prefetch_kvcache` releases the
active claim. Release is also not attempt-correlated, and the required typed
result/telemetry schemas are incomplete. Independently, the supplied design
gates are still proposed/conditional and pinned to an earlier revision rather
than authorizing this implementation.

## Findings

1. **BLOCKER** — Gate admission is unresolved. The architecture input declares
   implementation admission blocked and acceptance pending; the Novel Mechanism
   is proposed/non-self-approving; the Pattern Intake is conditional, pinned
   to `82ab235606`, and explicitly lacks a concrete implementation shape.

2. **BLOCKER** — `scheduler.py:3128-3235` has no `ISSUED` return on the
   gate-pass storage path. The wrapper at `3055-3068` keeps claims only for
   `ISSUED`, while the committed gate-pass fixture itself asserts `DECLINED`.
   This breaks the active-claim lifetime and duplicate suppression contract.

3. **BLOCKER** — `_release_prefetch_claim(req)` takes no expected attempt ID,
   and terminal outcomes are keyed only by RID. A stale completion therefore
   has no matching fence against a newer attempt, contrary to the architecture
   contract and RH-G07/RH-G08.

4. **BLOCKER** — The implementation's `PrefetchIssueResult` is a four-member
   enum rather than the required status/result carrying attempt, origin, reason,
   and before/after state. The emitted `rh_preadmission`, `ready_stage.v2`,
   `ready_host`, and `admission.v2` records omit required decision, policy,
   readiness, and join fields, so the specified RH-G09 oracle is unavailable.

## Acceptance matrix

| Requirement | Result |
| --- | --- |
| Prior tester BLOCK explicitly resolved | PASS |
| RH-ON queue-first and RH-OFF eager order | PASS structurally |
| Explicit origin call sites | PASS statically |
| Gate-pass typed `ISSUED` result and claim retention | BLOCK |
| Attempt-correlated cleanup | BLOCK |
| Telemetry non-authority and required joins | BLOCK |
| HOST_ALLOC/Mamba/allocator preservation | PASS by diff scope |
| Dependency-free regression/static checks | PASS |
| Dependency-backed focused tests | Not run; `orjson` unavailable |
| Final gate verdict | BLOCK |

## Followups

- Fresh implementation Task ID: correct successful-issue result/claim lifetime,
  add attempt-matched release/terminal correlation, and align the typed result
  and telemetry contract.
- Fresh gate-owner/orchestrator decision: accept and pin the architecture,
  Pattern Intake, and Novel Mechanism inputs to the implementation revision.
- Fresh tester Task ID after repair: run the complete deterministic ownership,
  cleanup, telemetry, RH-OFF equivalence, and dependency-backed focused suite.

## Open issues

- `orjson`, formatter/typechecker tooling, and live deployment evidence remain
  unavailable; these are non-blocking only after the code and gate blockers are
  resolved.
- No performance acceptance was performed or claimed.

Final verdict: **BLOCK**.
