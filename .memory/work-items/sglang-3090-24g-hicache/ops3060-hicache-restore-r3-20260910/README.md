# OPS3060-HICACHE-RESTORE-R3-20260910

- **工作标题：** OPS3060-HICACHE-RESTORE-R3-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-HICACHE-RESTORE-R3-20260910.md`：**
- RTX 3060 12 GB; Qwen3.5-4B AWQ W4A16/Marlin; FP8 E4M3 KV.
- `max_total_tokens=65536`, HiCache file backend, write-through, data-disk path
`/hy-tmp/hicache-restore-r3`.
- RH was OFF for the deterministic restore paths. The service was restored to
RH-ON c1 after the run.
- Each prompt had exactly 55,000 pre-tokenized input IDs and one generated token.
The 24-token page tail is not historical recompute; it is the legal tail after
the 54,976-token cached prefix.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-HICACHE-RESTORE-R3-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-HICACHE-RESTORE-R3-20260910.md`; SHA256 `427c360c844c28cbcd736965ba199d2a10c99207b127bf684fa09e280e4d3303`; source state `tracked`
