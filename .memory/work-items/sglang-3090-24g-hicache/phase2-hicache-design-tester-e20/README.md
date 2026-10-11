# phase2-hicache-design-tester-e20

- **工作标题：** phase2-hicache-design-tester-e20
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-e20.md`：**
**blocked（重要发现）** — K=16 smoke **完整通过**（128/128、18.5 分钟、OOM=0、五项全过）；**K=32 smoke 5 分钟 OOM 崩溃复发**（16384-token 半池锁链，与 e15 K=8 崩溃同形）——**M1/M2 修复未覆盖深度 32 触发的 evict 死锁路径**。归因曲线完整记录（K=8/16/32 对比），五项确认逐项结论见下。需协调人裁决：evict 锁链第三轮修复或接受 K=32 为已知 scale 边界。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-e20.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-e20.md`; SHA256 `ef1bc8ebe3e61c1c88bb7ae0e2cbd8595b523cac7aa737e3504dc932d1fc48c5`; source state `tracked`
