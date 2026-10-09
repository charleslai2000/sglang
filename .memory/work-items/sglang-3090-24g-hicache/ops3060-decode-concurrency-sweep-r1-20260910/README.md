# OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910

- **工作标题：** OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md`：**
- Hardware: one RTX 3060 12 GB, SM86.
- Model: `Qwen3.5-4B-AWQ`.
- Weight backend: compressed-tensors W4A16 with Marlin startup path.
- KV dtype: FP8 E4M3.
- CUDA Graph: enabled; HiCache enabled; RH was OFF for the sweep.
- Request: short prompt, generation length 256, same trace shape per concurrency point.
- Sweep: nominal concurrency `c1/c2/c4/c6/c8`.
- The service was restarted between points and restored to the AWQ RH-ON c1 profile after the sweep.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-DECODE-CONCURRENCY-SWEEP-R1-20260910.md`; SHA256 `e90cd88cce5acf6277c3b9ac3418bcea17b92641a687e9976f7d56b892ab744b`; source state `tracked`
