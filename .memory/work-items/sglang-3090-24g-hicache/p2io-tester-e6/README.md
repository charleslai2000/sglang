# p2io-tester-e6

- **工作标题：** p2io-tester-e6
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e6.md`：**
**done** — `metric_compare.py` 改造并迁入仓库（`3090-dev/metrics/`，双侧同步 md5 一致）；
配对语义按用户 M7 定案（(rid, episode) 键、B_ep/A_ep 逐样本 A−B、quantile 在差分布上取）；
四轮既有日志回注完成：**B_fin 验证门四值逐位复现**（e5 1.158/n=15、m4t 1.051/n=11、
m4f 1.320/n=20、m4t-e4 1.236/n=17）；**A−B 溯源判定完成**：e5 报告 32.5s 为逐样本计算
（非 percentile 相减），旧公式精确复现（32.455 = 报告舍入值），修正后权威值
e5 p50=32.495s（Δ0.04s 维持）；ledger 追加一条（历史零修改）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e6.md` → `.memory/phase2-hicache-design/work/p2io-tester-e6.md`; SHA256 `4eb50d173c9c3be8a59f5eaa0a51856f1f35cb36e8f1e9495c9bb6bdee84e3af`; source state `tracked`
