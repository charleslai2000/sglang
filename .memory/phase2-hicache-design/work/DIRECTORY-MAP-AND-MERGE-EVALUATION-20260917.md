# Directory / lineage map — verified 2026-09-17 09:20Z

## My working directory
`/home/ubuntu/workspaces/3rdparty` (the orchestrator's cwd).
Its ONLY child is `sglang-3090-24g-opt/` — the git repo.

## Three distinct trees (this was the confusion)

### 1. REPO (dev branch) — MINE
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`  (git repo)
- branch `3090-24g-opt` @ `ad749d6f28`
- **72 uncommitted entries**: 8 modified tracked files (+1745/-82) + untracked `.memory/` docs
- This is a DEV tree. Its working tree is NOT the production source.

### 2. FROZEN PRODUCTION ARTIFACTS — MINE (in /opt, not in repo)
`/opt/sglang/local-prod-v1`          LOCAL-PROD-BASELINE-v1 (frozen, never unfreeze)
`/opt/sglang/local-prod-v1.1-candidate` LOCAL-PROD-v1.1  digest f0ca9206...97ab7
`/opt/sglang/local-prod-v1.1.2-candidate` LOCAL-PROD-v1.1.2 digest cf32a429...44e5  (created today)
Layout: `src/` + `launcher/` + `manifest/` + `tools/` + `env -> /home/ubuntu/venvs/sglang-3090`

### 3. OTHER (not mine, do not touch)
`/home/ubuntu/sglang`                          an Aug-29 upstream checkout (HEAD 71de97b, 2026-08-20)
`/home/ubuntu/workspaces/local-prod-baseline-v1/testlib`   a pytest vendored dir (NO .git, not a sglang tree)
`/home/ubuntu/{models,sglang-run,venv,venvs,wheels,build-aot,fc-src,sglang-install-logs}`  pre-existing host dirs

Home dir also has stray files NOT mine: `SGLANG-ENV.md`, `SGLANG-TASK-BRIEF.md`(+2 .bak), `build.log`,
cuda-keyring deb. I created none of these.

## CRITICAL: the editable-install landmine (CONFIRMED by reading the finder)
`/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/__editable___sglang_*_finder.py`
maps `sglang` -> **`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang`** (the REPO).
Every frozen tree's `env` symlinks to this same venv. So **without explicit PYTHONPATH, `import sglang`
loads the repo working tree, not the frozen tree.** This is exactly why every gate now hard-asserts
`sglang.__file__`.

## LINEAGE (the decisive finding): four DIFFERENT extent_file_backend.py

| tree | lines | wal_fix hits | optionC |
|---|---:|---:|---:|
| origin/3090-24g-hicache | 2153 | 3 | 0 |
| **repo working tree** | 2313 | **3** | 0 |
| frozen v1.1 | 2316 | **4** | 0 |
| frozen v1.1.2 | 2490 | 4 | 1 |

* The **repo working tree is a pre-fix (older) lineage**: it has the WAL fix at 3 sites but is MISSING
  the 4th fix site (`extent_file_backend.py:2163`, inside `checkpoint()`), which frozen v1.1 HAS.
  => the repo working tree is a STALE copy relative to production (matches the earlier "stale WIP" finding).
* `origin/3090-24g-hicache` is **even older**: 2153 lines, 3 wal_fix hits, no Option-C.
* Repo working tree matches frozen v1.1.2 on 6 of the 8 WIP files (environ, output_streamer,
  tokenizer_manager, unified_radix_cache, hicache_telemetry, test_hicache_request_telemetry) and
  **differs** on exactly the 2 that matter: `extent_file_backend.py` (no Option-C, missing 4th WAL fix)
  and `test_extent_file_backend_unit.py`.

## BRANCH TOPOLOGY
* `3090-24g-opt` (local/current) @ ad749d6f28
* `origin/3090-24g-hicache` @ 560f9ad525 "Merge branch 3090-24g-opt into 3090-24g-hicache"
* divergence: `rev-list --left-right --count hicache...opt` = **3 / 6**
  - hicache-only 3: `560f9ad525` (merge), `0a725c6385` + `5a76070743` (**both DOCS ONLY**: 3090-dev
    handover-22151.md, prod-deploy-issues.md, relaunch-e1.sh)
  - opt-only 6: 4 docs(memory), 1 test(extent-g1), **1 `a207b567fe wip(p0-telemetry): UNREVIEWED snapshot`**
* `origin/main` vs hicache: `0 / 181` -> hicache is 181 commits ahead of main, main has none unique.

## MERGE CONSEQUENCE (owner asked to evaluate)
Merging the repo/dev branch into `hicache` would carry:
1. **`a207b567fe` — explicitly labelled UNREVIEWED** telemetry code (17 files). Merging it into the
   production integration branch would put unreviewed code on the production lineage.
2. The 72 uncommitted working-tree changes, of which **`extent_file_backend.py` is a STALE pre-fix
   version** (missing the 4th WAL fix site at :2163 and without Option-C). Committing/merging these would
   REGRESS the WAL checkpoint fix that the frozen production identity already contains.
3. It would NOT bring in the Option-C fix at all (repo working tree has optionC=0).
=> A naive `merge 3090-24g-opt -> hicache` is a **regression risk**, not a consolidation.
The production truth is the FROZEN TREE, not the repo working tree.
