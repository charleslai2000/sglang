# p2io-tester-e5

- **工作标题：** p2io-tester-e5
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e5.md`：**
**done** — 同步核验 9/9 一致；M4T 同配置终裁重测完整跑完（96 请求 0 失败，rc=0）。判据裁决：
**FAIL（双层门均不过）**。数据面 B（整链完成窗口）p50=1.158s 差于 1.0s 门 16%；机制面
**T15 全程 0 次触发**（0 park / 0 wake / 0 demand ticket）——e9 的 frontier 严格条件在本负载
下从不满足（在途备份目标从不覆盖请求终点），e4 的 72 次 park 全部被正确消除，但 T15 对
本负载贡献为零，行为回到 M4T 基线（partial restore + T6 DEVICE_QUOTA/PREFETCH_BUDGET 循环），
A（request-level cycle）p90=10.7s 仍 > 几秒级（T6 主导，Ready Horizon 域，范围外）。与 e4
相比的唯一改善：park→rate-limit 灾难消失（A p90 47.9→10.7s）。判据逐条见 §4。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e5.md` → `.memory/phase2-hicache-design/work/p2io-tester-e5.md`; SHA256 `d76bc787eb8b7cd407edc3143010211a900a885dafa1c1cae48cb77184cf68f9`; source state `tracked`
