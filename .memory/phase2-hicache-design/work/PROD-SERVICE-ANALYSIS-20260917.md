# Branch topology, merge plan, and service scaffold — evidence record

Task: `branch-merge-and-service-scaffold-20260917`
Repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`
Date: 2026-09-17 (UTC)

This file records the verified facts, the corrections to the dispatch brief, the
merge plan, and the explicit do-not-execute list. The service scaffold itself is
documented in `README.md`.

---

## 1. Verified branch topology

All commands run read-only. Full output in the task transcript.

```
$ git rev-parse HEAD
ad749d6f283b7d6c59a8df928304325eda90e98b

$ git for-each-ref --format='%(refname) %(objectname:short) %(committerdate:iso) %(subject)' \
    refs/heads refs/remotes/origin/3090-24g-opt refs/remotes/origin/3090-24g-hicache \
    refs/remotes/origin/main refs/remotes/upstream/main
refs/heads/3090-24g-opt                 ad749d6f28 2026-09-16 04:33:42 +0800 docs(memory): commit-time state, ...
refs/heads/main                         5263568bcb 2026-08-27 01:30:38 +0800 [HiCache] Keep auxiliary load-back ...
refs/remotes/origin/3090-24g-hicache    560f9ad525 2026-09-16 04:14:17 +0800 Merge branch '3090-24g-opt' into ...
refs/remotes/origin/3090-24g-opt        ad749d6f28 2026-09-16 04:33:42 +0800 docs(memory): commit-time state, ...
refs/remotes/origin/main                5263568bcb 2026-08-27 01:30:38 +0800 [HiCache] Keep auxiliary load-back ...
refs/remotes/upstream/main              24874f90a3 2026-09-15 12:40:28 -0700 [Test] Fix DeepGEMM batch invariance ...

$ git rev-list --left-right --count origin/3090-24g-hicache...3090-24g-opt
3	6

$ git merge-base 3090-24g-opt origin/3090-24g-hicache
34bd2ed49f2b2e6fef504019bfe3840eb30ac061

$ git log -1 --format='%H %P %s' 560f9ad525
560f9ad5256ad95b8075f474a679918340fcca47 0a725c6385805f21138111e09bf69464ec29f1dc \
  34bd2ed49f2b2e6fef504019bfe3840eb30ac061 Merge branch '3090-24g-opt' into 3090-24g-hicache

$ git merge-base --is-ancestor origin/3090-24g-opt origin/3090-24g-hicache ; echo $?   -> 1 (NO)
$ git merge-base --is-ancestor origin/3090-24g-hicache 3090-24g-opt ; echo $?           -> 1 (NO)

$ git merge-base origin/main 3090-24g-opt
5263568bcbf9da7b463e25c136f6aa92eedc3c08          # == origin/main tip
$ git rev-list --left-right --count 3090-24g-opt...origin/main      -> 184  0
$ git rev-list --left-right --count origin/3090-24g-hicache...origin/main -> 181  0
```

### Corrections to the dispatch brief

| brief said | verified |
|---|---|
| current branch `3090-24g-opt`, tip `ad749d6f28` | **correct** |
| `origin/3090-24g-hicache` tip `560f9ad525` | **correct** |
| left-right = 3 / 6, merge-base `34bd2ed49f` | **correct** |
| hicache-only = `560f9ad525`, `0a725c6385`, `5a76070743` | **correct** |
| 6 opt-only commits listed | **correct** |
| working tree 72 entries, 8 modified (+1745/-82) | **correct at task start**; a 73rd untracked `.memory/` doc (`DIRECTORY-MAP-AND-MERGE-EVALUATION-20260917.md`, mtime 09:43:24Z) was created by a **different agent**, not by this task. This task wrote nothing into the repo. |
| workspace `extent_allocator.py` == frozen v1.1 (`285df97c01da`) | **correct** (also == v1.1.2? **NO** — v1.1.2 is `fdbd9e4965b5`) |
| workspace `extent_file_backend.py` == `030487eebc58`, differs from v1.1 (`fbd19f10e669`) and v1.1.2 (`b284ec2a710d`) | **correct** |
| workspace has 0 Option-C relocation symbols | **correct** (v1.1.2 has 6) |
| frozen digests `f0ca9206…97ab7` (v1.1) / `cf32a429…44e5` (v1.1.2) | **correct**, independently recomputed |
| v1.1.2 launcher sha `6e57bc57…6ba4` | **correct** |

### New facts not in the brief

1. **`origin/3090-24g-opt` is the repository's DEFAULT branch.** The ledger
   (`ledger.md:7350`) records the owner changing `charleslai2000/sglang`'s
   default branch from `main` to `3090-24g-opt` on 2026-09-16. Fresh clones now
   check out `3090-24g-opt`.
2. **A `wip/p0-telemetry-current-17` ref exists on `origin` and points at the
   same commit as `3090-24g-opt`** (`ad749d6f28`). It is a *naming* snapshot, not
   a separate lineage.
3. **The `checkpoint/pre-v0.5.19-20260913` protected refs do NOT exist.**
   `.memory` documents them as protected (`refs/heads/checkpoint/...` + tag), but
   neither local refs nor `git ls-remote origin` contain them. Commit `993ef8e5`
   is reachable only from the 3090-24g line. This is a **documentation/reality
   mismatch** worth flagging: a documented rollback ref does not exist on the
   remote.
4. **`origin/main` is a strict ancestor of `upstream/main`** and has **no**
   `.memory`. `.memory` exists only on the 3090-24g branches (opt 421 files,
   hicache 393 files, main 0).
5. **`3090-dev/` is NOT hicache-only.** Both branches contain it; hicache adds
   exactly 4 files on top of opt (`README.md`, `handover-22151.md`,
   `prod-deploy-issues.md`, `prod-deploy/relaunch-e1.sh`).
6. **The frozen `/opt` trees are newer than the repo.** v1.1.2's
   `extent_file_backend.py` is `b284ec2a710d`, which is neither the workspace
   byte nor the v1.1 byte. The repo does **not** contain the frozen v1.1.2
   Option-C bytes.

---

## 2. Intended role of each branch (evidence-based)

### `main` @ `5263568b` — upstream sync line
Evidence: no `.memory`, is a strict ancestor of `upstream/main`; the handoff
(`HANDOFF-20260914` §11.3) states "`main` 未删除、未改动（仍 `5263568b`）". It is
the untouched upstream mirror, not a working branch.

### `3090-24g-opt` @ `ad749d6f28` — **the working / development branch, and the
GitHub default branch**
Evidence:
* `WORK-INVENTORY-20260914` §1: *"branch `3090-24g-opt`（working branch；后续工作在此展开）"*.
* `HANDOFF-20260914` §11.4: *"`3090-24g-opt` 工作分支/默认"*.
* `ledger.md:7350`: default branch changed `main` → `3090-24g-opt`.
* `context.md` banner: *"本 repo 现在的 working branch 是 `3090-24g-opt`"*.
* It carries the current product work: the loader shim (`48233f3aba`), the
  UNREVIEWED telemetry snapshot (`a207b567fe`), vendored evidence
  (`ce73d6671f`), and 421 `.memory` files.

### `3090-24g-hicache` @ `560f9ad525` — **the archive / superset branch, NOT the
production branch**
Evidence:
* `HANDOFF-20260914` §11.4 table: *"`3090-24g-hicache` 超集归档分支 = 合并
  `3090-24g-opt`；含 `3090-dev/`22151 部署文档"*.
* `WORK-INVENTORY-20260914` §1: *"`superset archive branch`"*.
* `ledger.md:7264`: *"约定后续 merge 方向为 **opt → hicache**"*.
* Its only unique content is 3 commits: 2 documentation commits about a
  **different physical host** (`22151`, port 8024, `/data/l3/hicache-prod`,
  conda `sglang-patch`) plus the merge commit that brought `opt` into it.
* `3090-dev/README.md` line 3 explicitly says it is *"随冻结基线分支
  `3090-24g-hicache` 提交"* — i.e. it is the archive for reproducible experiment
  scripts of the 3090-24g line.

**Therefore the owner's belief that `3090-24g-hicache` is the production /
integration branch is only half right.** It is the *archive/integration target*
for the `opt` line, but it is **not** where production source lives: the actual
frozen production artifacts live in `/opt/sglang/**` (outside git), and the
active development branch is `3090-24g-opt`. The two 22151 docs describe an
entirely separate deployment on a different machine.

### Frozen production artifacts (not in git at all)
| tree | identity | digest | notes |
|---|---|---|---|
| `/opt/sglang/local-prod-v1` | LOCAL-PROD-BASELINE-v1 | (no TREE-SHA256.txt) | frozen, never unfreeze |
| `/opt/sglang/local-prod-v1.1-candidate` | LOCAL-PROD-v1.1 | `f0ca9206…97ab7` | launcher has **no** identity gate |
| `/opt/sglang/local-prod-v1.1.2-candidate` | LOCAL-PROD-v1.1.2 | `cf32a429…44e5` | launcher **has** the fail-closed gate |

---

## 3. Merge plan

> **DO NOT EXECUTE.** This is a plan only. No merge, commit, push, rebase, stash,
> or branch creation/deletion was performed.

### 3.1 Commit-level classification

**hicache-only (3 commits) — all docs-only, all safe to keep as-is**

| commit | content | mergeable? |
|---|---|---|
| `5a76070743` | `3090-dev/{README.md, prod-deploy-issues.md, prod-deploy/relaunch-e1.sh}` | yes (docs/scripts for host 22151) |
| `0a725c6385` | `3090-dev/handover-22151.md` | yes (docs) |
| `560f9ad525` | merge commit | structural |

Verified docs-only: `git diff --name-only 34bd2ed49f origin/3090-24g-hicache`
returns exactly those 4 paths.

**opt-only (6 commits)**

| commit | content | verdict |
|---|---|---|
| `1352a69997` | docs(memory) branch consolidation | **docs-only** → mergeable |
| `ce73d6671f` | docs(memory) vendored P0 evidence (28 files) | **docs-only** → mergeable |
| `48233f3aba` | `fix(qwen3_5_text)` loader shim | **reviewed + GPU-validated** (`APPROVED_FOR_GPU_VALIDATION`, 1170/1170 tensors) → mergeable |
| `1dcaa80473` | `test(extent-g1)` KV+Mamba grouped fixture | **test-only**, pre-existing authorized → mergeable |
| `ad749d6f28` | docs(memory) commit-time state | **docs-only** → mergeable |
| `a207b567fe` | `wip(p0-telemetry)` 15 files | **⛔ BLOCKING: UNREVIEWED** |

#### ⛔ BLOCKING FINDING — `a207b567fe` must NOT enter the production branch

The commit message itself states `STATUS: not accepted`, terminal review
`CHANGES_REQUIRED`, **3 defects open** (2 HIGH, 1 MED), and explicitly:

> "Do NOT treat as reviewed. Do NOT unlock telemetry-enabled performance reruns,
> cache/agent matrix, soak/restart, scorecard freeze or B4 from this."

`WORK-INVENTORY-20260914` §4 repeats the warning and the convention:

> "**约定**：不要把这些未审字节合并进冻结基线。"

**Consequence:** merging `3090-24g-opt` into any production branch as-is would
carry 15 unreviewed source files (`scheduler.py`, `metrics_collector.py`,
`unified_radix_cache.py`, `hicache_telemetry.py`, …) into that branch. This is
the single hard blocker for the merge. Any merge must either (a) be a
**cherry-pick of only the 5 reviewed/docs commits**, or (b) wait for the P0
telemetry remediation + independent terminal review.

### 3.2 Direction: neither a plain FF nor a plain merge is safe

| option | command | reversible? | risk |
|---|---|---|---|
| A. FF hicache from opt | `git push origin 3090-24g-opt:3090-24g-hicache` (FF) | **yes** — reflog + old sha | **HIGH**: would overwrite the 3 hicache-only commits' tip and, if done as a merge instead, would pull `a207b567fe` into the archive branch. Also the archive would lose the 22151 docs unless re-merged. |
| B. merge opt → hicache | `git switch 3090-24g-hicache && git merge 3090-24g-opt` | yes (merge commit; `git reset --hard` before push) | **HIGH**: imports `a207b567fe`'s 15 unreviewed files into the archive branch. |
| C. cherry-pick the 5 clean commits onto hicache | `git switch -c tmp origin/3090-24g-hicache && git cherry-pick 1352a69997 ce73d6671f 48233f3aba 1dcaa80473 ad749d6f28` | yes (temp branch; delete on failure) | **LOW** — docs + one reviewed fix + one test-only change; no unreviewed product code. Recommended if the archive must advance now. |
| D. **do nothing to hicache** (recommended default) | — | n/a | **NONE**. The archive already contains all production source up to `34bd2ed49f`; the 6 opt-only commits are either docs or pending review. There is no functional need to advance hicache. |

**Recommendation: option D now, option C only if the owner wants the archive to
carry the loader-shim fix immediately. Never option A or B while
`a207b567fe` is unreviewed.**

### 3.3 The 73 working-tree changes — classification

`git diff --shortstat` = **8 files changed, +1745 / -82**. Untracked: 63
`.memory/` docs + 2 non-memory files.

#### Correction to the brief: the worktree is NOT the pre-review snapshot

The brief implies the uncommitted changes are the same bytes as `a207b567fe`
(the "17-file unreviewed identity"). **That is wrong, and the distinction is
material.** Verified by sha256: `a207b567fe`'s committed bytes are the
**pre-review** `CHANGES_REQUIRED` snapshot, while the **worktree** bytes are the
**post-review** bytes — all six hashes frozen in
`RESUME-HANDOFF-20260916.md` §1.1 (verdict `PASS_FOR_CURRENT_BYTES`) match the
worktree exactly.

| file | worktree | `a207b567fe` (committed) | frozen v1.1.2 |
|---|---|---|---|
| `observability/hicache_telemetry.py` | `788318d91dc4` | `5f433f8479f1` | `788318d91dc4` |
| `mem_cache/unified_radix_cache.py` | `5b5dc29fa21e` | `86117ad1736e` | `5b5dc29fa21e` |
| `managers/tokenizer_manager.py` | `9f9d38028008` | `b3f92cc2879e` | `9f9d38028008` |
| `managers/scheduler_components/output_streamer.py` | `8485d9563e07` | `e92da3e43c2e` | `8485d9563e07` |
| `test/.../test_hicache_request_telemetry.py` | `e577d94086dd` | `10f8b58a473b` | `e577d94086dd` |
| `test/.../test_output_streamer_hicache_telemetry_wiring.py` | `717ac93c6a3b` | (untracked) | `717ac93c6a3b` |

**Consequence:** committing the worktree would *upgrade* `a207b567fe`'s
unreviewed bytes to the reviewed ones, but that is a consequential provenance
action requiring owner authority — not a merge step. The `extent_file_backend.py`
hybrid below still blocks a wholesale commit.

**6 of the 8 modified files are byte-identical to the frozen, REVIEWED v1.1.2
tree.**

| file | workspace | frozen v1.1.2 | classification |
|---|---|---|---|
| `observability/hicache_telemetry.py` | `788318d91dc4` | `788318d91dc4` | **reviewed P0 bytes** (matches `RESUME-HANDOFF` hash `788318d9…`) |
| `mem_cache/unified_radix_cache.py` | `5b5dc29fa21e` | `5b5dc29fa21e` | **reviewed P0 bytes** |
| `managers/tokenizer_manager.py` | `9f9d38028008` | `9f9d38028008` | **reviewed P0 bytes** |
| `managers/scheduler_components/output_streamer.py` | `8485d9563e07` | `8485d9563e07` | **reviewed P0 bytes** |
| `test/.../test_hicache_request_telemetry.py` | `e577d94086dd` | `e577d94086dd` | **reviewed test bytes** |
| `test/.../test_output_streamer_hicache_telemetry_wiring.py` (untracked) | `717ac93c6a3b` | `717ac93c6a3b` | **reviewed test bytes** |
| `srt/environ.py` | `e49571c1d653` | `e49571c1d653` | reviewed-ish; matches v1.1.2 |
| `extent/extent_file_backend.py` | `030487eebc58` | `b284ec2a710d` | **⛔ does NOT match any frozen tree** |
| `test/.../test_extent_file_backend_unit.py` | `71c13ad1cb5b` | `bb08e341d14c` | **⛔ does NOT match** |

So the working tree is **not** the pre-review P0 snapshot. It is the **post-review
P0 bytes** (`RESUME-HANDOFF-20260916` §1.1 frozen 6 hashes all match) **plus** a
WAL-sequence fix in `extent_file_backend.py` that matches **v1.1 but not
v1.1.2**.

Precisely: the workspace `extent_file_backend.py` = v1.1.2's Option-C code
**minus** the Option-C relocation block (182 diff lines) **plus** the v1.1
WAL-watermark 3-line hunk (`self._wal_recovered_next_seq = self._wal_next_seq`
after `_wal_next_seq = state.checkpoint_lsn + 1`). It is a **hybrid that exists
in no frozen tree.**

| class | files | safe to commit? |
|---|---|---|
| **reviewed P0 telemetry bytes** | 6 files + `environ.py` | yes, **if** the owner confirms the RESUME-HANDOFF `PASS_FOR_CURRENT_BYTES` verdict still stands for these exact hashes |
| **unfrozen WAL-fix hybrid** | `extent_file_backend.py`, `test_extent_file_backend_unit.py` | **NO — must not be committed without an explicit provenance decision.** It is neither v1.1 nor v1.1.2 nor the pre-review snapshot. |
| **memory docs** | 63 untracked `.memory/**` | committing is a docs-only action; not required by this task |
| **scorecard tool** | `tools/production_performance_scorecard_v0.py` | unreviewed new tool; not required |

**Do NOT commit or stash any of these.** They were left byte-for-byte untouched.

### 3.4 Explicit "do not execute" list

```
DO NOT:
  git merge / git pull / git rebase        (either direction, either branch)
  git commit / git add / git stash / git clean
  git push / git push --force / git push --delete
  git branch -d/-D / git switch / git checkout (of any ref)
  git cherry-pick                          (until the owner approves option C)
  git reset --hard / git restore
  any modification of /opt/sglang/**       (frozen, read-only)
  any modification of /data/l3/**          (shared stores are never cleared)
  any modification of /var/log/** evidence
  any deletion of .memory/** docs
```

The reason `a207b567fe` is blocking is not stylistic: it carries **unreviewed
source** whose own review recorded 2 HIGH defects (a mismatched proof can yield
`outcome=complete`; hybrid component-complete authority not implemented). Mixing
it into the archive/production branch would make the archive's tip
indistinguishable from reviewed work.

---

## 4. Incidents during this task (disclosed)

1. **A scratch flock test wrote to the canonical lock path.** `service.env`
   originally allowed the environment to override `GPU_LOCK`, so a test
   intended for a scratch file used `/tmp/opencode/gpu-3090.lock`. The flock was
   acquired and released within the test; **no incumbent was signalled and no
   server existed at that time**. The lock file's *content* was left naming the
   test owner, so it was restored to an honest `state=free` record. Verified
   afterwards: the lock is **not held** (`{"held": false}`), no stray processes,
   GPU 1 MiB / 0 %, ports free.
   Root cause fixed: `GPU_LOCK` is now **not overridable**; isolated testing
   requires `GPU_LOCK_FOR_TESTS` and is restricted to the scaffold scratch root.
2. **A 73rd untracked file appeared in the repo** during the task
   (`DIRECTORY-MAP-AND-MERGE-EVALUATION-20260917.md`, mtime 09:43:24Z). It was
   authored by a **different agent**, not by this task. This task wrote nothing
   under the repo: `find . -newermt 09:18 -type f` outside `.memory/` returns
   empty.

---

## 5. Hard constraints honoured

* No server started. No port 30000/30164/30165 bound.
* No GPU lock held (only a bounded acquire/release test on an isolated scratch
  lock after the fix; the canonical lock was never held).
* No write to `/opt/sglang/**`, `/data/l3/**`, `/data/models/**`, or
  `/var/log/**` evidence.
* No irreversible git operation: no merge, commit, stash, rebase, push, branch
  creation or deletion. HEAD unchanged at `ad749d6f28`; stash list empty;
  reflog unchanged.
* Working tree left exactly as found (8 modified files, +1745/-82).
* Bulk scratch kept under `/tmp/opencode/prod-service-20260917/`.
