# phase2-hicache-design — doc-writer 追加 §7（实验① c>8 并发上限 sweep）

- 任务：sglang-3090-24g-hicache（phase2-hicache-design）doc-writer 追加 §7 到生产基线报告
- 日期：2026-09-05
- 状态：**done**

## status

done —— §7 已追加到目标报告，§0-§6 原样保留，数字全部来自 tester 数据，未编造。

## artifacts

- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-decbm-baseline-report.md` —— 追加 `## 7. 实验①：c>8 单卡 decode 并发上限 sweep（2026-09-05）`（含 7.1-7.6 小节），追加在现有 §6 之后。
- 本报告：`phase2-hicache-design-docwriter-baseline-s7-e1.md`。

## evidence（交叉核对的代码/数据源）

- tester 最终报告 `work/phase2-hicache-design-tester-conc-sweep-e1.md`（§0 profiler / §2 档位表 / §3 plateau / §4 并发结论 / §5 证据路径）——§7 全部数字据此转写。
- 目标报告 §4（三向归因）、§5（未测项 conc>8、证据路径）、§6（封板措辞）——§7 衔接 §5.1"conc>8 未测"与 §4.4 推荐点，口径（TTFT=E2E、decode tok/s 用 realtime_tokens_total delta）与 §3 一致。
- 验证：grep `^## ` 确认 §0-§6 行号不变（12-170），§7 新起于 206；未改动 §0-§6。

## summary

- 在 `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-decbm-baseline-report.md` 末尾（§6 封板之后）追加 §7，完整收录实验①：7.1 前置 profiler（c8 compute-bound/power-limited，GPM 降级）、7.2 各档结果表（agg TPS 用 realtime_tokens_total decode delta/稳态窗）、7.3 plateau 判定（actual ~15-16 达 plateau，c19→c21 <5% 判据成立，停止增大 Mamba pool）、7.4 最大有效并发 ≈16 + eviction 开销 ~4-6% 非预期发现 + 推荐工作点（强化阶段② pool64+c8）、7.5 边界/open issues、7.6 证据路径。
- 遵循的 style：与现有报告一致（紧凑表格 + 来源列/注 + 数据纪律声明：全部 TPS 口径、TTFT=E2E、actual-vs-nominal 对比纪律）；行宽 ≤100 字符、未断在 URL/代码内。
- 只改目标报告追加 §7，未动其他文件、未动 §0-§6、未 push。

## followups

1. runner 175.155.64.171:24052 上 PID 508273 `launch_server`（`--max-mamba-cache-size 32`，19:16:12 启动，非本实验进程）——不在本任务清理范围，仅记录，建议 orchestrator 知悉 runner 被该进程占用。
2. pool 耗尽 eviction 开销 ~4-6% 是否也在 pool64/c8 推荐点存在——tester 已判定 c8 avail 21.8 未耗尽无此问题；如需后续复核可单独建档。
3. 真 21 并发稳态需开放式客户端（`--stream:true` 等），改变 trace 语义，超出固定 trace 纪律——记录未测。

## open_issues

- GPM 消费卡硬件限制无法拆分 SM-activity vs Tensor-activity（严格区分需 Nsight，本机无）——不影响 compute-bound 结论（功耗墙 + SM/Mem 100% + PCIe 忽略已足够）。
- 无其他对 orchestrator 的未决问题。
