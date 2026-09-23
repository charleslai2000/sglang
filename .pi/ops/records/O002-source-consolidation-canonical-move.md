# O002 — 3090 source consolidation and canonical relocation

Date: 2026-09-23

## Authority

- Canonical source remains branch `3090-24g-opt`, HEAD before this record `772213e529bdd740e1faf58dee6e9f670809d24d`.
- Existing C3/C4/C5/C6 source-authority conclusions were reused, not re-audited: HiCache source and IQ3 source are already in the canonical branch; rescue/task source was absorbed; `/opt` has no unique required source; Falcon remains separate.
- Graph ancestry: `3090-iq3` is an ancestor of canonical. `3090-24g-hicache` diverges at `42693d23bd780a2e21b16dcc8681e0d5156c82f1`, with canonical adding C4/C5/C6 documentation/control and no outstanding required runtime/tool delta per prior audit. The old branch diff against HEAD consists of historical control/evidence deletions, not an identified unabsorbed executable-source payload.

## Actions

- Reverted the uncommitted `inspect_storage_key` implementation/test and removed all uncommitted C6.4R V2/V3 observer scripts. No experiment observer entered production code.
- Created archive tags before deleting branch/worktree refs:
  - `archive/3090-24g-hicache-8b77390` → `8b77390fd5a155e0af5f16e96c52641de338ec65`
  - `archive/3090-iq3-ad63118` → `ad63118354829f995b733ed0f5048caf8cda912e`
  - `archive/rescue-tmp-artifacts-20260917-0728adf` → `0728adf5d2220c165126882c46bd71c05eeece1f`
  - `archive/task-src-authority-20260917-206db3c` → `206db3c30e0b6c2ca5987ef0288e3aa6a4f07117`
  - `archive/iq3-pr-worktree-4c3e4c2` → `4c3e4c2350f4d6c4ff2a785e9b294938766a3cc6`
  - `archive/3090-opt-frozen-ec80842` → `ec8084207a548c1be36573797f81cc4fc6f73567`
- Removed the detached IQ3 PR worktree, frozen worktree, IQ3 worktree, and local branches `3090-24g-hicache`, `3090-iq3`, `rescue/tmp-artifacts-20260917`, `task/src-authority-20260917`.
- Canonical worktree is now at `/home/ubuntu/workspaces/3rdparty/sglang`, branch `3090-24g-opt`, same pre-record HEAD. Git worktree metadata reports that path as the branch worktree.
- M3/M4 local-prod envelope `src` symlinks now resolve to `/home/ubuntu/workspaces/3rdparty/sglang`; service and deployment source defaults were updated accordingly.
- `/opt/sglang/opencodex-provider-2d4e33a832` is an exported deploy source tree, and the DEV provider explicitly uses it as its fail-closed runtime artifact; it was preserved. Scripts can re-export pinned source from canonical Git but need local build artifacts/sudo, so no re-export was attempted. Preserved `/opt/sglang/opencodex-provider-run` logs/state and all local-prod exports/venv links.
- Kept all NInfer repositories untouched. Kept `sglang-falcon-h1-7b` and branch `falcon-h1-7b` intact.
- Did not push upstream or alter `main`.

## Final verification

- Static `bash -n` for deployment/smoke/recovery entry scripts, Python `py_compile` for sampled harness, and `git diff --check`: PASS.
- Final commit and `origin/3090-24g-opt` push are recorded by the commit that contains this result.
- `main` and upstream were not modified.
