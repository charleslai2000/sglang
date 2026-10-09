# phase2-hicache-design-task-manager-e1

- **工作标题：** phase2-hicache-design-task-manager-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
为 P2-0 HiCache scheduler baseline 制定可执行子任务计划，明确 11 项 DAG、并行批次与角色，预审 12 项指标可得性及缺口，并固定实验参数、证据结构与 epoch handoff。

## 实际改了什么
交付 `.memory/phase2-hicache-design/plan.md` 计划文档并完成计划自检；报告没有产品/引擎代码修改。将 slot refill gap、L3→H wait、device locked tokens、restore quota compressed 等不可直接观测项列为缺口/依赖，没有擅自加引擎埋点。

## 生成结果与验收
11 个子任务依赖图自检无环、三组批内并行文件域/运行资源无重叠，判据为可验证信号，参数与 engine-read-only 边界明确。该报告完成的是计划和自检，不代表下游 11 个子任务均执行或 baseline 已实测。多个关键信息仍待 orchestrator/user 确认，包括指标定义/回退、执行身份/root 写权限、冻结参数完整性、64 agents 是否硬目标及 payload suffix 复用策略。
- 子任务数：11（勘察 2 / 设计 2 / 实现 2 / 实验 3 / 分析 1 / 收口 1）。
- 依赖链：01,02 → 03,04 → 05,06 → 07 → 08 → 09 → 10 → 11（批内并行、批间串行）。
- 并行组：Batch1 {01,02} 勘察、Batch2 {03,04} 设计、Batch3 {05,06} 实现；
  07（K=1 基线 + K=8 试点）→ 08（K=16+32）→ 09（K=64，RAM 门控）→ 10（归因）→ 11（基线报告）。
- 角色分配：coder = 01/02（勘察）/ 05/06（工具脚本）；architect = 03/04（设计）/ 10（归因分析）/
  11（基线报告）；tester = 07/08/09（实验执行）。
- 关键风险（现有日志不可得的 4 项）：slot refill gap、L3→H wait、device locked tokens、
  restore quota compressed —— 已在计划"已核实的指标可得性"表与 Missing Information 1-4 明确标记；
  其中 slot refill gap 与 L3→H wait 若勘察/首跑实证仍不可得，登记为 P2-1 依赖（引擎埋点，
  超出 P2-0 边界，不得在本阶段执行）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-task-manager-e1.md`：- plan.md: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md`
- 交换目录依据：repo 含 `.claude/`（rules/ + skills/）= 项目根（ARTIFACTS v5.2，不查 .git）；
  `.memory/phase2-hicache-design/` 为 orchestrator 本次派发前 09:51 创建的脚手架（含空 work/），
  P2-0 计划按其落盘；期间 09:54 出现的 `fetched-hicache-upstream.md`（上游 HiCache 设计研究，
  P2-1/P2-2/P2-4 参照）已读入并折入 01/03/04 的 reference_files。

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `caeadcf492`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-task-manager-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-task-manager-e1.md`; SHA256 `bd77f090781c1d7972280f20aa2a1ee7b4d546086e0ebf6e9bf260a65a843f22`; source state `tracked`
