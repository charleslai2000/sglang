# phase2-p1-fix-coder-e1

- **工作标题：** phase2-p1-fix-coder-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-p1-fix-coder-e1.md`：**
- status: done
- epoch: e1
- owner: coder
- task: 实现 P1 修复（restore eligibility / admission re-arm churn），unit 验证
- 仓库: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt`（分支 3090-24g-opt）
- 本地 commit: `74246bb90f`（未 push，符合约束）
- 基线: cc718c3c2e（含 P0 修复）

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/phase2-p1-fix-coder-e1.md`：**
选 A（粘性 MISS_RECOMPUTE 状态 + Req miss_epoch/miss_generation 负证据字段）。
T9 genuine miss → MISS_RECOMPUTE/ADMIT_RECOMPUTE（不再回 NONE）；T6 在 sticky 且
l3_publish_epoch 未前移 / generation 未变时不 re-arm，请求 forward recompute；
epoch 前移或 generation 变恢复资格。三态分流（miss / 纯容量 / 瞬态）由状态 + epoch 门
区分，device-hit 容量 re-arm 不被误伤。Fix B 保留为历史证据。与 Fix A/P0 正交。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-p1-fix-coder-e1.md`：- commit: 74246bb90f（本地，未 push）
- 337 passed（相关 unit/state-machine 套件），5 个 drain_reentry 失败为基线既有
- 命令见上（pytest，各文件通过数）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `74246bb90f`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-p1-fix-coder-e1.md` → `.memory/phase2-hicache-design/work/phase2-p1-fix-coder-e1.md`; SHA256 `4e0dedef4716f7cd68314582cfc7a7ed094e713069c2caa624803b00caf39cd4`; source state `tracked`
