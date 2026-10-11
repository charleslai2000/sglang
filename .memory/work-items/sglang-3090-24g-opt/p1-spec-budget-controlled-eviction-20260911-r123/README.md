# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123

- **工作标题：** P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123.md`：**
R123 driver (`driver123.py`, R121-faithful decoy: F1 43107, F2 42930, T 27228,
5x ~43k pressure, plus a pre-window donor completion of F2 to seed evictable host
pages). Window `[R-F1, R-T]` submitted in one request, HTTP 200 in 74.409 s,
`prompt_tokens=70335` (=43107+27228). Window server window: `raw.log` = server
lines 3084733..3222416.

## 实际改了什么
在既有 local server (PID 48746/scheduler 48806) 上执行 R121-faithful driver workload：F1/F2/T durable builds、5 个压力 requests、F2 donor completion，随后单次 `[R-F1,R-T]` batch window；server/profile/source 保持不变，无 cache flush/session close/product edits/instrumentation。

## 生成结果与验收
**NOT_VERIFIED；冻结 R123 chain 未展示**。Gate A/C5 未满足：首个 R-F1 allocator record free_after_reclaim 1,581 vs required 43,072；driver 在未满足 R121 fail-fast precondition、且 DRAIN/DONOR_DRAIN false 时仍开 window。T 没有进入 preadmission/restore path，而是直接 prefill（cached-token 0），故无 T SPEC_BUDGET park/host wait/wake、无 finalize/restore_success；epoch +1 是 decoy F1 alloc_failed timeout release，不是 T 的 budget causal wake。Temporal criterion 不可评估，不能据此声称 product liveness fail。报告归类 harness defect：gate 未 fail-fast，donor preprocessing 自身 host-alloc timeout/recompute、增加压力。剩余一次 run budget 未花；须 owner 先解决 T bypass 和可行 Gate A 再授权重跑。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123.md` → `.memory/rh-p1-durable-replay-eviction/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123.md`; SHA256 `adbf6622990efcae18a1056ea7171b5a35c65f51c3ecd5de496ee3fc44d91f10`; source state `tracked`
