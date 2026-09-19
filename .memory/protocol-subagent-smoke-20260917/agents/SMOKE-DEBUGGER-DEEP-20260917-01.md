# SMOKE-DEBUGGER-DEEP-20260917-01 — debugger-deep result artifact

## Task
- task_id: SMOKE-DEBUGGER-DEEP-20260917-01
- role: debugger-deep
- goal: Causally reconstruct the real, file-evidenced defect in
  `agents/SMOKE-CONTEXT-20260917-01.md` — its 19-row index predicts result-artifact
  paths for rows 4–19 by mechanically uppercasing the role name, and those predictions
  are wrong.
- Dispatch validation: VALID. `ledger.md` ACTIVE (line 92) records
  `SMOKE-DEBUGGER-DEEP-20260917-01 | debugger-deep | causal reconstruction of the
  context-manager token-prediction defect (real, file-evidenced)`; the subject file is
  inside the authorized task root; the only permitted write is this result artifact;
  `ledger.md` and all other specialist artifacts were read-only. No git, GPU, services,
  or network used. One dispatch-narrative discrepancy was found and is recorded under
  Defects-blockers (the example list includes two rows that are not actually wrong).
- Inputs: `agents/SMOKE-CONTEXT-20260917-01.md` (subject); `ledger.md` (authoritative
  CANONICAL ARTIFACT PATHS, lines 31–47, and W1/W2 integration records); live listings
  of `agents/` inside the task root.
- Dependencies: none.

## Scope
- Read-only outside this artifact, confined to
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`.
- Only write performed: this result artifact. `ledger.md` and other agents' artifacts
  were never written or amended.
- No git, no GPU, no services, no network, no new observation mechanisms. Evidence is
  from the normal filesystem path (listings, `stat`, read-only parsing of the two files
  named above).
- This artifact diagnoses the token-prediction defect only. It does not certify any
  other artifact's content or terminal state, and it does not discharge the
  orchestrator's terminal integration.

## Result

### Observed evidence (quoted, not inferred)

Subject artifact prediction caveat (`SMOKE-CONTEXT-20260917-01.md` lines 40–43):

> `<ROLE>` is the role's uppercase dispatch-identity token. Only three tokens are
> materialized/confirmed by observable state in this run: `SCOUT`, `ARCHITECT`,
> `CONTEXT` (context-manager). For the 16 roles not yet dispatched at write time
> (`ledger.md` marks them `READY (slot-blocked)`), the token below is the uppercase role
> name and is a PREDICTION, explicitly flagged, not an observed fact.

Subject artifact risk flag (`SMOKE-CONTEXT-20260917-01.md` lines 79–86):

> **Confirmed vs predicted tokens:** `SCOUT`, `ARCHITECT`, `CONTEXT` are confirmed by
> `ledger.md` lines 51–53 and by this task's assigned result path. Rows 4–19 use the
> uppercase role name as a prediction (those roles were `READY (slot-blocked)` and their
> tokens were not materialized at write time). In particular, the confirmed token for
> context-manager is `CONTEXT`, not the literal role-name uppercase `CONTEXT-MANAGER`;
> if the orchestrator's short-token convention also applies to other multi-word roles
> (e.g. task-manager, doc-writer, test-runner, external-*), their real tokens may differ
> from the predicted paths above. This is called out in Remaining claims-exclusions.

Subject artifact exclusion (`SMOKE-CONTEXT-20260917-01.md` lines 160–166):

> The table does not prove the EXPECTED PATH is the path the orchestrator will actually
> use for rows 4–19. The confirmed token for context-manager is `CONTEXT`, demonstrating
> that the orchestrator may shorten multi-word role names; therefore the predicted
> uppercase-role-name paths for other multi-word roles (task-manager, domain-analyzer,
> doc-writer, debugger-deep, reviewer-deep, test-runner, devops-executor,
> external-investigator, external-researcher, external-analyst) are unverified and may
> be wrong.

Wrong sample rows as published (lines 55, 66, 68, 69, 70; full paths abbreviated at the
artifact's own `.memory/protocol-subagent-smoke-20260917/agents/` prefix):

| row | role | published predicted path |
|-----|------|--------------------------|
| 4 | task-manager | `SMOKE-TASK-MANAGER-20260917-01.md` |
| 15 | devops-executor | `SMOKE-DEVOPS-EXECUTOR-20260917-01.md` |
| 17 | external-investigator | `SMOKE-EXTERNAL-INVESTIGATOR-20260917-01.md` |
| 18 | external-researcher | `SMOKE-EXTERNAL-RESEARCHER-20260917-01.md` |
| 19 | external-analyst | `SMOKE-EXTERNAL-ANALYST-20260917-01.md` |

Authoritative ledger (`ledger.md`) quotes:

- line 31: `## CANONICAL ARTIFACT PATHS (authoritative; resolves O3 / context-manager prediction defect)`
- lines 33–34: `Token convention is an explicit short form, NOT mechanical uppercase of the role name.`
- canonical entries: row 4 = `SMOKE-TASK-MGR-20260917-01.md`; row 15 =
  `SMOKE-DEVOPS-EXEC-20260917-01.md`; row 17 = `SMOKE-EXT-INVESTIGATOR-20260917-01.md`;
  row 18 = `SMOKE-EXT-RESEARCHER-20260917-01.md`; row 19 =
  `SMOKE-EXT-ANALYST-20260917-01.md`.

Observed on-disk confirmation at `2026-09-17T20:49:47Z` (agents/ listing): files
`SMOKE-TASK-MGR-20260917-01.md`, `SMOKE-DOC-WRITER-20260917-01.md`, and
`SMOKE-DOMAIN-ANALYZER-20260917-01.md` exist. The task-manager dispatch therefore used
the short token `TASK-MGR`, not the predicted `TASK-MANAGER`.

Timeline observation: the subject artifact's own E1 snapshot (taken at ~20:46)
recorded `ledger.md` as `3038` bytes; my read-only `stat` at `20:49:38` shows
`7359` bytes, and the subject artifact's quoted line numbers (`ledger.md` line 55 for
the path template; lines 51–53 for the W1 identities) no longer match current ledger
content — consistent with the CANONICAL ARTIFACT PATHS section having been inserted
after the index was written.

### Row-by-row comparison (observed-derived)
Read-only parse of the subject table (19 rows) against the ledger canonical table
(19 rows), exact filename equality: rows 1–3 and 5–14 and 16 coincide; rows
**4, 15, 17, 18, 19** mismatch. No other rows mismatch. The 5 mismatches are exactly
the roles for which the orchestrator's canonical token is a short form; all 11
coinciding predicted rows are roles whose canonical token happens to equal
`uppercase(role)` (e.g. `DOMAIN-ANALYZER`, `DOC-WRITER`, `TEST-RUNNER`,
`REVIEWER-DEEP`, `EXECUTOR`).

### Inference (analysis, not directly observed)
- The prediction method was invalid in principle for all 16 not-yet-dispatched rows
  (it derived a path from a transform), so every row 4–19 carried prediction risk; only
  5 happened to be wrong by value.
- The subject artifact already held a disconfirming sample before writing: its own
  token was confirmed as `CONTEXT`, not `CONTEXT-MANAGER`. The artifact recognized the
  short-token convention and explicitly warned the mechanical rule might not
  generalize, yet still published computed filenames in the same
  `Expected artifact path` column used for confirmed paths.
- The canonical mapping likely did not exist in `ledger.md` at the subject artifact's
  write time (size/mtime growth after the E1 snapshot; line-number drift; the ledger
  header explicitly calls the section a resolution of this defect). This made
  prediction tempting, but it did not make the mechanical transform correct.

### Competing hypotheses and verdicts

**H1 — Mechanical token derivation without a canonical oracle (SUPPORTED; root cause).**
The index computed `<ROLE>.upper()` for the 16 pending roles instead of marking the
path cell unknown or obtaining the canonical map. This predicts exactly the observed
pattern: mismatch precisely on the 5 short-form roles (`TASK-MGR`, `DEVOPS-EXEC`,
`EXT-*`) and coincidence on every role whose canonical token is already the uppercase
role name. Supported additionally by the artifact's own admissions (lines 79–86,
160–166) and by the observed `SMOKE-TASK-MGR-20260917-01.md` on disk. The defect is the
method plus publishing its output in the authoritative-looking path column.

**H2 — No canonical token existed at write time, so the tokens genuinely could not have
been known (PARTIALLY SUPPORTED as enabling condition; REFUTED as root cause).**
Supported: artifact lines 41–43 state the 16 tokens were not materialized, and the
ledger canonical section was added after the snapshot as the defect's resolution.
But it cannot explain the defect: the artifact's own row already falsified mechanical
uppercase, so a correct response existed (emit `UNKNOWN — token pending dispatch`, or
escalate for the canonical map). The information gap explains why a prediction was
attempted; it does not explain why a mechanically computed filename was placed in the
same column as confirmed paths. Hence contributing condition, not cause.

**H3 — Transcription/misread of a canonical token list that was supplied in the
dispatch (REFUTED).** The artifact explicitly states the 16 rows are predictions, and
the recorded dispatch input is a 19-role name list, not a token list (artifact lines
14–17). A transcription error would scatter mismatches; instead the 5 errors are
systematic — exactly the short-form roles — which is the signature of a transform, not
a slip. If an authoritative token list had been available and misread, the artifact
would not have needed to flag the column as prediction.

### Root cause (one sentence)
The index generator produced its `Expected artifact path` column for the 16
not-yet-dispatched roles by mechanically uppercasing the role name instead of
consuming or soliciting the orchestrator's explicit short-token convention, so the 5
roles whose canonical token is a short form (TASK-MGR, DEVOPS-EXEC, EXT-INVESTIGATOR,
EXT-RESEARCHER, EXT-ANALYST) were published with wrong filenames in the same column
used for confirmed paths.

### Minimal counterfactual (single change at dispatch time)
If the context-manager's dispatch packet had included the orchestrator's canonical
19-file mapping (the table now in `ledger.md` lines 36–47), no token prediction would
have been needed and rows 4, 15, 17, 18, 19 would have been exact; alternatively, no
predicted filename should have been emitted for pending tokens.

### Minimal repair
Treat `ledger.md` lines 31–47 (`CANONICAL ARTIFACT PATHS`) as authoritative and
supersede rows 4, 15, 17, 18, 19 of the subject index; treat the whole of rows 4–19 as
non-canonical predictions. If an artifact-level correction is required, the
orchestrator should dispatch context-manager to append a single correction note naming
the 5 canonical filenames — this debugger must not and did not edit the subject
artifact or the ledger.

### Exact rows affected
- Wrong by value (5 rows): **4** (task-manager → `SMOKE-TASK-MGR-...`), **15**
  (devops-executor → `SMOKE-DEVOPS-EXEC-...`), **17** (external-investigator →
  `SMOKE-EXT-INVESTIGATOR-...`), **18** (external-researcher →
  `SMOKE-EXT-RESEARCHER-...`), **19** (external-analyst → `SMOKE-EXT-ANALYST-...`).
- Affected by the prediction-status defect (16 rows): **4–19**; the other 11
  (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16) coincide with canonical by coincidence of the
  naming rule, not because the predicted column was valid.
- Dispatch-narrative discrepancy: the dispatch named `SMOKE-DOC-WRITER-...` (row 6) and
  `SMOKE-TEST-RUNNER-...` (row 13) among the wrong examples; both coincide with the
  canonical table, and `SMOKE-DOC-WRITER-20260917-01.md` is observed on disk. They are
  prediction-status rows, not value errors.

## Evidence
All commands run read-only with the task root as working directory; no file outside the
task root was touched and no file was written except this artifact.

E1 — timestamped agent listing (observed tokens on disk):
```
$ date -u '+%Y-%m-%dT%H:%M:%SZ'
2026-09-17T20:49:47Z
$ ls -la .../protocol-subagent-smoke-20260917/agents/
-rw-rw-r-- 1 ubuntu ubuntu  6980 Sep 17 20:46 SMOKE-ARCHITECT-20260917-01.md
-rw-rw-r-- 1 ubuntu ubuntu 10188 Sep 17 20:46 SMOKE-CONTEXT-20260917-01.md
-rw-rw-r-- 1 ubuntu ubuntu  7777 Sep 17 20:47 SMOKE-DOC-WRITER-20260917-01.md
-rw-rw-r-- 1 ubuntu ubuntu 22323 Sep 17 20:49 SMOKE-DOMAIN-ANALYZER-20260917-01.md
-rw-rw-r-- 1 ubuntu ubuntu  5640 Sep 17 20:46 SMOKE-SCOUT-20260917-01.md
-rw-rw-r-- 1 ubuntu ubuntu 17883 Sep 17 20:48 SMOKE-TASK-MGR-20260917-01.md
```
Exit status: 0.

E2 — ledger timeline/state:
```
$ stat -c '%n size=%s mtime=%y' .../protocol-subagent-smoke-20260917/ledger.md
.../ledger.md size=7359 mtime=2026-09-17 20:49:38.280213927 +0000
```
Exit status: 0. Compare subject artifact E1 (~20:46): `ledger.md` was `3038` bytes.

E3 — deterministic comparison, read-only parse of both tables, exact filename
equality (19 canonical rows vs 19 predicted rows):
```
4  task-manager          predicted=SMOKE-TASK-MANAGER-...        canonical=SMOKE-TASK-MGR-...            MISMATCH
15 devops-executor       predicted=SMOKE-DEVOPS-EXECUTOR-...     canonical=SMOKE-DEVOPS-EXEC-...         MISMATCH
17 external-investigator predicted=SMOKE-EXTERNAL-INVESTIGATOR-... canonical=SMOKE-EXT-INVESTIGATOR-...  MISMATCH
18 external-researcher   predicted=SMOKE-EXTERNAL-RESEARCHER-... canonical=SMOKE-EXT-RESEARCHER-...      MISMATCH
19 external-analyst      predicted=SMOKE-EXTERNAL-ANALYST-...    canonical=SMOKE-EXT-ANALYST-...         MISMATCH
MISMATCH rows: [4, 15, 17, 18, 19]
COINCIDENT rows: [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16]
```
Method note: an initial single-regex parser matched only 10 canonical rows because the
ledger table shares `|` delimiters between its two column groups; re-parsed by splitting
on `|` into cells, which yielded all 19/19 rows. The corrected output above is the one
relied upon.

E4 — quoted source lines: subject artifact lines 40–43, 55, 66, 68–70, 79–86, 160–166;
ledger lines 31, 33–34, 36–47. Verbatim excerpts appear in Result above. No write was
performed on either file.

## Defects-blockers
- None blocking this task. The diagnosed defect is confirmed: 5 of 16 predicted paths
  are wrong (rows 4, 15, 17, 18, 19), and all 16 prediction rows are methodologically
  non-canonical.
- Dispatch-precision discrepancy (recorded, not repaired here): the dispatch's example
  list (`SMOKE-DOC-WRITER-...`, `SMOKE-TEST-RUNNER-...`) is broader than the actual
  value-error set; per the authoritative ledger and observed disk state those two rows
  coincide with canonical. This does not change the defect or its root cause.
- The subject artifact did flag the risk itself (lines 79–86 and 160–166), so the
  prediction was disclosed rather than silently asserted; the defect is that predicted
  filenames were published in the `Expected artifact path` column without being
  segregated from confirmed paths, which downstream consumers can mistake for canonical.

## Remaining claims-exclusions
- Existence, not content: other agents' artifacts were observed as filenames only; no
  claim is made about their contents or terminal states.
- The claim that the ledger lacked the canonical table at the subject artifact's write
  time is an inference from size/mtime growth and line-number drift, not a direct
  observation of a prior ledger revision.
- The canonical table is authoritative only insofar as the orchestrator's own ledger
  declares it; if the orchestrator later revises tokens, the mismatch set changes.
- This artifact does not amend or supersede `SMOKE-CONTEXT-20260917-01.md` or
  `ledger.md`, and does not discharge the run verdict (`ledger.md` F9/F10 remain
  dependency-blocked on the remaining waves).
- No product, test, config, service, GPU, or network surface was touched; the smoke
  goal has no project subject.

## Terminal state
DONE
