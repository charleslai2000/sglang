# P1-DURABLE-PREFIX-REPLAY-20260912-R125

- **工作标题：** P1-DURABLE-PREFIX-REPLAY-20260912-R125
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md`：**
The experiment ran (2/2 allowed live runs) and reproduced most of R121's chain on
the rebuilt server, but the **fixed HOST_ALLOC capacity clause was never the
deciding factor**, so the fix is **not runtime-exercised**. Per the frozen
contract this is a **NON-EVIDENCE** outcome, not a PASS. Budget is exhausted, so
this needs a fresh dispatch/decision.
- Bundle: `work/R125-bundle/` (root = run 1, chain-bearing; `run2/` = corrected
attempt). `chain.json`, `condition-evidence.md`, `manifest.json`,
`sha256sums.txt`, `driver125.py`, `raw.log`, `probe.log`, `requests.jsonl`,

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md` → `.memory/phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md`; SHA256 `e496a3ce75d71d7bfae44d46c480891d2c8361b0b4fc497fa5033666429e7c27`; source state `tracked`
