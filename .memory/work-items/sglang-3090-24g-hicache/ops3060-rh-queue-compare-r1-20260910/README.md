# OPS3060-RH-QUEUE-COMPARE-R1-20260910

- **工作标题：** OPS3060-RH-QUEUE-COMPARE-R1-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`：**
- Two distinct, previously durable 55K sessions A/B were submitted behind a
live blocker request (80 prompt tokens, 2,048 generated tokens).
- `max_running_requests=1`, AWQ W4A16/Marlin, FP8 E4M3 KV, Graph ON,
HiCache file backend on `/hy-tmp/hicache-restore-r3`.
- The blocker creates a real prediction horizon; the blocker plus A/B trace was
identical between RH OFF and RH ON.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`：**
- RH eligible Host-ready-before-admission rate for the two parked sessions is
  1/2 (50%), below the required 95%.
- RH ON does not yet convert the queued workload to a Host-ready path. It
  improves neither B's path nor the two-session trace's worst-case TTFT.
- The exact negative-cache/spec-budget re-trigger defect is being handed to a
  source debugger for an independent causal report before any code change.
- No broad fleet or 8-session claim is authorized from this result.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-RH-QUEUE-COMPARE-R1-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`; SHA256 `8162ea05a3c4546582f70efcf947192c0903ef3b81bb4f70de6c3ed91cab0699`; source state `tracked`
