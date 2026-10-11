# SMOKE-EXT-ANALYST-20260917-01

- **工作标题：** SMOKE-EXT-ANALYST-20260917-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`protocol-subagent-smoke-20260917/agents/SMOKE-EXT-ANALYST-20260917-01.md`：**
Synthesize the run's already-gathered PUBLIC external evidence into ONE calibrated judgment for a long-lived production deployment that pins the CPython 3.12 series, assessed as of 2026-09. State what an operations owner should conclude.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`protocol-subagent-smoke-20260917/agents/SMOKE-EXT-ANALYST-20260917-01.md`：**
**Judgment (one paragraph with explicit confidence):** An operations owner pinning CPython 3.12 for a long-lived production deployment should conclude that the series is in its **security-only support phase** as of September 2026, with no further bugfix or feature releases expected. The latest patch (3.12.14, released 2026-08-12) is the final maintenance opportunity within the bugfix window, and the series will transition to pure source-only security fixes until end-of-life approximately 5 years after the 3.12.0 release (October 2023), placing EOL around October 2028. **Confidence level: HIGH.** This is justified because (a) the investigator artifact establishes 3.12.14 as the latest patch from three independent, cross-verified public sources with no disagreement, and (b) the researcher artifact establishes — with explicit source attribution and empirical corroboration from endoflife.date — that the 3.12 series used an 18-month bugfix phase (not 24 months), meaning active bugfix support ended around April 2025 and the series has been in the security-only phase since then. The confidence is HIGH rather than maximal only because the inputs do not explicitly state a confirmed date for the 3.12 security-only transition weekend (they triangulate it from the 18-month rule + release date), and because the researcher artifact's source quality ratings note that endoflife.date is a secondary tracker (★★★☆☆) rather than an authoritative CPython source.
**Supporting evidence (each attributed to its input artifact):**
| Element | Source artifact | What it establishes |
|---|---|---|…（节选；见来源报告）


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `protocol-subagent-smoke-20260917/agents/SMOKE-EXT-ANALYST-20260917-01.md` → `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-EXT-ANALYST-20260917-01.md`; SHA256 `c8a1f769cae8fab8a3fefed7224f99b936b99855c139884f816d580912288365`; source state `tracked`
