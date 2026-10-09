# P2A-ORCHESTRATOR-VERIFICATION

- **工作标题：** P2A-ORCHESTRATOR-VERIFICATION
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
独立重算 R129 P2-A 原始 log window 的 Q1/Q2/Q3 指标，审查 tester 报告数值并结合源码追溯 storage-query 耗时根因；标出 per-request join/样本量等证据缺口。

## 实际改了什么
这是只读独立验证，没有产品修复。独立核对 raw window SHA 与 tester report SHA，重新解析事件并检查配置和 source；未把建议的 metadata-cache 配置变更当作已经实施。

## 生成结果与验收
Tester report 主要结论判为 **ACCURATE**，同时记录 percentile method 的 Q1 p95/p99 数值差异。Q3 的 27 个 storage_hit_query 显示 p50 17.777s，backend lookup 占 span 99.93–100%；源码确认 metadata cache 默认关闭时每次 query 对 3.09M-file L3 目录执行 `os.scandir`。Q1↔Q2 有 per-request telemetry 缺口（完成尝试无 admission.v2，且 32/59 enqueue 无 admission），Q2 仅 n=1；因此相关 coverage 不作推断。结论：metadata query 是强优化候选，但无 product fix，任何 profile/config 改动需另行授权；报告中锁释放 watcher 触发 SIGTERM 的责任与主 59-request run 不受影响亦有记录。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R129-bundle/P2A-ORCHESTRATOR-VERIFICATION.md` → `.memory/phase2-hicache-design/work/R129-bundle/P2A-ORCHESTRATOR-VERIFICATION.md`; SHA256 `23a7a5fd173a1de2503df8fe594d97ad4a7b223b7090f4671fdbcf02c0e51b21`; source state `tracked`
