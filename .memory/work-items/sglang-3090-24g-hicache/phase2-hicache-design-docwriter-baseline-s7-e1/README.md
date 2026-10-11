# phase2-hicache-design-docwriter-baseline-s7-e1

- **工作标题：** phase2-hicache-design-docwriter-baseline-s7-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-docwriter-baseline-s7-e1.md`：**
- 任务：sglang-3090-24g-hicache（phase2-hicache-design）doc-writer 追加 §7 到生产基线报告
- 日期：2026-09-05
- 状态：**done**

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/phase2-hicache-design-docwriter-baseline-s7-e1.md`：**
- 在 `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-decbm-baseline-report.md` 末尾（§6 封板之后）追加 §7，完整收录实验①：7.1 前置 profiler（c8 compute-bound/power-limited，GPM 降级）、7.2 各档结果表（agg TPS 用 realtime_tokens_total decode delta/稳态窗）、7.3 plateau 判定（actual ~15-16 达 plateau，c19→c21 <5% 判据成立，停止增大 Mamba pool）、7.4 最大有效并发 ≈16 + eviction 开销 ~4-6% 非预期发现 + 推荐工作点（强化阶段② pool64+c8）、7.5 边界/open issues、7.6 证据路径。
- 遵循的 style：与现有报告一致（紧凑表格 + 来源列/注 + 数据纪律声明：全部 TPS 口径、TTFT=E2E、actual-vs-nominal 对比纪律）；行宽 ≤100 字符、未断在 URL/代码内。
- 只改目标报告追加 §7，未动其他文件、未动 §0-§6、未 push。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-docwriter-baseline-s7-e1.md`：- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-decbm-baseline-report.md` —— 追加 `## 7. 实验①：c>8 单卡 decode 并发上限 sweep（2026-09-05）`（含 7.1-7.6 小节），追加在现有 §6 之后。
- 本报告：`phase2-hicache-design-docwriter-baseline-s7-e1.md`。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-docwriter-baseline-s7-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-docwriter-baseline-s7-e1.md`; SHA256 `2eb5c7718c8f614671d2211fc81701d3e5faad45cebc69c5b508f1ccad975320`; source state `tracked`
