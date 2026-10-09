# phase2-hicache-design-tester-scorecard-e1

- **工作标题：** phase2-hicache-design-tester-scorecard-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-scorecard-e1.md`：**
全部只读重算，未启动任何引擎/load，未修改任何证据。计算脚本留在 runner `/root/scorecard_cells.py`、`/root/scorecard_gate3.py`、`/root/scorecard_abwin.py`。
**数据源与对象集合**
- 阶段② 固定 trace decode 基准（正式工作点，11 cell）：`/root/evidence-gen-p{32,64,96}-c{4,6,8}/`（Graph ON）与 `/root/evidence-gen-p{32,96}-c8-goff/`（Graph OFF）。每 cell 取 `run-*/mid-run-metrics.txt`（引擎 /metrics 快照，~5s 间隔）、`runs.csv`（逐请求）、`gpu-util.csv`（nvidia-smi 5s 采样）、`metrics-final.txt`（Prometheus text 末态）。
- Cache/restore/GC/容量（RH OFF/ON 基线 + A/B）：`/root/evidence-gate3-soak/`、`/root/evidence-gate3-rhon/`、`/root/evidence-gate3-ab-a-off/`、`/root/evidence-gate3-ab-a-on/` 及其 `engine-gate3-*.log`（事件日志，`evt=` 行）。
- Gate-2 K 变体（K4/K8/K16）用作容量分层参考，非 restore 主导，标注后作旁证。
**delta 对齐**
- decode TPS：`realtime_tokens_total{mode="decode"}` 计数器，按 `ts` 相邻快照差 / 时间窗。全窗 = 首末快照；稳态窗 = `num_running_reqs` ≥ 峰值 90% 的子窗。
- prefill_compute TPS：`realtime_tokens_total{mode="prefill_compute"}` delta / 窗。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-scorecard-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-scorecard-e1.md`; SHA256 `3f39fc909e7c6eebf877b53f5b488eaa5f9d2f3ea1f785d2f35c3dea9bd87d6f`; source state `tracked`
