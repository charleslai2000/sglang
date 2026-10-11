# OPS3060-CONTEXT-CAPACITY-R3-20260910

- **工作标题：** OPS3060-CONTEXT-CAPACITY-R3-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-CONTEXT-CAPACITY-R3-20260910.md`：**
- RTX 3060 12 GB, one GPU; Qwen3.5-4B AWQ W4A16/Marlin.
- FP8 E4M3 KV, CUDA Graph decode/prefill enabled, chunked prefill 2048.
- HiCache enabled with file backend and write-through semantics.
- RH OFF for the capacity measurements (the `--enable-ready-horizon` flag was
omitted); service was restored to RH-ON c1 afterward.
- File HiCache was explicitly redirected to `/hy-tmp/hicache-context-r3`.
The default `/tmp/hicache` is on the 30G root overlay and is not safe for
long-context experiments.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-CONTEXT-CAPACITY-R3-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-CONTEXT-CAPACITY-R3-20260910.md`; SHA256 `1d614f95d7a9c24172b391d012ed35068d59e3ec0dc2172e033fa54ca05a1e9d`; source state `tracked`
