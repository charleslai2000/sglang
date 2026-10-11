# TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1

- **工作标题：** TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1.md`：**
- Invocation status: done
- Live verdict: **NOT_VERIFIED / fail-closed**
- Host: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-churn-fix1-live-r12`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** NOT_VERIFIED; done

**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1.md`：**
The fresh frozen S=25 run started successfully with RH off and the accepted FIX1
vehicle. It produced all 25 target build identities and exactly 9 auxiliary churn
builds. The raw product trace contains 25 combined KV+Mamba durability barriers,
but it contains **zero strict `residency_barrier(cold_residency=true)` events**.
Consequently the vehicle issued no warm lookup/request and no restore request. The
vehicle reached its bounded watchdog and returned a fail-closed `NOT_VERIFIED`
verdict. This is not runtime PASS evidence; lower-level `residency_free_complete`
events were not mapped to residency acceptance.
The independent debugger conclusion that product-side strict residency evidence is
missing is consistent with the raw trace. No product implementation, design, ledger,
or gate report was modified.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1.md` → `.memory/phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-TARGET-CHURN-FIX1.md`; SHA256 `8f15674083a9a4303d2ba30b2ef746751d1156ef68f96ae151b2d48335a9f05e`; source state `tracked`
