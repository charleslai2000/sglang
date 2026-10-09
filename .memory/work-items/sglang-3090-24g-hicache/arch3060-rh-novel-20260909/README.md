# ARCH3060-RH-NOVEL-20260909

- **工作标题：** ARCH3060-RH-NOVEL-20260909
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
阐明 RH-ON 唯一初始 pre-admission prefetch 所有权边界为何构成新机制，并与 RH-OFF eager path、HOST_ALLOC generation/FIFO retry、hybrid allocation/durability 的职责区分开。

## 实际改了什么
架构声明工作，生成 `sglang-3090-24g-opt/review/gates/NOVEL-MECHANISM-20260909-RH-PREADMISSION.md` 及本报告；未修改 source file 或其他 gate artifact。

## 生成结果与验收
声明 RH-ON 对每个选定 request/stage generation 仅有一个初始 pre-admission prefetch 的语义授权，禁止 ordinary eager duplicate；RH-OFF 保留现有 eager path。物理分配、KV+Mamba finalization/durability、HOST_ALLOC generation/FIFO retry 不归 RH 所有；后续因果上独立的 demand retry 按 restore rules 处理。报告只是供 orchestrator/gate owner 决策的非权威设计建议，不批准实现。

### 报告列出的产物/证据
- `phase2-hicache-design/work/ARCH3060-RH-NOVEL-20260909.md`：- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/NOVEL-MECHANISM-20260909-RH-PREADMISSION.md`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-NOVEL-20260909.md`
No source file or other gate artifact was changed.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH3060-RH-NOVEL-20260909.md` → `.memory/phase2-hicache-design/work/ARCH3060-RH-NOVEL-20260909.md`; SHA256 `c0d4da7ec550930fe49ae8577a1a88bc014285bb307b14da5a9bec2b53a42f11`; source state `tracked`
