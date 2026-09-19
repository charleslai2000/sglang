# protocol-subagent-smoke-20260917 — orchestrator control ledger (FINAL)

Sole writer: orchestrator. Cites by section name (corrects I12).
Task root: `.memory/protocol-subagent-smoke-20260917/`

## Goal

Smoke-test the orchestrator dispatch protocol: dispatch each of the 19 installed specialist roles
exactly once with a bounded, self-contained deliverable, each returning a TERMINAL artifact at its
assigned path. PLUS (user directive): a dedicated special audit of the dispatches — model & variant
accuracy, communication integrity, `.memory` artifact-protocol compliance — with a reported result.

No project subject.

## Terminal condition

`VERIFIED DONE` when all 19 roles have a reconciled terminal artifact AND the audit is reported.
Otherwise `EVIDENCED BLOCKED` naming the failing role, or `MATERIAL USER DECISION`.

## EVIDENCE BOUNDARY — runtime variant verification (binding)

- **B1** This build's CLIENT log does NOT record subagent variant. Runtime-effort attribution from it
  is a timestamp-join INFERENCE, not a direct read. (Confirmed first-hand by the extension audit.)
- **B2** The `public` tier's client-log records were asserted to be "2 records under a different key
  (`dev-codex-…`), corroborating only". **The extension audit could NOT reproduce that basis**: it
  counted 38 public `stream` records + 1 public `stream error`, and no `dev-codex` model key.
  The DISPOSITION (client log cannot verify variant) stands; the stated BASIS is unreproduced. See D1.
  This is a conflict between user-supplied evidence and a first-hand audit read, reported unresolved.
- **B3** Verification CEILING: local records show only what the runtime RECORDED and what the
  configured agent SELECTED. Provider-side router target identity and wire-level `reasoning_effort`
  are NOT ESTABLISHED. A silent upstream substitution must NOT be claimed as excluded.
- **R-VARIANT-3 (CLOSED)** The 5 roles not run when the user audited have all since been dispatched,
  and their runtime variant is now covered (see EXTENDED AUDIT). Coverage of the 5 gap roles: closed.

## ORCHESTRATOR CONTRACT RULINGS (binding)

- R-A1/D4 first write `WORKING`; terminal update before return; a no-material-transition task MAY
  write terminal directly.
- R-A3/O5 one terminal value per artifact; partial results in prose.
- R-A4/D1/O4 (AMENDED) non-DONE terminal closes the artifact permanently; retry uses a NEW `task_id`
  and NEW path (`...-R2.md`); superseded artifacts are recorded, never rewritten.
- R-A2/Q4 dead invocation recovered only by resuming the SAME `task_id`; orchestrator never authors
  artifact content. Trigger remains under-defined — recorded, not exercised.
- R-D2 `DONE` must be scope-qualified (frontier state / artifact status / child terminal).
- R-O1 (AMENDED) W4 targets bound; "independent method" = different parser AND different author.
- R-D3 integration check = path + terminal token + required sections + evidence presence.
- R-PACKET (from audit O1) the packet `Return only:` clause must match or explicitly override the
  installed per-role return contract. Prose clause included below.

## FINAL DECISIVE FRONTIER

```
F1  control state established ................................ DONE (frontier state)
F2  W1 scout | architect | context-manager ................... DONE (3/3, child terminal DONE)
F3  W2 task-manager | domain-analyzer | doc-writer ........... DONE (3/3 child terminal DONE)
F4  W3 coder | executor | debugger-deep ...................... DONE (3/3 child terminal DONE)
F5  W4 reviewer | reviewer-deep | tester ..................... DONE (3/3 child terminal DONE)
F6  W5 test-runner | devops .................................. DONE (2/2 child terminal DONE)
F7  W6 devops-executor | frontend | external-investigator .... DONE (3/3 child terminal DONE)
F8  W7 external-researcher | external-analyst ................ DONE (2/2 child terminal DONE)
F11 SPECIAL AUDIT (user directive) ........................... DONE (terminal; Q1/Q2/Q3 + O1-O6, C1-C3)
F12 AUDIT EXTENSION (5 gap roles, R-VARIANT-3) ............... DONE (terminal; 5/5 MATCH + D1)
F9  integrate all 19 role artifacts + 2 audit deliverables ... DONE (21/21 reconciled)
F10 terminal verdict ......................................... DONE -> VERIFIED DONE
```

## ACTIVE

- (none)

## BLOCKED

- (none)

## INTEGRATED — 21/21 reconciled dispatches; every child terminal DONE

19 role artifacts (all at their canonical assigned paths, verified terminal DONE):
scout, architect, context-manager, task-manager, domain-analyzer, doc-writer, coder, executor,
debugger-deep, reviewer, reviewer-deep, tester, test-runner, devops, devops-executor, frontend,
external-investigator, external-researcher, external-analyst.

2 audit deliverables:
- `SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01` | Q1 MATCH 12/12 + 3 supplementary, no
  fallback/substitution; Q2 PARTIALLY DEFECTIVE (O1-O6, all orchestrator packet wording);
  Q3 COMPLIANT (byte-replay single-writer, ledger sole-writer verified)
- `SMOKE-AUDIT-VARIANT-EXT-20260917-01` | 5/5 MATCH; parameter exposure independently re-confirmed;
  D1 basis unreproduced; D2 adjacent unrelated errors; D3 retry-not-substitution recorded

## AUDIT RESULT — model/variant coverage (final)

- **19/19 role dispatches have runtime variant coverage; all MATCH configured.**
  Audit 1: scout, architect, context-manager, task-manager, domain-analyzer, doc-writer, coder,
  executor, debugger-deep, reviewer, reviewer-deep, tester, test-runner, devops (14 roles).
  Audit extension: devops-executor (worker/low), frontend (worker/high),
  external-investigator (public/high), external-researcher (public/high), external-analyst
  (public/high) (5 roles).
- **No MISMATCH and no NOT-DETERMINABLE** among the 19 roles. No fallback/retry/substitution
  observed. One retried transport error (external-researcher), retried on the SAME recorded model.
- **Dispatch tool exposes NO `model` and NO `variant` parameter** (independently re-confirmed;
  exact params: `description, prompt, subagent_type, task_id, command, background`). DB-wide: 239
  task parts, zero with a model/variant key. => **the orchestrator never selected a model or variant.**
- Discriminating evidence that the child variant came from AGENT CONFIG, not parent inheritance:
  the dispatcher ran `control`/`high` while devops-executor ran `worker`/`low`.
- **Uncovered: the extension audit's own session** (self-reference); 20 of 21 dispatches covered.
- **NOT ESTABLISHED (B3):** provider-side target identity / wire-level effort; upstream substitution
  is NOT excluded.

## FINAL DEFECT REGISTER (against the orchestrator)

I7 domain-analyzer read outside the task root (read-only) — closed by scope tightening.
I8 debugger-deep packet named 2 roles that were actually correct.
I9 integrated "zero R_i->R_j edges" claim was FALSE — WITHDRAWN.
I10 INTEGRATED count mismatch — CORRECTED.
I11 coder artifact exclusion self-contradiction — minor wording.
I12 ledger line-number citation drift — CORRECTED (cite section names).
I13 R-D3/R-O1 under-defined — AMENDED.
I14 (root cause of the run's one real child defect) context-manager packet omitted the canonical
    short-token map while requiring predicted paths — 6 of 19 tokens are short forms.
I15 packet `Return only:` clause conflicts with the installed role contract — R-PACKET.
I16 `external-investigator` returned an EMPTY `task_result` (no terminal, no path). Deliverable
    recovered from the assigned artifact (protocol §3.5); the RETURN CHANNEL was defective.
    Root cause NOT established. See CHILD/OPS defects.
I17 a glob for `agents/SMOKE-EXT-*.md` returned NO files while both existed. The directory read is
    authoritative; a glob miss must never be treated as evidence of absence.
I18 reviewer packet described condensed criteria as "verbatim" — minor.

Child-behaviour defects (from audit): C1 context-manager's 5 wrong predicted filenames (self-flagged,
superseded); C2 = I7; C3 architect+coder return-format deviation (CAUSED by I15, no child blame).
Auditor self-disclosure: audit 1 wrote intermediate extracts under `/tmp/opencode/audit/`, outside
its literal single-write permission; disclosed by the child, no read-set file modified.

## UNRESOLVED CONFLICT (reported, not adjudicated)

**D1** — the basis the user supplied for the "public tier, corroborating only" boundary
("2 records in the whole client log, different key `dev-codex-…` under `medium`") could not be
reproduced by the extension audit from the only client log in the read set (it found 38 public
`stream` records + 1 error, and no `dev-codex` model key). The user's DISPOSITION is nonetheless
correct and independently confirmed: the client log carries no variant field for subagent sessions,
so it cannot verify variant. Possible explanations (NOT established): a different log/build than the
one in the authorized read set, or a different key/level interpretation. Reported for the user.

## NEXT

- Goal terminal. Verdict issued: **VERIFIED DONE**, scoped by B3 and with D1 reported unresolved.
