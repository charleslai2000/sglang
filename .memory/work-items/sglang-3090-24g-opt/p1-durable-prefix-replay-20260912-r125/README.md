# P1-DURABLE-PREFIX-REPLAY-20260912-R125

- **工作标题：** P1-DURABLE-PREFIX-REPLAY-20260912-R125
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md`：**
The experiment ran (2/2 allowed live runs) and reproduced most of R121's chain on
the rebuilt server, but the **fixed HOST_ALLOC capacity clause was never the
deciding factor**, so the fix is **not runtime-exercised**. Per the frozen
contract this is a **NON-EVIDENCE** outcome, not a PASS. Budget is exhausted, so
this needs a fresh dispatch/decision.
- Bundle: `work/R125-bundle/` (root = run 1, chain-bearing; `run2/` = corrected
attempt). `chain.json`, `condition-evidence.md`, `manifest.json`,
`sha256sums.txt`, `driver125.py`, `raw.log`, `probe.log`, `requests.jsonl`,

## 实际改了什么
在 rebuilt server (PID 3082643/scheduler 3086752) 上完成冻结预算的 2/2 live runs；核验 L3 durable objects 与 scheduler fix hash，使用 `work/R125-bundle/` 保存 raw evidence。无 server lifecycle/cache/session、product source 或 instrumentation changes。

## 生成结果与验收
P1 **NOT_VERIFIED / NON-EVIDENCE，预算已耗尽**。Run 1 复现大部分链（Gate 0 identity pass、SPEC_BUDGET park、F1 release +1、T issue、HOST_ALLOC wait、accepted finalize 完整取回 D_req=27,328 与 Mamba 1/1），但 Gate 2 未证明 scheduler fix 起决定作用：grant 时 KV 和 Mamba generations 都推进，旧规则也会 grant；capacity clause 未被调用。Gate 3 字面合同亦未满足：PARTIAL/shortfall 是 11-token 外部 tail，`restore_success` 为 D_req−2，虽 durable boundary 完整 fetch。Run 2 的 F1 HOST_ALLOC wait 占住唯一 running slot 并 timeout，T 未进入 RH/storage restore 而普通 recompute。分类为 workload timing/harness NON-EVIDENCE，不是产品 fix 失效；contract 中 p1 nonce 应改 p3，且 Gate 3 的 FULL/成功 token 字面表达受 tail 与 -2 telemetry convention 阻碍。要再跑须 fresh authorization；不能据此宣称 fix runtime exercised。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md` → `.memory/rh-p1-durable-replay-eviction/P1-DURABLE-PREFIX-REPLAY-20260912-R125.md`; SHA256 `e496a3ce75d71d7bfae44d46c480891d2c8361b0b4fc497fa5033666429e7c27`; source state `tracked`
