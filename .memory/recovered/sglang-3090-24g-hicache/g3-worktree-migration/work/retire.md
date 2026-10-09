# Linked worktree retirement

ENTRY: ACCEPT

Task ID: `WORKTREE-RETIRE-20260907`  
Epoch: E3  
Role: executor  
Invocation status: **done**  
Date: 2026-09-07 (Asia/Shanghai)

## Goal and scope

Retired exactly:

`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`

Only local filesystem/Git state was touched. The current clone, main repository
contents, unrelated worktrees, remote hosts, and processes were not touched.

## Pre-removal evidence

- Exact target existed and was registered as a linked worktree.
- Target `.git` contained exactly:
  `gitdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.git/worktrees/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`.
- Target and current HEAD were both
  `dac6db1ebabdb80209b757fd063cf53e05c091e7`; the preserved branch ref
  resolved to the same commit.
- The target's five dirty tracked paths matched current byte-for-byte:
  `protocol.py`, `serving_chat.py`, `serving_completions.py`,
  `custom_logit_processor.py`, and
  `test_custom_logit_processor.py`.
- The four target nonignored untracked handoffs matched current byte-for-byte:
  `AGENTS.md`, `CODEX_DPRIME_STATIC_REVIEW.md`, `CODEX_HANDOFF.md`, and
  `HANDOFF-G3-2026-09-07.md`.
- No old-only nonignored files existed. Old-only regular files were ignored
  `.ruff_cache/**` and `__pycache__/*.pyc` cache artifacts only.
- A `/proc` scan found no live process whose cwd, root, executable, or
  command-path argument was under the exact target. (An earlier scan's
  transient shell match was rechecked using path-token matching; it was not a
  target process.)
- Main repository status before removal was preserved as the existing dirty
  `3090-24g-hicache` worktree with its `.memory/` and five `3090-dev/*` files.

## Commands and result

The linked-worktree-aware normal removal was attempted first:

```text
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache \
  worktree remove \
  /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
```

It correctly refused with exit 128 because the target contained modified or
untracked files. After the byte-identical-copy and process checks above, the
authorized exact-target force removal was run:

```text
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache \
  worktree remove --force \
  /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
```

It exited 0. No `rm -rf`, branch deletion, worktree prune, or broad cleanup
was used.

## Post-removal verification

- Exact target path: **absent**.
- Exact linked-worktree metadata directory:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.git/worktrees/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`: **absent**.
- Main `git worktree list --porcelain`: target no longer listed; the two
  unrelated worktrees remain registered.
- Branch ref `refs/heads/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s` still
  exists and still resolves to
  `dac6db1ebabdb80209b757fd063cf53e05c091e7`.
- Current worktree status after removal is unchanged from before removal:
  the six listed modified paths and five listed untracked entries (including
  `.memory/`) remain. Main repository status is likewise unchanged.

## What was removed and recoverability

The old linked-worktree directory, its dirty duplicate copies, ignored cache
files, and Git linked-worktree metadata were removed. No unique nonignored data
was removed: all nine dirty/untracked handoff/source copies were verified in
the current tree, while the target branch ref and commit remain preserved in
the main repository. The current clone also retains the same commit and its
working copies. Status: **done**.
