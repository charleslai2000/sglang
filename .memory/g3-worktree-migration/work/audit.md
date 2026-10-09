# Worktree migration audit

ENTRY: ACCEPT

Task ID: `WORKTREE-MIGRATION-AUDIT-R1-20260907`  
Epoch: E3  
Role: reviewer  
Invocation status: **done**  
Audit date: 2026-09-07 (Asia/Shanghai)

## Scope and method

Compared the retirement candidate
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`
(`old`) with the current tree
`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s` (`current`).
Read both root and `docs/AGENTS.md`, Git status/diffs/refs/reflogs/stashes,
worktree registration, handoff documentation, and current `.memory` state.
No product file, Git ref, worktree, remote, process, or benchmark was changed.

The full filesystem sweep excluded `.git`; ignored cache/build output was not
hashed. Model/artifact binaries were not read. The only matching special data
file found was the common tracked `benchmark/llava_bench/questions.jsonl`
(8,246 bytes). No `.gguf`, `.safetensors`, `.bin`, `.pt`, `.pth`, `.pem`, or
credential-bearing binary was found in either tree.

## Git identity and ancestry

Both worktrees have the same branch and commit:

| Field | old | current |
|---|---|---|
| branch | `sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s` | same |
| HEAD | `dac6db1ebabdb80209b757fd063cf53e05c091e7` | same |
| tree | `5bcb6d5ec9f2d1088f6caca330246ef757946bb8` | same |
| parent | `d0e9450123de7b425e7e95a00f25c450704dfbab` | same |
| HEAD subject | `test(qwen35): B2 test harness + checkpoint doc` | same |
| merge-base with tracked remote branch | `dac6db1ebabdb80209b757fd063cf53e05c091e7` | same |

`git diff --name-status <old-HEAD> <current-HEAD>` is empty because the
commits and trees are identical. Neither repository has a stash. The current
tree is a separate clone (`.git` directory, `origin=/tmp/sglang-qwen3-27b-iq3s.bundle`);
old is a linked worktree (`.git` file) of
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache`, whose remotes
are the user's GitHub fork and upstream.

## Categorized inventory

The Git-native inventory below includes tracked files plus nonignored
untracked files, and compares file bytes (not filesystem mtimes or ordinary
permission bits).

| Category | Evidence | Required migration action |
|---|---|---|
| Identical | 8,563 common files are byte-identical; this includes all four root handoff files (`AGENTS.md`, `CODEX_DPRIME_STATIC_REVIEW.md`, `CODEX_HANDOFF.md`, `HANDOFF-G3-2026-09-07.md`) and all five old modified source/test paths | No copy/sync. Preserve current copies. Their SHA-256 values are recorded below. |
| Old-only, nonignored | None (`old=8,564`, `current=8,601`, common=`8,564`) | No action. There is no old authored file absent from current. |
| Current-only, nonignored | 37 files, all under `.memory/g3-baseline-20260907/` (ledger/context/plan/handoff and work evidence) | Preserve as current task-state; do not replace from old. These are not present in old. The audit file itself is created after this inventory and is an additional current-only report artifact. |
| Divergent | `python/sglang/benchmark/serving.py` | Keep current content. Do not copy old over it: current has the GGUF single-file tokenizer guard; old has the unmodified baseline. If the patch must be retained beyond this tree, archive/commit it independently before deletion. |
| Symlinks | Three common symlinks have identical targets: `.dockerignore -> .gitignore`, `python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format -> ../../../kernels/aot/.clang-format`, `sgl-model-gateway/LICENSE -> ../LICENSE` | No action. |

### Old ignored-only files (excluded from sync)

The old tree has 83 files that are not visible to ordinary `git status`:

- 18 under `.ruff_cache/**` (including `.ruff_cache/.gitignore` and
  `CACHEDIR.TAG`);
- 65 `**/__pycache__/*.pyc` files.

These are disposable linter/interpreter caches, not source or experiment
evidence. Do not sync them. They may be discarded with the retirement tree
after checking that no running process depends on the directory. The current
tree has five unrelated ignored `__pycache__` files and one ignored
`.memory/g3-baseline-20260907/work/G3-RUNNER-OOM-FIX-local-guard-verify.out`;
these are also not migration inputs.

### Old modified paths

Old has five unstaged modified paths:

```text
python/sglang/srt/entrypoints/openai/protocol.py
python/sglang/srt/entrypoints/openai/serving_chat.py
python/sglang/srt/entrypoints/openai/serving_completions.py
python/sglang/srt/sampling/custom_logit_processor.py
test/registered/unit/sampling/test_custom_logit_processor.py
```

Each is byte-identical to current; no synchronization is needed. Current has
those same five modifications plus the divergent `python/sglang/benchmark/serving.py`.
Neither tree has staged changes.

### Current task-state and credential boundary

The current-only `.memory/g3-baseline-20260907/` contains 37 nonignored files
and is the only task-state directory in either compared tree. Its evidence
includes the frozen protocol, G3 runbooks, baseline reports, remote audit,
source audit, and local patch snapshots. The current local snapshot
`.memory/g3-baseline-20260907/work/G3-RUNNER-OOM-FIX-serving.py.patched.local`
has the same SHA-256 as current `python/sglang/benchmark/serving.py`.

`.memory/g3-baseline-20260907/work/G3-SSH-KEY-20260907.md` is a likely
credential-related artifact by name. Metadata only: regular file, mode 600,
309 bytes, owned by `dev-codex:dev-codex`; its contents were intentionally not
printed. Preserve it confidentially in current and do not copy, expose, or
delete it as part of this migration without a separate decision.

## Divergence evidence and hashes

Selected SHA-256 evidence:

| Path | old SHA-256 | current SHA-256 | Result |
|---|---|---|---|
| `protocol.py` | `5ef8e76a3038aab3ac3be807d563aa8fd82ef7b27a417b1556f69e2dd6427970` | same | identical |
| `serving_chat.py` | `e4b1cbcf57695acd1cd78825519b90e99e944890bd467ac528f059d360285fd1` | same | identical |
| `serving_completions.py` | `b62a90747bd37750449a1b46cb7216a589307b6bcec45f2df6e50cf680275165` | same | identical |
| `custom_logit_processor.py` | `97b07a12a56c3d24460d20a113f1851b312b8a2542dc1ca4c40cec36f2427e8a` | same | identical |
| `test_custom_logit_processor.py` | `e45caa39245001c0dfbe8c2945554244df92147b3b8845e6b1b3e7b2b55cc955` | same | identical |
| `python/sglang/benchmark/serving.py` | `0d65ec5e4490eaf5bc999cd11f045688b05ff6a040b6fabc4e5e60faf134e574` | `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb` | divergent |

The only source divergence is a 15-line current-only guard in
`check_chat_template`: for a single GGUF file it checks tokenizer sidecars,
uses the parent directory, and returns false rather than asking
`AutoTokenizer` to parse the GGUF. This is a current safety/performance patch;
overwriting it with old would regress the established OOM mitigation.

The four common root handoff files are also byte-identical. Their hashes are:

```text
AGENTS.md                         02858b9f97c686f4f847d4b170f00e81bd447a921b696a09a8b03d6a0b4113db
CODEX_DPRIME_STATIC_REVIEW.md    f772b2112063d842dd5ce3077c4db061a33a6cc2e2e3bd3278e19d419ee907dd
CODEX_HANDOFF.md                  2093ea124e17eb010072363054836da47167ff2a37138b460b6900da901bff97
HANDOFF-G3-2026-09-07.md          86bfbdc331ab9a102b9c34078beab3c13333b2cd8669d379084a93f1d8458afc
```

## Worktree-registration blocker and safe retirement method

`git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache worktree list --porcelain`
still registers old as:

```text
worktree /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
HEAD dac6db1ebabdb80209b757fd063cf53e05c091e7
branch refs/heads/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
```

The old `.git` pointer resolves to
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.git/worktrees/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`.
The old worktree is dirty (five tracked modifications and four common
untracked handoff files), so a normal `git worktree remove` will refuse until
those files are dealt with. Directly removing the directory would leave stale
registration metadata and is not safe.

The main `sglang-3090-24g-hicache` repository is itself dirty and ahead of its
remote by two commits, with its own untracked `.memory/` and five `3090-dev/*`
scripts. Those files are outside old and must not be touched during retirement.

Recommended sequence, after user confirmation of the destructive step:

1. Keep current's five shared source/test modifications and current
   `benchmark/serving.py` patch. No file synchronization from old is required.
2. Preserve current `.memory/g3-baseline-20260907/`, especially the mode-600
   SSH-key-named artifact. The four old handoff files already exist byte-for-byte
   in current; do not copy them again.
3. Confirm no old worktree process is active. If the old dirty files are
   intentionally retired because their identical copies are already current,
   use the linked-worktree-aware removal from the main repository, with force
   only after the above preservation check:

   Preferred first attempt (preserves refusal on dirty data):

   ```text
   git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache \
     worktree remove \
     /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
   ```

   Only after explicit acceptance of discarding the old dirty copy:

   ```text
   git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache \
     worktree remove --force \
     /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
   ```

   Omitting `--force` is preferred; it will expose any remaining dirty data.
   `--force` discards the old worktree's uncommitted copy and must not be used
   until the user accepts that loss. Do not run `rm -rf` or broad cleanup.
4. Verify the old path is absent and `git worktree list --porcelain` no longer
   lists it. Keep the main repository's branch ref unless the user separately
   decides to retire that ref; current is a separate clone and already retains
   the same commit on its own branch.

## Open issues and decisions

- **Blocking for unattended deletion:** old is a registered, dirty linked
  worktree. A user must approve disposition of its uncommitted files before a
  forced worktree removal.
- Decide whether the old branch ref in the `sglang-3090-24g-hicache` repository
  should remain as a backup after worktree removal. It is not needed for current
  source continuity but is separate Git state.
- Current's remote is a local bundle rather than old's GitHub remotes. This does
  not block deleting old, but future fetch/push behavior must be configured
  independently if required.

## Evidence commands

Key commands run read-only:

```text
git show -s --format='%H %T %P %s' HEAD
git merge-base HEAD origin/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s
git status --porcelain=v1 --untracked-files=all
git diff --name-status <old-HEAD> <current-HEAD>
git worktree list --porcelain
git ls-files; git ls-files --others --exclude-standard
cmp -s <old>/<path> <current>/<path>
sha256sum <modified-or-untracked-path>
```

Final audit status: **done**. No sync, deletion, Git mutation, remote access,
or benchmark action was performed.
