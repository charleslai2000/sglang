# P1-R122-GATE-V1-INVALIDATION

- **工作标题：** P1-R122-GATE-V1-INVALIDATION
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`：**
- Artifact invalidated: `work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md`
sha256 `92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`.
- Status: **INVALIDATED** (not merely "corrected"). The gate *intent* (two
moments; sequential chain; Gate B = "F1 released so T is genuinely
allocatable") remains user-ratified, but its **measurement basis is wrong and
must not be used again**.
- Reason: v1 defined `host_allocable := full_free + full_evictable`, which reads
the **device** KV pool (`_component_available_size(ComponentType.FULL)` =

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** INVALIDATED

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md` → `.memory/phase2-hicache-design/work/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`; SHA256 `db6e3e786204f188e60e63e83d4f93ff4d780109da0f9d8734dfb38ace57cfcb`; source state `tracked`
