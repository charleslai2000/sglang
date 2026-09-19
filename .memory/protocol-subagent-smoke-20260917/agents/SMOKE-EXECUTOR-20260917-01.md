# SMOKE-EXECUTOR-20260917-01

status: DONE

## Task

Executor-role dispatch-path smoke test. Execute an already-specified mechanical
collection: for each of the 19 canonical artifact paths, record EXISTS/ABSENT and
byte size, and emit the result as a manifest table in this artifact. No project
subject beyond the canonical file list.

task_id: SMOKE-EXECUTOR-20260917-01
role: executor

## Scope

Confined to:
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/`

No reads or writes outside it. The orchestrator ledger and other agents' artifacts
were not written or edited. No files were created, moved, renamed, or deleted
(other than this result artifact, the sole permitted write). No git, no GPU, no
services, no network.

## Result

Manifest snapshot taken before this artifact was written (command run C1).
Each canonical filename is resolved against the `agents/` directory.

| filename | EXISTS/ABSENT | bytes |
|---|---|---|
| SMOKE-ARCHITECT-20260917-01.md | EXISTS | 6980 |
| SMOKE-CODER-20260917-01.md | ABSENT | - |
| SMOKE-CONTEXT-20260917-01.md | EXISTS | 10188 |
| SMOKE-DEBUGGER-DEEP-20260917-01.md | ABSENT | - |
| SMOKE-DEVOPS-20260917-01.md | ABSENT | - |
| SMOKE-DEVOPS-EXEC-20260917-01.md | ABSENT | - |
| SMOKE-DOC-WRITER-20260917-01.md | EXISTS | 7777 |
| SMOKE-DOMAIN-ANALYZER-20260917-01.md | EXISTS | 22323 |
| SMOKE-EXECUTOR-20260917-01.md | ABSENT | - |
| SMOKE-EXT-ANALYST-20260917-01.md | ABSENT | - |
| SMOKE-EXT-INVESTIGATOR-20260917-01.md | ABSENT | - |
| SMOKE-EXT-RESEARCHER-20260917-01.md | ABSENT | - |
| SMOKE-FRONTEND-20260917-01.md | ABSENT | - |
| SMOKE-REVIEWER-20260917-01.md | ABSENT | - |
| SMOKE-REVIEWER-DEEP-20260917-01.md | ABSENT | - |
| SMOKE-SCOUT-20260917-01.md | EXISTS | 5640 |
| SMOKE-TASK-MGR-20260917-01.md | EXISTS | 17883 |
| SMOKE-TEST-RUNNER-20260917-01.md | ABSENT | - |
| SMOKE-TESTER-20260917-01.md | ABSENT | - |

19 rows. 6 EXISTS, 13 ABSENT at snapshot time.

Note on self-reference: `SMOKE-EXECUTOR-20260917-01.md` (this artifact) records
ABSENT because the snapshot was taken before this file was written. It was
created by this task as its one permitted write, not pre-existing.

## Evidence

### Command C1 — manifest snapshot (executed before writing this artifact)

Exact command:

```
D=/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/agents; for f in SMOKE-SCOUT-20260917-01.md SMOKE-ARCHITECT-20260917-01.md SMOKE-CONTEXT-20260917-01.md SMOKE-TASK-MGR-20260917-01.md SMOKE-DOMAIN-ANALYZER-20260917-01.md SMOKE-DOC-WRITER-20260917-01.md SMOKE-CODER-20260917-01.md SMOKE-EXECUTOR-20260917-01.md SMOKE-DEBUGGER-DEEP-20260917-01.md SMOKE-REVIEWER-20260917-01.md SMOKE-REVIEWER-DEEP-20260917-01.md SMOKE-TESTER-20260917-01.md SMOKE-TEST-RUNNER-20260917-01.md SMOKE-DEVOPS-20260917-01.md SMOKE-DEVOPS-EXEC-20260917-01.md SMOKE-FRONTEND-20260917-01.md SMOKE-EXT-INVESTIGATOR-20260917-01.md SMOKE-EXT-RESEARCHER-20260917-01.md SMOKE-EXT-ANALYST-20260917-01.md; do p="$D/$f"; if [ -f "$p" ]; then printf '%s|EXISTS|%s\n' "$f" "$(stat -c %s "$p")"; else printf '%s|ABSENT|-\n' "$f"; fi; done | sort; echo "EXIT_STATUS=$?"
```

Verbatim output:

```
SMOKE-ARCHITECT-20260917-01.md|EXISTS|6980
SMOKE-CODER-20260917-01.md|ABSENT|-
SMOKE-CONTEXT-20260917-01.md|EXISTS|10188
SMOKE-DEBUGGER-DEEP-20260917-01.md|ABSENT|-
SMOKE-DEVOPS-20260917-01.md|ABSENT|-
SMOKE-DEVOPS-EXEC-20260917-01.md|ABSENT|-
SMOKE-DOC-WRITER-20260917-01.md|EXISTS|7777
SMOKE-DOMAIN-ANALYZER-20260917-01.md|EXISTS|22323
SMOKE-EXECUTOR-20260917-01.md|ABSENT|-
SMOKE-EXT-ANALYST-20260917-01.md|ABSENT|-
SMOKE-EXT-INVESTIGATOR-20260917-01.md|ABSENT|-
SMOKE-EXT-RESEARCHER-20260917-01.md|ABSENT|-
SMOKE-FRONTEND-20260917-01.md|ABSENT|-
SMOKE-REVIEWER-20260917-01.md|ABSENT|-
SMOKE-REVIEWER-DEEP-20260917-01.md|ABSENT|-
SMOKE-SCOUT-20260917-01.md|EXISTS|5640
SMOKE-TASK-MGR-20260917-01.md|EXISTS|17883
SMOKE-TEST-RUNNER-20260917-01.md|ABSENT|-
SMOKE-TESTER-20260917-01.md|ABSENT|-
EXIT_STATUS=0
```

Exit status: 0.

### Command C2 — post-write verification (executed after writing this artifact)

Exact command:

```
D=/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/protocol-subagent-smoke-20260917/agents; f=SMOKE-EXECUTOR-20260917-01.md; p="$D/$f"; if [ -f "$p" ]; then printf '%s|EXISTS|%s\n' "$f" "$(stat -c %s "$p")"; else printf '%s|ABSENT|-\n' "$f"; fi; echo "EXIT_STATUS=$?"
```

Verbatim output:

```
SMOKE-EXECUTOR-20260917-01.md|EXISTS|5154
EXIT_STATUS=0
```

Exit status: 0. Size is that observed at C2 time; the delivered revision may differ
slightly after subsequent terminal edits (including this evidence correction).

## Defects-blockers

None. C1 and C2 both completed with exit status 0.

## Remaining claims-exclusions

- Byte sizes are a point-in-time snapshot; concurrent writers could change them.
- Only file type regular-file presence is tested (`[ -f ]`); a directory or other
  non-regular entry at a canonical path would report ABSENT.
- This task did not inspect or validate the contents of any listed artifact.
- Zero files were created, moved, renamed, or deleted by this task other than
  this result artifact (the sole permitted write).

## Terminal state

DONE
