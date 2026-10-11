# p2io-tester-e7h

- **工作标题：** p2io-tester-e7h
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7h.md`：**
报告人: root tester | 状态: **done** | 日期: 2026-09-01 | epoch: 1
> 本次运行：e7h-r2（干净单发命名空间，锁保护），配置 = e7g 核算的 HICACHE_SIZE=12G +
> reserve 0.75G + margin 0.3G，其余同 e7f（enable-ready-horizon + extent + write_back +
> T15 off + 8 agents/96 req/24 turns/K=8）。`ready_horizon_state_p95_tokens` 未设（默认 0 → 配置水位 2/4）。
> 8 个 agent × 12 turns（agent_driver 强制 turns≤12）实际 96 请求（非 dispatch 的 24 turns，
> 与 e7f verdict 一致）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** /root/p2io-m4t-e7h-r2-status.log; status=done agents=8 turns=12 requests=96 failed=0 downgraded=16 elapsed=479s

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7h.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7h.md`; SHA256 `b641b157b399f8399feab2a9d4e9ce26a17b77455245502e4f8d304c686de7a0`; source state `tracked`
