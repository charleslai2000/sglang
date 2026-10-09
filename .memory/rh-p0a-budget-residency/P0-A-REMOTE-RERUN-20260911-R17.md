status: blocked

artifacts:
- This report: `.memory/phase2-hicache-design/work/P0-A-REMOTE-RERUN-20260911-R17.md`

evidence:
- Invocation confirmed working directory `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- It then checked unrelated nonexistent paths (`python/sglang/srt/memory_pool.py`, `python/sglang/srt/budget_manager.py`, `test/srt/test_hicache_restore.py`) instead of the three explicitly authorized test paths.
- No SSH, backup, transfer, remote verification, or pytest was performed.

summary:
- R17 is an execution-procedure failure, not a P0-A test result. It must not change the P0-A classification beyond remaining NOT_VERIFIED.

followups:
- Fresh executor must use exactly these existing local paths and no inferred alternatives:
  `3090-dev/test_ready_horizon_unit.py`,
  `3090-dev/test_prefetch_budget_split_unit.py`,
  `3090-dev/test_hicache_restore_scheduler_feed.py`.
- Print `pwd`, `test -f`, and sha256sum for those exact paths before transfer.

open_issues:
- Remote corrected-source test result remains unknown.
