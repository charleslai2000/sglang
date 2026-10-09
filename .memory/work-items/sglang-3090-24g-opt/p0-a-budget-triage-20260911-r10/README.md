# P0-A-BUDGET-TRIAGE-20260911-R10

- **工作标题：** P0-A-BUDGET-TRIAGE-20260911-R10
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
只读分诊 R9 budget suite 的 12 项失败，判定是 P0-A budget/Ready Horizon 产品回归还是测试 fixture 与生产 API 不兼容，并提出最小安全的 test-only 修复。

## 实际改了什么
仅检查本地源码、测试 fixture、R9 报告/transcript、R4 triage 和当前 diff；没有重新跑测试、修改文件或接触远端/3090/3060 runtime。本 invocation 唯一写入是诊断报告。

## 生成结果与验收
将观察到的 12 failures 分类为 fixture/setup contract error：旧 `object.__new__` fixture 缺 `_t38c_request_contexts` 与 `_t38c_residency_lock`，错误发生在 budget assertions 前；并指出补齐后可能出现 `_BudgetController.prefetch()` 不接 `trace_context=` 的下一项 fixture failure。该诊断不证明修复后 budget 行为正确；报告提出只修改 fixture/stub 的最小方案，需新 executor 实施并重跑 focused/full suite。
### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-A-BUDGET-TRIAGE-20260911-R10.md`：- R9 report says the full budget file had `12 passed, 12 failed`; failures
  involve missing `_t38c_request_contexts` and `_t38c_residency_lock`.
  Source: `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.md`,
  lines 44-46 and 76-79.
- R9 transcript preserves all 12 IDs and tracebacks at lines 155-647.
- Current test fixture `_make_budget_cache()` creates its cache with
  `test_storage_regression._make_cache()` at
  `3090-dev/test_prefetch_budget_split_unit.py:157-190`.
- That legacy harness uses `object.__new__(UnifiedRadixCache)` and initializes
  neither `_t38c_request_contexts` nor `_t38c_residency_lock`; see
  `3090-dev/test_storage_regression.py:755-819`.…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-BUDGET-TRIAGE-20260911-R10.md` → `.memory/rh-p0a-budget-residency/P0-A-BUDGET-TRIAGE-20260911-R10.md`; SHA256 `ec5692301c8f2023195183b001a505c5bfaf046f2e09f28d3fadbdfbfc2e6913`; source state `tracked`
