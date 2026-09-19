# SMOKE-TASK-MGR-20260917-01 — task-manager result artifact

- task_id: SMOKE-TASK-MGR-20260917-01
- role: task-manager
- artifact status: DONE
- date: 2026-09-17

## Task
- task_id: SMOKE-TASK-MGR-20260917-01
- role: task-manager
- goal: Produce, inside this single result artifact, an executable dependency DAG for the
  19-role orchestrator smoke run: waves, per-role deliverable, owner, acceptance criteria,
  and dependency edges.
- Dispatch validation: VALID. The dispatch matches ledger.md line 53's sibling frontier
  entries and the run's declared design (ledger lines 15-22, 30-47). Goal is analysis and
  writing only; confined to the task root; the only permitted write is this result
  artifact; the ledger is not written or edited. No authority boundary was exceeded.
- Inputs: the 19 roles and their authoritative canonical artifact paths (dispatch text);
  observed run state (task root listing, ledger.md, and the W1 artifacts).
- Dependencies: none.
- This artifact is a PLAN. Its deliverable/acceptance text is my design for executable
  sequencing; it is not a claim about how the orchestrator has already behaved.

## Scope
- Analysis and writing only, confined to
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`.
- No reads/writes/creates/deletes outside that directory. `ledger.md` was read, never
  written. No git, no GPU, no services, no network, no new observation mechanisms.
- Only write performed: this result artifact. No other specialist report was modified.
- This artifact does not evaluate any repository product, test, configuration, service, or
  infrastructure; the smoke goal has no project subject.
- It does not discharge the orchestrator's reconciliation, integration, or terminal
  verdict (ledger F9/F10), and it does not amend the orchestrator ledger.

## Result

### Definitions used below
- `TASK_ROOT` = `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917`
- Every role's canonical result artifact is `<TASK_ROOT>/agents/<FILE>`. Column
  "Canonical result-artifact path" spells out `<TASK_ROOT>/agents/SMOKE-<TOKEN>-20260917-01.md`.
- Ownership (C2): one role = one task_id = one invocation = one deliverable = one result
  artifact path = one active writer. The "owner" for every row is the named role's single
  dispatch invocation; no row shares a writer with another row.
- Write sets: each role's write set is exactly its own canonical result-artifact path.
  The 19 write sets are pairwise disjoint (19 distinct paths). The orchestrator ledger is
  present in the same directory but is EXCLUDED from every child write set (sole writer:
  orchestrator, ledger.md line 3).
- Wave grouping is the orchestrator's dispatch-slot schedule observed in ledger.md lines
  30-47. It is a RESOURCE constraint (concurrency cap 3, ledger line 45), not a data
  dependency; see "DAG edges".

### Acceptance criteria (general, referenced by ID in the table)
- **G1** Artifact exists at the exact canonical path and contains sections: Task / Scope /
  Result / Evidence / Defects-blockers / Remaining claims-exclusions / Terminal state.
- **G2** Exactly one terminal state from {DONE, BLOCKED, FAILED}; no WORKING left.
- **G3** Evidence cites what the role actually did (commands/observations); no unobserved
  orchestrator behavior asserted.
- **G4** Only write is the role's own artifact; ledger untouched; no repo/test/config/git/
  GPU/service/network (external roles: sanitized public data only).
- **G5** Deliverable is self-contained and appropriate to the assigned role.
Role-specific acceptance additions are named in the "Acceptance criteria" column.

### Wave / role / deliverable table (19 roles)
| Wave | Role (owner = single invocation) | Deliverable (proposed plan) | Canonical result-artifact path | Acceptance criteria | Dependencies |
|------|----------------------------------|-----------------------------|--------------------------------|---------------------|--------------|
| W1 | scout | read-only ground-truth inventory of the task root (observed ledger line 51) | `<TASK_ROOT>/agents/SMOKE-SCOUT-20260917-01.md` | G1-G5; inventory matches a live listing | none (independent) |
| W1 | architect | artifact-lifecycle + ownership-boundary note (observed ledger line 52) | `<TASK_ROOT>/agents/SMOKE-ARCHITECT-20260917-01.md` | G1-G5; contract states C1-C4 | none (independent) |
| W1 | context-manager | expected-artifact index for the 19 dispatches (observed ledger line 53) | `<TASK_ROOT>/agents/SMOKE-CONTEXT-20260917-01.md` | G1-G5; all 19 paths indexed | none (independent) |
| W2 | task-manager | this executable 19-role DAG (waves, owners, paths, edges, concurrency) | `<TASK_ROOT>/agents/SMOKE-TASK-MGR-20260917-01.md` | G1-G5; table + explicit edges present | none (independent) |
| W2 | domain-analyzer | terminology/invariant note for the run's control vocabulary (WORKING/DONE/BLOCKED/FAILED, wave, frontier, ownership) | `<TASK_ROOT>/agents/SMOKE-DOMAIN-ANALYZER-20260917-01.md` | G1-G5; each term defined with invariant | none (independent) |
| W2 | doc-writer | run-protocol conventions note (artifact section set, path template); in-artifact only, no product docs | `<TASK_ROOT>/agents/SMOKE-DOC-WRITER-20260917-01.md` | G1-G5; documents stated conventions only | none (independent) |
| W3 | coder | minimal, self-contained, deterministic code example embedded in the artifact with a verification transcript; no repository file writes | `<TASK_ROOT>/agents/SMOKE-CODER-20260917-01.md` | G1-G5; example runs/reproduces inside artifact | none (independent) |
| W3 | executor | explicitly-specified mechanical transformation over data embedded in the artifact, with before/after record; no external file writes | `<TASK_ROOT>/agents/SMOKE-EXECUTOR-20260917-01.md` | G1-G5; deterministic, reversible, in-artifact | none (independent) |
| W3 | debugger-deep | causal reconstruction of a described trivial failure with root cause + counterfactual check; in-artifact | `<TASK_ROOT>/agents/SMOKE-DEBUGGER-DEEP-20260917-01.md` | G1-G5; competing hypotheses addressed | none (independent) |
| W4 | reviewer | independent review of one prior run artifact against its stated acceptance criteria; findings only | `<TASK_ROOT>/agents/SMOKE-REVIEWER-20260917-01.md` | G1-G5; review target named by path | none (independent) — see O1 |
| W4 | reviewer-deep | adversarial review of this DAG/contract edges and the architect ambiguities; risk-focused | `<TASK_ROOT>/agents/SMOKE-REVIEWER-DEEP-20260917-01.md` | G1-G5; at least one counterexample attempt | none (independent) — see O1 |
| W4 | tester | independent reproduction of one falsifiable claim from a prior artifact using observable state; pass/fail | `<TASK_ROOT>/agents/SMOKE-TESTER-20260917-01.md` | G1-G5; claim + reproduction recorded | none (independent) — see O1 |
| W5 | test-runner | run a defined read-only verification command (ls/find/wc/stat) and return exit status + raw output | `<TASK_ROOT>/agents/SMOKE-TEST-RUNNER-20260917-01.md` | G1-G5; command reproducible verbatim | none (independent) |
| W5 | devops | design/describe a safe, reversible release procedure abstractly; no infra/service action; explicit rollback | `<TASK_ROOT>/agents/SMOKE-DEVOPS-20260917-01.md` | G1-G5; no side effects; rollback stated | none (independent) |
| W5 | devops-executor | execute a defined no-op/dry-run procedure and record evidence of zero external side effects | `<TASK_ROOT>/agents/SMOKE-DEVOPS-EXEC-20260917-01.md` | G1-G5; no service/infra change | none (independent) |
| W6 | frontend | in-artifact rendering/accessibility sanity check of a markdown table/component; no product UI edits | `<TASK_ROOT>/agents/SMOKE-FRONTEND-20260917-01.md` | G1-G5; checks are observable/in-artifact | none (independent) |
| W6 | external-investigator | retrieve one precise public fact with source citation (sanitized packet only) | `<TASK_ROOT>/agents/SMOKE-EXT-INVESTIGATOR-20260917-01.md` | G1-G5 + source cited, no private data | none (independent) |
| W6 | external-researcher | bounded public research synthesis comparing >=2 sources with conflict notes (sanitized) | `<TASK_ROOT>/agents/SMOKE-EXT-RESEARCHER-20260917-01.md` | G1-G5 + >=2 sources, conflicts stated | none (independent) |
| W7 | external-analyst | synthesize the external evidence into one calibrated judgment with confidence + counterevidence (sanitized) | `<TASK_ROOT>/agents/SMOKE-EXT-ANALYST-20260917-01.md` | G1-G5 + judgment, confidence, counterevidence | none (independent) |

Canonical-path note: the dispatch's authoritative tokens for multi-word roles are the
short forms `TASK-MGR`, `DEVOPS-EXEC`, `EXT-INVESTIGATOR`, `EXT-RESEARCHER`, `EXT-ANALYST`
(and `CONTEXT`), which supersede the uppercase-role-name PREDICTIONS in
`SMOKE-CONTEXT-20260917-01.md` rows 4-19. See O3.

### Control nodes (not role dispatches; not task IDs)
| Node | Owner | Deliverable | Dependencies |
|------|-------|-------------|--------------|
| I1 integrate-19 | orchestrator (ledger writer) | reconcile all 19 terminal artifacts + ledger INTEGRATED record | all of R01-R19 terminal |
| V1 terminal-verdict | orchestrator | run verdict: VERIFIED DONE / EVIDENCED BLOCKED / MATERIAL USER DECISION | I1 |

I1 and V1 are plan labels, not dispatches. They introduce no new artifact path and no new
writer; the orchestrator remains sole writer of `ledger.md`.

### DAG edges (explicit: what blocks what)
Node IDs: R01=scout, R02=architect, R03=context-manager, R04=task-manager,
R05=domain-analyzer, R06=doc-writer, R07=coder, R08=executor, R09=debugger-deep,
R10=reviewer, R11=reviewer-deep, R12=tester, R13=test-runner, R14=devops,
R15=devops-executor, R16=frontend, R17=external-investigator, R18=external-researcher,
R19=external-analyst.

Blocking edges (adjacency list):
```
R01 -> I1
R02 -> I1
R03 -> I1
R04 -> I1
R05 -> I1
R06 -> I1
R07 -> I1
R08 -> I1
R09 -> I1
R10 -> I1
R11 -> I1
R12 -> I1
R13 -> I1
R14 -> I1
R15 -> I1
R16 -> I1
R17 -> I1
R18 -> I1
R19 -> I1
I1  -> V1
```
That is the complete edge set: 19 producer->integration edges + 1 integration->verdict
edge. There are NO edges R_i -> R_j for any i != j.

Non-edges (independence): for all i != j in 1..19 there is no blocking edge between R_i
and R_j. The 19 role deliverables are pairwise independent because each is self-contained
and consumes no sibling artifact as a required input (ledger lines 17-18, 45-47).

Wave schedule vs dependency DAG: W1<W2<...<W7 is a dispatch-slot ordering (cap 3 active
children), not a dependency chain. Concretely, R07 (W3) does not depend on R01 (W1); it
merely cannot be dispatched until a slot frees. Treating waves as edges would be a false
serialization. If the cap were unbounded, all 19 could dispatch concurrently.

### Independence / concurrency
- All 19 items are mutually independent and could run concurrently in the absence of the
  cap. Under the cap of 3, maximum safe concurrency is 3.
- Executable concurrent groups (the observed frontier):
  - `{R01,R02,R03}` W1, `{R04,R05,R06}` W2, `{R07,R08,R09}` W3, `{R10,R11,R12}` W4,
    `{R13,R14,R15}` W5, `{R16,R17,R18}` W6, `{R19}` W7.
- Any size-3 subset across these groups is equally safe; the grouping above is the
  lowest-coordination packing (6x3 + 1x1 = 19).
- I1 must wait for all 19 terminal artifacts; V1 must wait for I1.

### Intrinsically atomic items (why they are not further decomposed)
Every role deliverable is atomic by contract C2: one task_id, one deliverable, one
invocation, one result-artifact path, one writer (SMOKE-ARCHITECT-20260917-01.md, C2).
Splitting any row would create two writers for one acceptance unit or a second artifact
path, violating the one-writer rule and the run's single permitted write per child
(ledger lines 16-18). No decomposition is available within the authorized scope.

### Serialization reasons (recorded)
- The only reason to serialize role dispatches is the orchestrator's concurrency cap of 3
  slots (ledger line 45), plus the single-writer/one-artifact rule. There is no correctness
  dependency between role deliverables in this smoke design.
- I1->V1 is a genuine logical dependency: reconciliation precedes the run verdict.

### Inputs per role
- Own dispatch packet (task_id, role, goal, scope, acceptance criteria, canonical path).
- Read-only references available in-scope: `ledger.md`, `TASK_ROOT/agents/` listing, and
  any already-materialized sibling artifacts. `ledger.md` is read-only for all children.

### Evidence requirements per role
- G3: cite the concrete command(s)/observation(s) actually performed (mandated by the
  dispatch and by account rules §3/§6). Minimum for read-only roles: one reproducible
  listing or stat. Minimum for external roles: a cited public source, sanitized.

### Report paths
- Report path == canonical result-artifact path in the table above; each role reports its
  terminal state + artifact path back to the orchestrator, which owns the ledger.

### Explicit open decisions (for the orchestrator)
- **O1 (reviewer/reviewer-deep/tester target).** Should W4 roles review concrete named
  upstream artifacts (which would ADD edges R10->R07 etc.) or perform self-contained
  exercises? I did not assert such edges because the smoke design makes each deliverable
  self-contained. Orchestrator decision required before W4 dispatch.
- **O2 (wave binding).** Are W1-W7 binding, or collapsible given full role independence?
  I present them as the observed resource schedule; changing them changes no dependency.
- **O3 (path tokens).** Confirm the dispatch's authoritative short tokens
  (`TASK-MGR`, `DEVOPS-EXEC`, `EXT-INVESTIGATOR`, `EXT-RESEARCHER`, `EXT-ANALYST`,
  `CONTEXT`) are the real artifact names for R04, R15, R17, R18, R19, R03.
- **O4 (child->run verdict mapping).** Does any child BLOCKED force EVIDENCED BLOCKED, or
  can I1 complete with a named blocked role? (architect A4).
- **O5 (partial terminal encoding).** No encoding exists for per-section DONE/BLOCKED
  (architect A3); affects how I1 reconciles.
- **O6 (in-artifact-only deliverables).** Confirm coder/executor/frontend should exercise
  their work inside the artifact only (no repo/product writes), which I assumed.

## Evidence
Observed facts (what I actually did):

1. Dispatch validation against live state. Read `/home/ubuntu/.../ledger.md` (72 lines):
   line 3 "Sole writer: orchestrator"; lines 30-43 DECISIVE FRONTIER listing
   F1 control-state DONE and W1-W7 role groupings with F9 integrate / F10 verdict; line 45
   concurrency cap 3; line 55 path template. This is the source of my wave assignment.
2. Read three materialized W1 artifacts in full:
   `SMOKE-SCOUT-20260917-01.md` (124 lines, terminal DONE),
   `SMOKE-ARCHITECT-20260917-01.md` (129 lines, terminal DONE),
   `SMOKE-CONTEXT-20260917-01.md` (175 lines, terminal DONE). These supplied the
   artifact-contract facts (C1-C4), the observed W1 deliverables, and the predicted-path
   caveat used in O3.
3. Timestamped listing at `2026-09-17T20:47:40Z`:
   ```
   $ date -u '+%Y-%m-%dT%H:%M:%SZ'   -> 2026-09-17T20:47:40Z
   $ ls -1 <TASK_ROOT>/agents/
   SMOKE-ARCHITECT-20260917-01.md
   SMOKE-CONTEXT-20260917-01.md
   SMOKE-DOC-WRITER-20260917-01.md
   SMOKE-SCOUT-20260917-01.md
   ```
   Confirms live sibling dispatch: the W2 doc-writer artifact appeared between my first
   listing and this one. It also confirms the dispatch's canonical filename for doc-writer.
4. `find <TASK_ROOT> -mindepth 1 -printf '%y %s %p\n'` showed `agents/` + `ledger.md`
   (3038 bytes) + the four artifacts above. `ledger.md` present and unmodified by me.
5. Post-write self-check of this artifact (performed after the terminal write; recorded in
   the terminal update, not the stub): exact path exists with all required sections.

Derivation (not observation): the logical dependency edges (19 producers -> I1 -> V1) and
the "all 19 independent" claim are derived by me from the run's stated self-contained
design (ledger lines 16-22, 45-47) and from contract C2; they are NOT a report of observed
orchestrator execution of W2-W7. The wave groupings are observed from ledger.md.

## Defects-blockers
- None blocking this task. Dispatch was valid and in-scope; produced with the single
  permitted write after the required ACCEPTANCE stub.
- Observed (not a defect of this task): `SMOKE-CONTEXT-20260917-01.md` states its rows 4-19
  paths are predictions and may be wrong for multi-word roles. My dispatch supplies the
  authoritative short tokens, resolving the prediction to a fact — tracked as decision O3.
- Contract ambiguities A1-A6 (architect) remain the orchestrator's to resolve; O1-O6 above
  are the ones that affect this DAG's executability.

## Remaining claims-exclusions
- I did not observe orchestrator dispatch of W2-W7, nor any execution beyond the four
  materialized artifacts and the ledger snapshot. All wave text is quoted from ledger.md;
  all edge/independence claims are derivation from the stated design.
- Proposed deliverables and role-specific acceptance additions are my planning design, not
  orchestrator-assigned content. The orchestrator's dispatch packet per role is
  authoritative and may differ.
- I read three sibling artifacts and observed one more by filename only; I did not verify
  the content, terminal state, or correctness of any artifact beyond those three reads, and
  computed no checksums.
- The canonical-path column reproduces the dispatch's authoritative list; I did not verify
  those files exist for the 15 not-yet-materialized roles.
- No product, test, config, service, GPU, or network surface was touched; the smoke goal
  has no project subject. I did not write, repair, or amend `ledger.md`.
- This artifact does not reconcile or supersede any other artifact and does not deliver the
  run's terminal verdict.

## Terminal state
DONE
