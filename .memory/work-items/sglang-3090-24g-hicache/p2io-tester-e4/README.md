# p2io-tester-e4

- **工作标题：** p2io-tester-e4
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e4.md`：**
**done** — 代码同步核验 9/9 一致；M4T 同配置实验完整跑完（96 请求 0 失败，rc=0）；判据裁决：
**P2-IO 未 CLOSED**。T15 park 机制本身生效且无 lost-wake 孤儿（BACKUP_PENDING residence
p50=0.70s / max=3.74s，无 ~60s 样本，per-pass predicate 兜底成立），但核心指标全部 FAIL 且
**整链 restore p90 较基线恶化**（3.9s→47.9s）：park 等待的写在途 span 常不含缺失尾（drop-
without-backup / 链增长），wake 后 re-lookup 仍 partial；且 wake 后 re-issue 与 prefetch
rate limit（预算 ≈ 单条整链 20,910 tokens）碰撞，57 次 denied_rate_limit → PREFETCH_BUDGET
等待 p90=18.4s 成为新尾延迟。判据逐条证据见 §4；根因与修复方向见 §5。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e4.md` → `.memory/phase2-hicache-design/work/p2io-tester-e4.md`; SHA256 `e47eb34a4b19827820da97c1fa943814c02ef9a94bffbd01483dc85081d87208`; source state `tracked`
