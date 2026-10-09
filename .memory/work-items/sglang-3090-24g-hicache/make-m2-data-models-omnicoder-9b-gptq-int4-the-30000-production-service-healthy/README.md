# Make M2 (`/data/models/omnicoder-9b-gptq-int4`) the `:30000` production service, healthy

- **工作标题：** MLINE-M2-CUTOVER-WINDOW-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MLINE-M2-CUTOVER-WINDOW-20260918.md`：**
and verified. M1 (`/data/models/qwen35-9b-w4a16`) is only a fallback.
Scope: State determination (read-only) → M1 baseline capture → stop M1 via `stop.sh prod` →
launch M2 sequentially on the one RTX 3090 → validate health/models/deterministic chat/
coder-style/tool-call/throughput → on failure restore M1. No product source, test, frozen-tree,
or git modification. No `pkill`.
Result: **DONE — `:30000` now serves M2 (OmniCoder-9B GPTQ-INT4), healthy and verified.**
No rollback was needed. State found at start was `M1_UP`; M1 was stopped cleanly and M2 came up
in 89 s cold start. All Step-4 validation passed.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MLINE-M2-CUTOVER-WINDOW-20260918.md` → `.memory/phase2-hicache-design/agents/MLINE-M2-CUTOVER-WINDOW-20260918.md`; SHA256 `eaee9091c7d9f5ab7e733e6e2c6fdf50932f75c73f1ba3565665c42fbb9876bf`; source state `tracked`
