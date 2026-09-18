# SMOKE-DOMAIN-ANALYZER-20260917-01 — orchestrator control-plane vocabulary & child-state/Goal-verdict boundary

- task_id: SMOKE-DOMAIN-ANALYZER-20260917-01
- role: domain-analyzer
- artifact: `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DOMAIN-ANALYZER-20260917-01.md`
- artifact status: DONE
- date: 2026-09-17

## Task

- `task_id:` SMOKE-DOMAIN-ANALYZER-20260917-01
- `role:` domain-analyzer
- `goal:` Pin down the vocabulary of the orchestrator control plane precisely enough that
  the terms cannot be conflated, and expose the semantic boundary between child state and
  Goal verdict. Analysis and writing only; no architecture, no implementation.
- Dispatch validation: **VALID.** The smoke ledger's DECISIVE FRONTIER line F3
  (`task-manager | domain-analyzer | doc-writer`) names domain-analyzer as a W2 role, and
  the ledger's READY section puts W2 items at `READY (slot-blocked)`; this dispatch's
  goal, scope, and single result-artifact path match that record, the role is one of the
  19 smoke roles, and the only permitted write is this artifact. No authority boundary
  was exceeded; nothing outside the task root was modified, created, or deleted.
- Inputs: none required. Dependencies: none.
- Deliverable: this artifact. It defines terminology and boundaries; it does **not** amend
  the ledger or the protocol, does not reconcile any other artifact, and does not issue
  the Goal verdict (orchestrator-only acts).

## Scope

- Analysis and writing only, confined to
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`.
- Only write performed: this result artifact (an ACCEPTANCE stub setting `WORKING`, then
  this terminal update). `ledger.md` was read, never written or amended. No git, no GPU,
  no services, no network, no new observation mechanisms.
- Read-only evidence used: account-level operating rules (global `AGENTS.md`), the smoke
  ledger, the three W1 sibling artifacts, and the live `.memory/phase2-hicache-design`
  control records (only for observed control-plane usage of `AUTHORITY_BLOCKED` /
  `DEPENDENCY_BLOCKED` / `VERIFIED DONE`).
- Out of scope: software design, code, product semantics, verification of sibling
  artifacts, and the smoke run's eventual verdict.
- This smoke Goal has no project subject; no repository product, test, config, or service
  was evaluated or touched.

## Result

Definitions below are synthesized from observed usage. Facts are cited in Evidence and
are separated from interpretation (stated explicitly in Evidence, last paragraph). No
official definition document for these tokens was found in the authorized evidence; the
one-line invariants are analysis, offered to the orchestrator as contract owner.

Every term is given a one-line invariant plus one concrete misuse example.

### T1. frontier item

- Invariant (one line): a named, state-tracked unit of Goal work in the DECISIVE FRONTIER
  (here `F1`–`F10`) whose current state token in the ledger is the orchestrator's
  planning-level truth and which is **not** itself a deliverable or an artifact.
- Misuse (concrete): treating `F9 integrate 19 terminal artifacts` as a child task and
  dispatching it to an agent — F9 is an orchestrator-only act; a frontier item is a
  planning record, not a dispatch unless the orchestrator explicitly assigns a packet.
- Grounding: smoke ledger lines 30–43 (F1–F10 with state tokens); phase2 `context.md`
  "Current frontier" lists; architect note ("orchestrator records dispatch, frontier
  movement, reconciliation, and integration").

### T2. READY

- Invariant (one line): all prerequisites for the item are satisfied and no authority
  block exists, but the item has **not** been dispatched; the only residual obstacles are
  resource/scheduling constraints (e.g. the 3-child concurrency cap), so READY asserts
  nothing about work started or output produced.
- Misuse (concrete): reporting the `READY (slot-blocked)` W2–W7 lines as progress on the
  Goal; or moving a `DEPENDENCY_BLOCKED` item to READY because a dispatch slot freed —
  freeing a resource does not satisfy an unmet prerequisite.
- Grounding: smoke ledger lines 35–40 and 57–59 (`READY (slot-blocked)`), lines 45–47
  (cap = 3; waves are a resource constraint, not an independence claim).

### T3. ACTIVE

- Invariant (one line): exactly one running child invocation is bound to the item (one
  `task_id`, one result-artifact path), no terminal artifact has been returned yet, and
  the number of ACTIVE children must not exceed the concurrency cap.
- Misuse (concrete): leaving a task listed ACTIVE after its terminal artifact exists (it
  is then a reconciliation/integration candidate, not active work); or treating ACTIVE as
  evidence that the deliverable is on track or complete.
- Grounding: smoke ledger lines 49–55 (ACTIVE entries + artifact path template), lines
  45–47 (cap = 3).

### T4. DEPENDENCY_BLOCKED

- Invariant (one line): the item cannot start or advance because a **named predecessor
  frontier item** has not reached its required state; the unblock condition is mechanical
  and in-scope (the predecessor completes), requiring no authority decision.
- Misuse (concrete): filing "waiting for the owner to authorize a GPU hand-over window"
  as DEPENDENCY_BLOCKED (that needs authority, hence AUTHORITY_BLOCKED); or blocking F9 on
  F10 — a cycle, since F10 depends on F9.
- Grounding: smoke ledger lines 41–42 (`F9 ... DEPENDENCY_BLOCKED (on F2-F8)`,
  `F10 ... DEPENDENCY_BLOCKED (on F9)`); phase2 ledger lines 7906 and 7995
  (`DEPENDENCY_BLOCKED: C3（依赖 C2）、C4（依赖 C3）`).

### T5. AUTHORITY_BLOCKED

- Invariant (one line): advancing requires a decision or grant that lies outside the
  orchestrator's and children's authority, so no amount of in-scope work clears it and the
  orchestrator must not self-unlock it.
- Misuse (concrete): the orchestrator treating a non-owner pre-authorization note as a
  standing ruling and proceeding — the phase2 record explicitly guards against this
  ("do not treat it as a standing ruling"; "must not be unlocked by the orchestrator
  itself"); equally, labeling something a child can satisfy in-scope as AUTHORITY_BLOCKED.
- Grounding: phase2 ledger line 8073 (heading "已识别的 AUTHORITY_BLOCKED（不得由
  orchestrator 自行解锁）" — identified AUTHORITY_BLOCKED, not to be unlocked by the
  orchestrator itself), line 7838 (`AUTHORITY_BLOCKED` ⇒ requires owner ruling), line
  7854 (owner ruling supersedes); smoke ledger line 28 (`MATERIAL USER DECISION` if a role
  is unavailable/has no installable path).

### T6. DONE

- Invariant (one line): a child's terminal self-report that its **single bounded
  deliverable's** acceptance condition is met, backed by a terminal artifact at the
  assigned path with cited evidence; it certifies only that deliverable and is a claim,
  not independent verification.
- Misuse (concrete): reading a child's `Terminal state: DONE` as satisfying F9, F10, or
  the Goal; or writing DONE while the artifact is still `WORKING` or is missing a required
  section.
- Grounding: account rules §6.6 and §8.1; sibling artifacts' terminal sections;
  architect note C1/C3.

### T7. child state

- Invariant (one line): the state of exactly one dispatch — dispatch phase
  (`READY`/`ACTIVE`/returned) plus artifact status (`WORKING`/`DONE`/`BLOCKED`/`FAILED`) —
  valid only for that `task_id` and artifact path, and it can be true while the Goal is
  entirely unmet.
- Misuse (concrete): summing 19 child states into a Goal verdict ("all children DONE, so
  the run is done"); or letting a child-state token overwrite a frontier item's state in
  the ledger.
- Grounding: smoke ledger lines 49–59 (dispatch listing) with account rules §6.6 (artifact
  status); the category label "child state" is the dispatch's term — the evidence shows
  its components, not a formal definition.

### T8. Goal verdict

- Invariant (one line): the orchestrator's terminal judgment over the whole Goal —
  `VERIFIED DONE` | `EVIDENCED BLOCKED` | `MATERIAL USER DECISION` — issued only after
  every required frontier item is integrated and the run's terminal condition is
  satisfied; it is a conclusion about the whole, never a roll-up of child statuses.
- Misuse (concrete): declaring `VERIFIED DONE` because 19 files merely exist (existence is
  not terminal state, and neither is reconciled content); or issuing `EVIDENCED BLOCKED`
  when the sole obstacle is a pending owner decision (that is `MATERIAL USER DECISION`).
- Grounding: smoke ledger lines 24–28 (terminal condition and its three tokens), line 42
  (F10 "terminal verdict"), lines 65–67 (INTEGRATED).

### T9. WORKING artifact

- Invariant (one line): an artifact whose first write set `status: WORKING`; it satisfies
  ACCEPTANCE only, and is progress state — never a result, never completion, never
  evidence that a claim is established, and it must not be reported as a terminal result.
- Misuse (concrete): counting a `WORKING` artifact toward the "19 reconciled terminal
  artifacts" condition; or citing it during integration as if the child had returned.
- Grounding: account rules §6.6 (artifact write moments / artifact status; explicit
  prohibition on reporting WORKING as a terminal result); architect note C3.

### T10. terminal artifact

- Invariant (one line): an artifact whose final write before the child returns sets exactly
  one terminal state — `DONE` | `BLOCKED` | `FAILED` — and contains the required sections;
  only terminal artifacts are eligible for reconciliation/integration, and terminality is
  read from the artifact, not from the child's chat/task-status message.
- Misuse (concrete): treating the task tool's result message as the terminal artifact
  (the orchestrator must reconcile against the recorded artifact path); or a later agent
  overwriting/amending a terminal artifact it does not own.
- Grounding: account rules §6.6; smoke ledger line 55 (path template) and lines 69–72
  ("reconcile each against its recorded artifact path and integrate"); architect note C2
  (one deliverable / one owner / one invocation).

### T11. integration

- Invariant (one line): the orchestrator-only act of reconciling each dispatch against its
  recorded artifact path, confirming terminal state and required content, and recording
  the item in the ledger (`INTEGRATED`), which gates the Goal verdict; it is not a child
  deliverable and cannot be self-certified by the producing child.
- Misuse (concrete): a child "integrating" its own artifact or reporting the run done; or
  integrating by file existence alone (existence ≠ terminal state ≠ validated content).
- Grounding: smoke ledger line 26 ("reconciled terminal artifact"), line 41 (F9
  "integrate 19 terminal artifacts"), lines 65–72; architect note C4 (orchestrator records
  dispatch, frontier movement, reconciliation, integration).

### Boundary rule: child DONE vs Goal VERIFIED DONE

- Rule (one line): **child DONE is a per-deliverable claim by the child; Goal VERIFIED
  DONE is a whole-Goal verdict by the orchestrator that requires integration of every
  required terminal artifact plus satisfaction of the run's terminal condition — so child
  DONE is necessary but never sufficient, and no child state (including DONE) can award or
  imply the Goal verdict.**
- Case where they differ (timing): at some instant all 19 children may have returned
  `Terminal state: DONE` with artifacts at their recorded paths, while F9 ("integrate 19
  terminal artifacts") and F10 ("terminal verdict") are still `DEPENDENCY_BLOCKED` — 19×
  child DONE is true and the Goal verdict has not been issued (and cannot be, until F9/F10
  run). Summing child states would produce a false goal claim.
- Case where they differ (quality): a child reports DONE but its artifact is at the wrong
  path or lacks a required section (the context-manager index already flags that predicted
  tokens for multi-word roles may be wrong). The child's DONE claim exists, yet the
  dispatch mechanism's acceptance is not demonstrated, so `VERIFIED DONE` is not
  warranted; only orchestrator reconciliation can decide this.
- Reverse direction: a child's terminal `BLOCKED`/`FAILED` still yields a *terminal*
  artifact; whether that satisfies "all 19 ... reconciled terminal artifact" or forces
  `EVIDENCED BLOCKED` is unresolved in the contract — see D1 below. This artifact takes no
  position; it is a contract-owner decision.

### Commonly conflated pairs and discriminators

| # | Pair | Discriminator (question that separates them) |
|---|------|----------------------------------------------|
| 1 | child DONE vs Goal VERIFIED DONE | Who signed, and over what scope? Child (one deliverable, self-report) vs orchestrator (whole Goal, post-integration verdict). |
| 2 | READY vs ACTIVE | Has a child been dispatched? READY = eligible, no owner yet; ACTIVE = bound invocation in flight, no terminal artifact yet. |
| 3 | DEPENDENCY_BLOCKED vs AUTHORITY_BLOCKED | Can in-scope work clear it? Named predecessor state (mechanical) vs authority grant (owner decision). |
| 4 | child state vs Goal verdict | What is the subject? One dispatch/artifact (part) vs all required frontier items integrated (whole). |
| 5 | WORKING artifact vs terminal artifact | Is exactly one terminal state token present? WORKING = progress; terminal = outcome; only the latter is reconcilable. |
| 6 | integration vs verification | What kind of act? Orchestrator reconciliation/recording across all recorded paths vs independent evidence check of a claim (reviewer/tester). File existence is neither terminality nor verification. |
| 7 | READY (slot-blocked) vs DEPENDENCY_BLOCKED | What is the obstacle? Resource/scheduling (wave slot cap; waves are "a RESOURCE constraint ... not an independence claim") vs unmet prerequisite. |
| 8 | product READY vs control-plane READY | Which system? Live product telemetry (`restore_state_after=READY` in phase2 cache logs) vs orchestrator scheduling state. Same token, unrelated semantics — never carry one across the boundary. |

### Contradictions and under-specification (contract-level; not execution failures)

- **D1 — terminal artifact vs failing role.** The run's terminal condition says
  `VERIFIED DONE` when all 19 dispatches have "a reconciled terminal artifact"
  (`DONE | BLOCKED | FAILED` are all terminal), yet "otherwise `EVIDENCED BLOCKED` with the
  named failing role". Whether a child terminal `BLOCKED`/`FAILED` still counts as a
  reconciled terminal artifact (→ possibly VERIFIED DONE) or forces EVIDENCED BLOCKED is
  not stated. This changes the verdict for any non-DONE child. (Same gap as architect A4.)
- **D2 — `DONE` is overloaded across three scopes.** Observed uses: frontier item state
  (`F1 ... DONE`), child artifact status (`artifact status: DONE`), child terminal state
  (`Terminal state: DONE`). The ledger does not require a scope qualifier, so "DONE" in a
  status message is ambiguous unless qualified. Recommended discriminator: always qualify
  as frontier state / artifact status / child terminal state.
- **D3 — reconciliation vs integration.** The terminal condition says "reconciled terminal
  artifact", F9 says "integrate", and the architect note lists "reconciliation, and
  integration" as separate recorded acts. One stage or two is unspecified; this affects
  what `INTEGRATED: (none)` will mean once F9 runs.
- **D4 — single-write conflict (inherited, architect A1).** Account rules §6.6 says the
  first write sets `WORKING`, yet acceptance and terminal MAY be satisfied by a single
  write for tasks with no material transition; one write cannot be both. Resolution
  applied in this artifact: first write `WORKING`, then a terminal update. The contract
  should state this explicitly.
- **D5 — frontier-item identity is only a formatting convention.** The `F#` lines have no
  stated definition, ID-ownership rule, or relation to any other ID space; if another
  agent (e.g. task-manager) mints dependency-DAG IDs, the two ID spaces could diverge.
- **D6 — wave order vs dependency.** The ledger says waves are a resource constraint, not
  an independence claim, and W2–W7 are "slot-blocked only"; whether a READY item may be
  dispatched out of wave order when a slot frees is not stated.

### Questions that would change downstream decisions

- Q1: Does any child terminal `BLOCKED`/`FAILED` make the run `EVIDENCED BLOCKED` even if
  its artifact is reconciled? (D1)
- Q2: What is the minimum integration check — path match + terminal token only, or also
  required-section and evidence presence? (The "quality" differ-case depends on this.)
- Q3: Are reconciliation and integration one stage or two? (D3)
- Q4: Who may complete a dead child's `WORKING` artifact, and does same-`task_id` resume
  transfer ownership? (Architect A2; not answered here.)
- Q5: Is the `F#` frontier ID space the single canonical work-ID space for this run, or
  does a separate task-ID space coexist? (D5)

## Evidence

Facts (read-only; the only write was this artifact at its assigned path):

- E1 — Account-level operating rules, global `AGENTS.md`: §6.6 defines the artifact write
  moments `ACCEPTANCE → MATERIAL RECOVERY POINT → TERMINAL`; artifact status
  `WORKING → DONE | BLOCKED | FAILED`; `WORKING` is progress state, MUST NOT be reported as
  a terminal result, MUST NOT be treated as completion, and MUST NOT be cited as evidence
  that the task's claims are established. §8.1: a task is complete only when its assigned
  acceptance condition is established by appropriate evidence or a concrete blocker is
  established.
- E2 — Smoke ledger `.memory/protocol-subagent-smoke-20260917/ledger.md` (read-only):
  lines 1–4 header and sole-writer rule; lines 24–28 terminal condition and the three Goal
  tokens (`VERIFIED DONE`, `EVIDENCED BLOCKED`, `MATERIAL USER DECISION`); lines 30–43
  DECISIVE FRONTIER F1–F10 (F3 names this dispatch; F9/F10 are `DEPENDENCY_BLOCKED`);
  lines 45–47 cap of 3 active children and "Waves are a RESOURCE constraint ... not an
  independence claim"; lines 49–55 ACTIVE listing and artifact path template
  `agents/SMOKE-<ROLE>-20260917-01.md`; lines 57–59 READY (W2–W7, slot-blocked); lines
  61–63 BLOCKED (none); lines 65–67 INTEGRATED (none); lines 69–72 NEXT ("reconcile each
  against its recorded artifact path and integrate").
- E3 — Sibling W1 artifacts, used as observed usage evidence only: `SMOKE-ARCHITECT-
  20260917-01.md` C1–C4 (lifecycle, one-owner rule, WORKING-never-terminal, ledger
  ownership) and A1–A6 (ambiguities, especially A1 single-write and A4 mapping);
  `SMOKE-CONTEXT-20260917-01.md` snapshot at `2026-09-17T20:46:34Z` (scout EXISTS, 18
  ABSENT; prediction caveat on artifact tokens); `SMOKE-SCOUT-20260917-01.md` ground-truth
  inventory and terminal section.
- E4 — Live `.memory/phase2-hicache-design` control records (read-only, usage of the same
  control vocabulary): `ledger.md` line 7906 and line 7995
  (`DEPENDENCY_BLOCKED: C3（依赖 C2）、C4（依赖 C3）` — dependency-blocked items name their
  upstream dependencies); line 7838 (`AUTHORITY_BLOCKED` ⇒ requires owner ruling); line
  7854 (owner ruling supersedes a prior AUTHORITY_BLOCKED); line 8073 heading
  `已识别的 AUTHORITY_BLOCKED（不得由 orchestrator 自行解锁）` (identified
  AUTHORITY_BLOCKED, not to be unlocked by the orchestrator itself); `context.md` lines
  42–48 (`Current frontier` with `VERIFIED DONE` / `PASS` states).
- E5 — This invocation's dispatch text: task_id, role, goal, scope, acceptance criteria,
  single result-artifact path; requires terminal state one of DONE/BLOCKED/FAILED.
- E6 — This artifact's own post-write self-check (read-only, run after the terminal write
  and before returning): all seven required section headings present (`Task`, `Scope`,
  `Result`, `Evidence`, `Defects-blockers`, `Remaining claims-exclusions`,
  `Terminal state`); every one of the 11 required terms (T1–T11) carries an invariant line
  and a misuse line; the boundary rule and a difference case are present; a conflated-pair
  table with discriminators is present; terminal token is a single value.

Interpretation (not fact): the one-line invariants (T1–T11), the boundary rule, the
discriminator framings, and the D1–D6 / Q1–Q5 findings are analysis, not statements
recorded in the ledger or in any authoritative protocol document. No authoritative
definition document for these terms was found in the authorized evidence; the smoke
ledger uses the tokens operationally without defining them, and the account rules define
only the artifact lifecycle vocabulary (`WORKING`/terminal states).

## Defects-blockers

- None blocking this task. The dispatch was valid and in-scope; the single permitted write
  was honored; `ledger.md` and all sibling artifacts were not modified.
- Contract-level findings for the orchestrator, as contract owner, to accept, reject, or
  defer: ambiguities D1–D6 and the decisions they gate, Q1–Q5. These are analysis, not
  execution failures of this smoke run.
- Observation, not a defect: `DONE` (D2) and `READY` (conflated-pair 8) are homonyms
  across scopes/systems; unqualified use anywhere in the control plane is a conflation
  risk.

## Remaining claims-exclusions

- This artifact does not issue, predict, or preempt the Goal verdict, does not reconcile
  or integrate any child artifact, does not verify any sibling artifact's content or
  terminal state, and does not amend the ledger or the protocol.
- The D1–D6 findings are not verified defects of the protocol; they are ambiguities in the
  text as stated, identified from the authorized evidence only.
- Product-level usages (e.g. phase2 `restore_state_after=READY`) are cited only as
  cross-domain homonyms; no product semantics are asserted or relied on.
- Definitions rest solely on the evidence listed under E1–E5; no external, official, or
  project-authority definition of the control-plane tokens was consulted.
- No project code, tests, configuration, services, GPU, or network were touched; the smoke
  Goal has no project subject.

## Terminal state

DONE
