# Restore production M1 on port 30000 after the failed M2 cutover stopped it, and verify it

- **工作标题：** PROD-RESTORE-M1-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/PROD-RESTORE-M1-20260918.md`：**
end to end. M1 = frozen tree `/opt/sglang/local-prod-v1.2.1-candidate`, model
`/data/models/qwen35-9b-w4a16`. The M2 cutover was explicitly OUT OF SCOPE.
Scope: Pre-flight (read-only) → start via canonical entrypoint → bounded readiness wait → verify
health/models/chat on loopback + LAN → record PIDs/argv/logs/GPU/lock. No M2, no source/tree edits,
no git changes, no `pkill`, no signal to any pre-existing process.
Result: **DONE — production `:30000` is UP and serving M1.** Entrypoint `start.sh prod` returned rc=0,
cold start 132.0s (identical to the prior recorded cold start), and all Phase-2 checks passed on both
loopback and LAN.

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
- `phase2-hicache-design/agents/PROD-RESTORE-M1-20260918.md` → `.memory/phase2-hicache-design/agents/PROD-RESTORE-M1-20260918.md`; SHA256 `3c247e2c685edc4206a2ba99a5096b057cde31610932f23b944c09e2c1aa9e1e`; source state `tracked`
