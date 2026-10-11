# phase2-restorearm-architect-e3

- **工作标题：** phase2-restorearm-architect-e3
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-restorearm-architect-e3.md`：**
- status: **done**
- epoch: e3
- owner: architect
- task: 只读定位 restore eligibility / admission re-arm 核心缺陷（不做实现、不做计数器 heuristic），给出精确代码链、device-hit 阻塞原因、正确状态语义裁决、Fix A 边界
- 代码基线: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt`（分支 3090-24g-opt，含 Fix A/B patch）
- 既有证据: `phase2-rhfix-architect-e1.md`、`phase2-rhfix-fixb-crosstest-tester-e1.md`、`phase2-rhfix-tester-e1.md`
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/phase2-restorearm-architect-e3.md`：**
restore eligibility / admission re-arm churn 的根因是**状态语义缺陷**：definitive miss 把状态塌缩回 NONE，丢失"该前缀刚被证明 L3 缺失"的负证据；re-arm 资格谓词 `has_restore_potential` 是结构存在性检查，不读任何 epoch/generation，因此同 episode 内无真实 cache 变化时仍立即 re-arm，形成 ~13ms churn。修复方向 = 以粘性 MISS 状态（或 miss_epoch 字段）携带负证据，re-arm 仅在 `l3_publish_epoch` 前移或 generation 改变时放行，否则转 forward recompute/admit。不用"连续 miss N 次放弃"计数 heuristic（频率代理无结构意义、与正确信号错位、Fix B 实证不触发）。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-restorearm-architect-e3.md` → `.memory/phase2-hicache-design/work/phase2-restorearm-architect-e3.md`; SHA256 `38302b7fded2d071770ed609c5e53500a45c45678ed1dad08af61a4244c52ec5`; source state `tracked`
