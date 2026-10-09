# P0-A-FIX-20260911-R4

- **工作标题：** P0-A-FIX-20260911-R4
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-A-FIX-20260911-R4.md`：**
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore_scheduler_feed.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-A-FIX-20260911-R4.md
evidence:
dispatch:
task_id: P0-A-FIX-20260911-R4

## 实际改了什么
仅修改三个获准测试文件：`test_ready_horizon_unit.py`、`test_prefetch_budget_split_unit.py`、`test_hicache_restore_scheduler_feed.py`。适配 typed `PrefetchIssueResult`/status、release epoch 与 `origin=` API、rh_stage.v2 telemetry、真实 cleanup fixture state，并调整 HOST_ALLOC oracle 反映 alloc→evict_host→alloc retry。未改任何产品源码、Git state 或远端/服务。

## 生成结果与验收
三文件 py_compile/compileall、AST/contract-string 与 scoped diff-check 通过；diff 恰为三测试文件 157 insertions/14 deletions。目标单测无法在本地运行（依赖环境缺失，导入 KeyError `sglang`；pytest/torch/msgspec 等不可用），formatter/typecheck 工具也缺失。因此本任务 done 只代表 test-only fixture/API 修订与静态验收；P0-A 仍 NOT VERIFIED，需在 dependency-complete environment 跑 focused/full suites，不得冒称远端通过。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-FIX-20260911-R4.md` → `.memory/rh-p0a-budget-residency/P0-A-FIX-20260911-R4.md`; SHA256 `ce15327d25dcfa03991c96fdd18b409a4e8e533a5b429f25f678caaabce64239`; source state `tracked`
