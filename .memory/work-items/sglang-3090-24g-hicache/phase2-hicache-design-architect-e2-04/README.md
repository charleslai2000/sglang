# phase2-hicache-design-architect-e2-04

- **工作标题：** phase2-hicache-design-architect-e2-04
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
为 P2-0 子任务 p2-0-04 设计 HiCache prefetch/storage-hit 部分恢复的归因与测量方案，梳理候选机制、事件分类、per-request/run-level 指标与探针缺口。

## 实际改了什么
交付并落盘 `attribution-design.md`（外部工作区路径见原报告）；仅写设计文档，未 commit/push，也无引擎代码修改。基于源代码行与前序勘察结果整理预算门、L3 部分命中、host 压力部分分配、H→D 全有全无等触发机制。

## 生成结果与验收
设计稿给出 34 行测量变量表、partial-restore 判定公式、事件分类/置信边界与 P2-1 探针缺口。host-pressure partial allocation 是本稿新识别的 ②b 变体；现有 b15 面未必能区分②/②b，不能强行归因。`pb_load_*` 无 rid、mem_quota 缺失、prefill fail 静默等限制均列明。任务 done 仅指设计交付，不代表这些机制已运行时验证或下游实验完成。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-architect-e2-04.md`：- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/attribution-design.md`（交付物，已落盘；
  只写文档，未 commit 未 push）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-architect-e2-04.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e2-04.md`; SHA256 `4a721b66cbfd8520a0d77081b24bd7ebd7a3b28d52a5918c861e3453ad20637d`; source state `tracked`
