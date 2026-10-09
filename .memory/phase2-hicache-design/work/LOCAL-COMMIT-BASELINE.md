# Local commit baseline

## Original local commit

- Commit: `6abdbb61cc5576461de11e59d5e6fb3ad626ddb9` (`last rescued`)
- Parent / exact base commit: `560f9ad5256ad95b8075f474a679918340fcca47` (`Merge branch '3090-24g-opt' into 3090-24g-hicache`)
- The commit was created directly on that parent.

## Remote branch observed before rebase

- Remote: `origin` (`git@github.com:charleslai2000/sglang.git`)
- Branch: `3090-24g-hicache`
- Observed remote-tracking tip: `ec8084207a548c1be36573797f81cc4fc6f73567` (`Merge 3090-24g-opt (M3 correctness): 9e88a0ba72 + d637d258bb + 42693d23bd into 3090-24g-hicache`)
- At that point, local and remote had diverged: local was 1 commit ahead and 54 commits behind; common ancestor was `560f9ad5256ad95b8075f474a679918340fcca47`.

## Rebase performed

- Fetched `origin`, then rebased the local change onto `origin/3090-24g-hicache`.
- Rebased commit: `3acac4aae62e67ab7aba7d2c64744e3641840913` (same subject: `last rescued`); parent is `ec8084207a548c1be36573797f81cc4fc6f73567`.
- Original commit retained locally by `backup/3090-24g-hicache-before-rebase`.
- This records the baseline and rebase operation; it does not claim that the rebased commit has been pushed.
