# P0-B-ORACLE-REFREEZE-20260911-R111

- **工作标题：** P0-B-ORACLE-REFREEZE-20260911-R111
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-ORACLE-REFREEZE-20260911-R111.md`：**
- Task ID: `P0-B-ORACLE-REFREEZE-20260911-R111`
- Invocation: `ses-p0b-oracle-refreeze-r111-20260911` (fresh)
- Role: `coder`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
(HEAD `4f41f5bab562b99562f30c67540eb05344d13637`, intentionally dirty).
- Boundary: oracle/reducer + tests + contract doc only. **No product source

## 实际改了什么
新增 `.memory/phase2-hicache-design/work/R111-reducer/` package（reducer、tests、冻结 predicate 文档、README、manifest、R109 rerun/test outputs）；保留 R107 package byte-identical。只改 oracle/reducer、tests、contract docs；无产品源码、提交、server/GPU 变更。

## 生成结果与验收
重新冻结精确 11-predicate oracle，仅修改 predicate 6 `generation_transition`、predicate 8 `attempt_lineage` 及其依赖的 `negative_safety/repeated_retry` scope。理由是 R107 要求每个 pool 的完整 emitted generation edge chain，但 producer 有界采样、真实 R109 Mamba edges 缺失；新版以 park/grant cache instance 和完整 per-pool counters 严格递增作 deciding evidence，已采样 edges 只作一致性 corroboration，contradiction 仍 fail closed。R111 使用真实 R109 bundle 重跑（详报告输出），不含 live evidence。需后续独立语义审查；不得把规则修订/离线重判当作产品修复或 P0-B pass。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-ORACLE-REFREEZE-20260911-R111.md` → `.memory/rh-p0b-harness-durability/P0-B-ORACLE-REFREEZE-20260911-R111.md`; SHA256 `22bf83093c8842a78b1c1678b081f89e52de57861a52c5aec6a13fe3bc046dac`; source state `tracked`
