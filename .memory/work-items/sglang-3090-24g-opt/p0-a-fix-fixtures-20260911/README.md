# P0-A-FIX-FIXTURES-20260911

- **工作标题：** P0-A-FIX-FIXTURES-20260911
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-A-FIX-FIXTURES-20260911.md`：**
artifacts:
- `3090-dev/test_ready_horizon_unit.py`
- `3090-dev/test_prefetch_budget_split_unit.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- This report: `.memory/phase2-hicache-design/work/P0-A-FIX-FIXTURES-20260911.md`
evidence:
- Inspected the pre-existing dirty diff before editing. Product files under `python/` were not modified by this task.
- Updated typed `PrefetchIssueResult` checks to assert the dataclass and its `status` (`ISSUED` / `SKIPPED_ACTIVE`) rather than compatibility enum aliases.

## 实际改了什么
修改三份 P0-A tests：`3090-dev/test_ready_horizon_unit.py`、`test_prefetch_budget_split_unit.py`、`test_hicache_restore_scheduler_feed.py`。同步 typed `PrefetchIssueResult`/`origin=` test doubles、ready-stage schema assertion、durable trace fixture context、`pop_host_alloc_failure` fixture，并修正 HOST_ALLOC wake 预期以匹配 alloc→evict_host→alloc retry contract；未改 `python/` 产品源码，先检查了既有 dirty diff。

## 生成结果与验收
解决 R3 识别的 17 项 stale/incomplete fixtures/assertions，保留测试意图；diff-check 与 py_compile 通过。Local pytest 因环境缺 `pytest` module 未运行；无 remote test。故这只是测试 fixture 修复，不声称运行时通过；follow-up 是按后续流程在授权 3060 跑 P0-A regression suite。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-FIX-FIXTURES-20260911.md` → `.memory/rh-p0a-budget-residency/P0-A-FIX-FIXTURES-20260911.md`; SHA256 `2f58f48c8ef8fa308f6d5fc4bfe342262beaba1f9ae6d1c68ebea4f72782f891`; source state `tracked`
