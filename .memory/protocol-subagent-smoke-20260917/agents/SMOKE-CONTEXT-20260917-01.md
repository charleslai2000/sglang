# SMOKE-CONTEXT-20260917-01 — context-manager result artifact

## Task
- task_id: SMOKE-CONTEXT-20260917-01
- role: context-manager
- goal: Record the durable context index for this smoke run — the 19 role dispatch
  identities, their expected result-artifact paths, and which of those artifacts
  existed at the moment this artifact was written.
- Dispatch validation: VALID. `ledger.md` line 53 records
  `SMOKE-CONTEXT-20260917-01 | context-manager | expected-artifact index for this smoke
  run`, matching this dispatch; the task root under
  `.memory/protocol-subagent-smoke-20260917/` is within scope; the only permitted write is
  this result artifact; no orchestrator ledger or other specialist report was touched.
- Inputs: the 19-role list supplied in the dispatch (scout, architect, context-manager,
  task-manager, domain-analyzer, doc-writer, coder, executor, debugger-deep, reviewer,
  reviewer-deep, tester, test-runner, devops, devops-executor, frontend,
  external-investigator, external-researcher, external-analyst).
- Dependencies: none.

## Scope
- Read-only outside this artifact, confined to
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`.
- No reads/writes/creates/deletes outside that directory. `ledger.md` was read, never
  written. No git, no GPU, no services, no network, no new observation mechanisms.
- Only write performed: this result artifact.
- This artifact records an INDEX only. It does not validate the content or terminal state
  of any listed artifact, and it does not modify or amend the orchestrator ledger or any
  other specialist's report.

## Result

### Expected artifact path template
Per the dispatch and `ledger.md` line 55, each role's result artifact lives at:

```
.memory/protocol-subagent-smoke-20260917/agents/SMOKE-<ROLE>-20260917-01.md
```

`<ROLE>` is the role's uppercase dispatch-identity token. Only three tokens are
materialized/confirmed by observable state in this run: `SCOUT`, `ARCHITECT`,
`CONTEXT` (context-manager). For the 16 roles not yet dispatched at write time
(`ledger.md` marks them `READY (slot-blocked)`), the token below is the uppercase role
name and is a PREDICTION, explicitly flagged, not an observed fact.

### Role index (19 rows)
Exists/absent is taken from the real directory listing at
`2026-09-17T20:46:34Z` (Evidence, Command E3), immediately before this artifact was
written.

| # | Role | Expected artifact path | EXISTS/ABSENT |
|---|------|------------------------|---------------|
| 1 | scout | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-SCOUT-20260917-01.md` | EXISTS |
| 2 | architect | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-ARCHITECT-20260917-01.md` | ABSENT |
| 3 | context-manager | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-CONTEXT-20260917-01.md` | ABSENT |
| 4 | task-manager | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-TASK-MANAGER-20260917-01.md` | ABSENT |
| 5 | domain-analyzer | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DOMAIN-ANALYZER-20260917-01.md` | ABSENT |
| 6 | doc-writer | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DOC-WRITER-20260917-01.md` | ABSENT |
| 7 | coder | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-CODER-20260917-01.md` | ABSENT |
| 8 | executor | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-EXECUTOR-20260917-01.md` | ABSENT |
| 9 | debugger-deep | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DEBUGGER-DEEP-20260917-01.md` | ABSENT |
| 10 | reviewer | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-REVIEWER-20260917-01.md` | ABSENT |
| 11 | reviewer-deep | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-REVIEWER-DEEP-20260917-01.md` | ABSENT |
| 12 | tester | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-TESTER-20260917-01.md` | ABSENT |
| 13 | test-runner | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-TEST-RUNNER-20260917-01.md` | ABSENT |
| 14 | devops | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DEVOPS-20260917-01.md` | ABSENT |
| 15 | devops-executor | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-DEVOPS-EXECUTOR-20260917-01.md` | ABSENT |
| 16 | frontend | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-FRONTEND-20260917-01.md` | ABSENT |
| 17 | external-investigator | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-EXTERNAL-INVESTIGATOR-20260917-01.md` | ABSENT |
| 18 | external-researcher | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-EXTERNAL-RESEARCHER-20260917-01.md` | ABSENT |
| 19 | external-analyst | `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-EXTERNAL-ANALYST-20260917-01.md` | ABSENT |

Summary: 1 EXISTS (scout), 18 ABSENT at the observation instant.

### Notes that constrain the table
- **Self row (context-manager, #3):** the row reads ABSENT because this artifact did not
  exist at the observation instant. This write creates it, so after this write
  `SMOKE-CONTEXT-20260917-01.md` exists. The listing was taken before the write on
  purpose, so the column reflects ground truth at that instant, not a post-write state.
- **Confirmed vs predicted tokens:** `SCOUT`, `ARCHITECT`, `CONTEXT` are confirmed by
  `ledger.md` lines 51–53 and by this task's assigned result path. Rows 4–19 use the
  uppercase role name as a prediction (those roles were `READY (slot-blocked)` and their
  tokens were not materialized at write time). In particular, the confirmed token for
  context-manager is `CONTEXT`, not the literal role-name uppercase `CONTEXT-MANAGER`;
  if the orchestrator's short-token convention also applies to other multi-word roles
  (e.g. task-manager, doc-writer, test-runner, external-*), their real tokens may differ
  from the predicted paths above. This is called out in Remaining claims-exclusions.
- **Liveness:** the task root is live with concurrent sibling dispatches. The first
  directory listing in this run (Evidence E1, ~20:45Z) showed `agents/` empty; the scout
  artifact appeared before the E3 listing. Therefore EXISTS/ABSENT is a point-in-time
  snapshot and later snapshots may differ.

## Evidence
All commands run with working directory set to the task root unless noted. No file
outside the task root was touched.

E1 — initial ground-truth listing (before any child artifact was visible):
```
$ ls -la /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/
total 16
drwxrwxr-x 3 ubuntu ubuntu 4096 Sep 17 20:45 .
drwxrwxr-x 4 ubuntu ubuntu 4096 Sep 17 20:39 ..
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 17 20:41 agents
-rw-rw-r-- 1 ubuntu ubuntu 3038 Sep 17 20:46 ledger.md

$ ls -la /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/agents/
total 8
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 17 20:41 .
drwxrwxr-x 3 ubuntu ubuntu 4096 Sep 17 20:45 ..
```
Exit status: 0. `agents/` contained no role artifacts at that instant.

E2 — task-root `find` (shows the scout artifact appeared concurrently):
```
$ find /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/ -mindepth 1
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/agents
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/agents/SMOKE-SCOUT-20260917-01.md
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/ledger.md
```
Exit status: 0.

E3 — authoritative listing used for the EXISTS/ABSENT column (timestamped):
```
$ date -u '+%Y-%m-%dT%H:%M:%SZ'
2026-09-17T20:46:34Z
$ cd /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917
$ ls -1 agents/
SMOKE-SCOUT-20260917-01.md
$ ls -1 agents/ | wc -l
1
```
Exit status: 0 (`date`), 0 (`ls`), 0 (`wc`). Exactly one artifact present:
`SMOKE-SCOUT-20260917-01.md`.

E4 — ledger read (provenance only, no write):
`ledger.md` lines 51–55 confirm the three W1 dispatch identities and the artifact path
template `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-<ROLE>-20260917-01.md`;
lines 36–41 mark the remaining roles `READY (slot-blocked)`.

E5 — post-write self-check (run after this artifact was created):
```
$ ls -1 agents/
SMOKE-CONTEXT-20260917-01.md
SMOKE-SCOUT-20260917-01.md
```
Confirms this index artifact now exists alongside the scout artifact. `ledger.md` was
not modified (read-only treatment), consistent with the single permitted write.

## Defects-blockers
- None. No BLOCKED condition encountered.
- Two observations recorded as context, not defects:
  1. The task root is concurrently active, so a point-in-time EXISTS/ABSENT column is
     inherently a snapshot. Mitigated by timestamping the listing (E3).
  2. Confirmed dispatch tokens for multi-word roles other than context-manager are not
     yet observable, so rows 4–19 of the index are predictions (see below).

## Remaining claims-exclusions
- EXISTS/ABSENT reflects only the directory listing at `2026-09-17T20:46:34Z`. It is not
  a claim about artifact content, validity, terminal state, or acceptance — only
  existence of a file at the expected path.
- The table does not prove the EXPECTED PATH is the path the orchestrator will actually
  use for rows 4–19. The confirmed token for context-manager is `CONTEXT`, demonstrating
  that the orchestrator may shorten multi-word role names; therefore the predicted
  uppercase-role-name paths for other multi-word roles (task-manager, domain-analyzer,
  doc-writer, debugger-deep, reviewer-deep, test-runner, devops-executor,
  external-investigator, external-researcher, external-analyst) are unverified and may
  be wrong.
- No content of `SMOKE-SCOUT-20260917-01.md` is asserted beyond its existence here (its
  content was not relied upon for this index).
- No product, test, config, service, GPU, or network surface was touched; the smoke goal
  has no project subject.
- This artifact does not reconcile, amend, or supersede the orchestrator ledger, and it
  does not discharge the orchestrator's terminal integration of all 19 artifacts.

## Terminal state
DONE
