# SOURCE AUTHORITY CORRECTION — 2026-09-17 (owner ruling)

This **supersedes** the earlier working assumption that `3090-24g-hicache` was the production
source authority, and the practice of treating `/opt/sglang/local-prod-*` or `/tmp/opencode/*`
copies as development source trees.

## New authority model (binding)

| location | role |
|---|---|
| repo `sglang-3090-24g-opt` | **the** development source authority |
| branch `3090-24g-opt` | **authoritative development branch**; all formal development lands here |
| `/opt/sglang/local-prod-*` | deployment artifact / historical evidence **only** — never edited, never a source tree |
| `/tmp/opencode/*` | scratch; must be `rm -rf`-safe at any time |
| `/var/log/sglang/*` | run results only |

Direction of truth is one-way:

    git commit SHA  ->  deterministic deploy  ->  /opt tree

NOT `/opt -> source`.

## Rules
* Every subagent that writes code must report `REPO_ROOT`, `BASE_BRANCH`, `BASE_COMMIT`,
  `WORKTREE_PATH`, `TASK_BRANCH`, and must work in a **git worktree** on a `task/*` branch.
* No development inside `/tmp` source copies; no editing `/opt`; no detached-HEAD deliverables.
* Task completion = tests PASS -> independent review -> commit -> merge back to `3090-24g-opt`
  -> delete task worktree. Usable results must never exist only in a worktree.
* Gates, oracles, freeze/deploy tools, provider lifecycle scripts and identity validators are
  **code** and live in `3090-dev/{gates,tools,deploy}/`. Only their *results* go to `/var/log`.
* `.memory` holds decisions, reports, manifests and evidence indexes — never the only copy of
  executable code.
* Do not `git add -A`; do not merge the UNREVIEWED default-branch commit; import only allowlisted files/hunks.
* No new "frozen source tree" may be created as a development authority.

## Acceptance checklist for this correction

    SOURCE_AUTHORITY            = git branch 3090-24g-opt
    PRODUCTION_COMMIT           = <sha>
    DEPLOYED_FROM_COMMIT        = yes
    UNCOMMITTED_PRODUCTION_CODE = 0
    UNIQUE_CODE_IN_TMP          = 0
    UNIQUE_CODE_IN_OPT          = 0
    REUSABLE_HARNESS_OUTSIDE_GIT= 0
