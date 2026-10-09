# p2io-tester-e7o

- **工作标题：** p2io-tester-e7o
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7o.md`：**
done（实验已跑完、证据已拉回、分析完成、远端已清理、GPU 已归零）。结论为 **FAIL**：e28 修复
（batch_exists_v2 placeholder 强制 TRAILING）**未能恢复 storage_hit**，但实验产生了决定性证据，
将封锁点从之前的 "allocator 注册缺陷"（e7m 结论）修正为 **mamba 组件 key 位置错位**（写侧
`node.hash_value[-1]` → `.mamba` key，读侧 TRAILING 扫描窗口内永远找不到该 key）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7o.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7o.md`; SHA256 `4c2ee78c907768b1d8345a5803de385ac3c924684af65a59712f30fad54b387f`; source state `tracked`
