# P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT

- **工作标题：** P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`：**
- Applies to `P1-DURABLE-PREFIX-REPLAY-20260912-R125`.
- Binding additive superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
(`2ac86b5a…b3b`) and `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`
(`bf7b09ee…1e1f8`). Gate basis is v2 (L2 host pool via `host_alloc.v1`).
- User ruling (2026-09-12): execute **Option A** — restore-path replay of R121's
KNOWN durable prefix on the rebuilt server (which loads the HOST_ALLOC
wake-liveness fix). NO product patch, NO profile change, NO workload redesign.

## 实际改了什么
用户 ruling 选择 Option A 后冻结的 replay contract；不包含产品/profile/workload 改动或执行。采用 R122 v2 L2 host pool gate basis，要求复用已存在 R121 durable prefix，严禁重建“相似”prefix。

## 生成结果与验收
规定 Gate 0 exact L3 keyset/hash 与 27,328 hit；其后 nonresident→SPEC_BUDGET park→F1 release epoch +1→T RH issue→HOST_ALLOC wait→观察新 wake predicate 决定 grant→durable boundary FULL KV+Mamba restore→generation。核心区分：若 grant 时所有 blocked-domain generations 都已前进，即使恢复成功也只是 NON-EVIDENCE（旧规则同样会 grant），不算新修复命中。禁止 server restart、profile/parameter change、flush/close、新 instrumentation及修改 R121–R124 artifacts；最多 2 runs/60min/200 HTTP。该文件是冻结合同，不是 run 结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md` → `.memory/rh-p1-durable-replay-eviction/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`; SHA256 `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f`; source state `tracked`
