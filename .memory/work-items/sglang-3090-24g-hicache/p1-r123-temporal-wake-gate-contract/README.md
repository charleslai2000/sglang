# P1-R123-TEMPORAL-WAKE-GATE-CONTRACT

- **工作标题：** P1-R123-TEMPORAL-WAKE-GATE-CONTRACT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`：**
- Applies to `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123`.
- Binding ADDITIVE superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
(sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`).
- Gate basis is v2 (`host_allocable := free_after_reclaim`, L2 host pool via
`host_alloc.v1`). The v1 device-pool gate is **INVALIDATED**
(`R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`).
- User ruling (2026-09-12): R121 exposed TWO potentially independent problems.
R123 must DISCRIMINATE them; it must not merge "headroom timing" with

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`：**
| condition | verdict |
|---|---|
| `t_feasible < t_deadline` but T did NOT wake / was held because Mamba generation did not change | **PRODUCT LIVENESS FAIL** — must fix `_host_alloc_wait_eligible` blocked-domain semantics; a workaround recipe is NOT acceptable |
| `t_feasible >= t_deadline` | capacity/timing shortfall at this profile/workload — NOT a wake bug |
| `t_feasible < t_wake < t_deadline` and final FULL restore | **P1 PASS** |
Plus the standing chain/C1–C4 conditions: `durable-prefix recompute == 0`;
`hybrid_discard == 0`; PARTIAL/shortfall within `D_req` = FAIL (tail strictly
outside `D_req` allowed and must be evidenced); HTTP completed; identity
continuous.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md` → `.memory/phase2-hicache-design/work/R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`; SHA256 `bf7b09ee67f40a3f9c5e58b89d54e091b028fae1a96c853bdebfcadd1145e1f8`; source state `tracked`
