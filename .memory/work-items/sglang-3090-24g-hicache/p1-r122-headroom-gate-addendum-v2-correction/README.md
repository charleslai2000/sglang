# P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION

- **工作标题：** P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
修正 P1-R122 host-headroom gate 的测量对象，同时保留用户已确认的两时点顺序链与 Gate B“F1 已释放、T 才可分配”意图；解释 R121 blocker 并冻结 R123 可证伪实验目标。

## 实际改了什么
产出 orchestrator 规范/更正文档；不是代码实现或运行实验。v1 文件保留但注明测量 basis INVALID，由 v2 替代该 basis，原 gate intent 不变。

## 生成结果与验收
v1 的 `full_free + full_evictable` 实际读 device KV pool，而 restore 阻塞条件是 L2 host pool；v2 规定权威值为 host `retry_result.per_pool.kv.free_after`（含可回收页），Gate A 要求 F1_D_req+margin，Gate B 要求 T_D_req+margin 且有 F1 RELEASED 证据。R121 记录已 grant T，但 `free_after_reclaim=24670 < 27328`，且 F1 pages 到约 60s deadline 时才可回收、Mamba generation 未推进；因此判断为 headroom/deadline/wake-eligibility race，推翻“只能加容量”的旧解释。R123 目标要求 FULL_DURABLE、非驻留、两次 gate、F1 release/wake、完整恢复且零 recompute/discard。此为冻结的验证合同，不证明 R123 已执行或系统已修复。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md` → `.memory/phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md`; SHA256 `cbd1cf5748146a6bf1e77bedb6586d99019ea48ccd791a9b0d0f2a47555decce`; source state `tracked`
