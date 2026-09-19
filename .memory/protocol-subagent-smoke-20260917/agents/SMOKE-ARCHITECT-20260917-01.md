# SMOKE-ARCHITECT-20260917-01 — Artifact-Lifecycle & Ownership Contract Note

- `task_id:` SMOKE-ARCHITECT-20260917-01
- `role:` architect
- `artifact:` `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-ARCHITECT-20260917-01.md`
- `artifact status:` DONE
- `date:` 2026-09-17

## Task

Produce, for the orchestrator, a compact structural decision note describing the
artifact-lifecycle contract used by the `protocol-subagent-smoke-20260917` run: states,
ownership, invocation binding, ledger ownership, and any point where the contract as
stated is ambiguous or under-specified. This artifact is the sole deliverable.

## Scope

- Analysis and writing only, confined to the task root
  `.memory/protocol-subagent-smoke-20260917/`.
- Only permitted write: this result artifact. No product code, no git, no GPU, no
  services, no network. Nothing outside the task root was modified, created, or deleted.
- This note does not evaluate any repository product, test, config, or service.

## Result

### Contract as stated (commitments)

**C1 — Artifact state machine.** An artifact is created at task acceptance; its first
write sets `WORKING`. `WORKING` is progress state only. The artifact's terminal state is
exactly one of `DONE`, `BLOCKED`, or `FAILED`, written by a terminal update before the
child returns. The permitted transitions are therefore:
`WORKING -> DONE`, `WORKING -> BLOCKED`, `WORKING -> FAILED`. No transition out of a
terminal state.

**C2 — One deliverable, one owner, one invocation.** Each dispatch binds exactly one
`task_id`, one deliverable, and one result-artifact path to exactly one agent invocation.
At most one active writer may exist per artifact path. A new invocation does not inherit,
overwrite, or amend another invocation's artifact; resuming the same `task_id` continues
the same ownership rather than creating a second owner. A child may not spawn agents,
mint task IDs, or accept work outside its invocation.

**C3 — WORKING is never terminal.** A `WORKING` artifact never satisfies a terminal
condition. It is not a result, not completion, and not evidence that any claim is
established. It may not be reconciled, integrated, or reported as a terminal outcome.
Only a terminal update (`DONE` | `BLOCKED` | `FAILED`) satisfies the artifact's
acceptance condition.

**C4 — Ledger ownership.** The run's control ledger
(`.memory/protocol-subagent-smoke-20260917/ledger.md`) has exactly one writer: the
orchestrator. Children never write, repair, or amend the ledger. Children report their
terminal state and artifact path back to the orchestrator; the orchestrator records
dispatch, frontier movement, reconciliation, and integration in the ledger.

### Run-level framing (observed, from the ledger)

- Task root is pre-provisioned runtime data; per-role deliverable path template is
  `agents/SMOKE-<ROLE>-20260917-01.md` for each of 19 role dispatches.
- Run terminal condition: `VERIFIED DONE` when all 19 role dispatches have a reconciled
  terminal artifact; otherwise `EVIDENCED BLOCKED` (named failing role) or
  `MATERIAL USER DECISION` if a role is unavailable / has no installable path.
- Concurrency cap: 3 active children; waves are a resource constraint on the
  orchestrator's dispatch slot, not an independence claim.

### Ambiguities / under-specification in the contract as stated

- **A1 (single-write conflict).** The lifecycle text says the first write sets `WORKING`,
  yet also allows ACCEPTANCE and TERMINAL to be satisfied by a single write for tasks
  with no material transition. One write cannot be both `WORKING` and terminal under C1.
  Resolution applied here: first write `WORKING`, then a terminal update; a "single
  write" is read as a terminal write only. The contract should state this explicitly.
- **A2 (recovery / ownership handoff).** If a child dies leaving a `WORKING` artifact,
  the contract does not say who may complete it, whether the orchestrator may repair it,
  or whether ownership transfers when a `task_id` is resumed. Needs an explicit rule
  (e.g. same-`task_id` resume is the only sanctioned takeover; orchestrator may record
  but not author artifact content).
- **A3 (partial terminal states).** One terminal state is fixed per artifact, but no
  encoding is defined for partial completion (sections individually DONE and BLOCKED).
  Under-specified.
- **A4 (child-terminal-to-run-verdict mapping).** Child vocabulary is
  `DONE | BLOCKED | FAILED`; run vocabulary is
  `VERIFIED DONE | EVIDENCED BLOCKED | MATERIAL USER DECISION`. The mapping (e.g. whether
  any child `BLOCKED` forces the run to `EVIDENCED BLOCKED`) is not stated.
- **A5 (status field syntax).** The contract does not fix whether `status:` is a
  machine-readable field (front matter / exact token) or prose, nor where the terminal
  state must appear. This artifact uses an explicit line field plus a Terminal state
  section.
- **A6 (material recovery point threshold).** "Material recovery point" relies on agent
  judgment ("substantial already-completed work" is unquantified). Low risk for bounded
  tasks, but under-specified.

## Evidence

Observed facts:

- `agents/` existed and was empty immediately before this acceptance write (`ls -la`
  showed only `.` and `..`); no prior writer for this path.
- Read-only inspection of `ledger.md`: line 3 "Sole writer: orchestrator. No other agent
  may write, repair, or amend this file."; line 4 task-root declaration; lines 24-28
  run-level terminal condition; lines 45-47 concurrency cap; line 55 per-role artifact
  path template; lines 52-55 ACTIVE listing includes this `task_id`; children confined to
  the task root and prohibited from git/GPU/services/network.
- Dispatch text for this invocation: task_id, role, goal, scope, four acceptance
  criteria, and the single result-artifact path restated in C1-C4.
- Account-level operating rules §6 (artifact write moments / artifact status) are the
  source of the ACCEPTANCE -> MATERIAL RECOVERY POINT -> TERMINAL and
  `WORKING -> DONE|BLOCKED|FAILED` wording.

Interpretation (not fact): C1-C4 are a faithful restatement of the stated contract;
A1-A6 are analysis, not established defects in execution.

## Defects-blockers

- None blocking this task. The dispatch was valid and in-scope; the note was produced
  with the single permitted write.
- Contract-level open items = A1-A6 (ambiguities, not execution failures) — for the
  orchestrator, as contract owner, to accept, reject, or defer.

## Remaining claims-exclusions

- Does not verify the existence, quality, or terminal state of any other role's
  artifact, nor the ledger's future reconciliation or the run's eventual verdict.
- Does not test or evaluate any code, service, or configuration; no runtime evidence was
  produced or required.
- Claims about the contract rest solely on the dispatch text, account-level rules, and
  the ledger's own declarations; no independent authority was consulted.

## Terminal state

DONE
