# P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION

- **工作标题：** P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md`：**
- Supersedes the gate BASIS of `P1-R122-HEADROOM-GATE-ADDENDUM.md`
(sha256 `92ad1c29…1aea25`). The v1 gate *intent* (two moments, sequential
chain, Gate B = "F1 released so T is genuinely allocatable") is user-ratified
and UNCHANGED. Only the pool/measurement basis is corrected, because v1's
`host_allocable := full_free + full_evictable` measured the WRONG pool.
- Disposition of the v1 file: RETAINED, not deleted; annotated INVALID on basis.
This v2 governs.

## 实际改了什么
冻结的 orchestrator contract correction，supersedes R122 v1 **measurement basis only**；保留 v1 文件作审计，不含代码改动或实验。v1 的 two-moment sequential Gate A/B intent 不变。

## 生成结果与验收
纠正 HOST_ALLOC capacity basis 为真实 L2 host pool：权威 fresh measurement 是 `host_alloc.v1` retry_result 的 `per_pool.kv.free_after`（free_after_reclaim），不是 `full_free/full_evictable` device KV pool，也不是 raw free_before。Gate A 在 F1 stage 前要求 `free_after_reclaim >= F1_D_req + margin`；Gate B 在 T stage 前要求 `>= T_D_req + margin`，并证明 F1 host allocation 已释放。基于 R121 evidence 修正 blocker 归因：T 实际已有 F1 RELEASED predecessor grant，但 free_after_reclaim 24,670 < D_req 27,328（差 2,658）；稍后 F1 pages 可 reclaim 时 T deadline 同时到期，且 Mamba generation 未推进而被 hold。故原先“只有 flush/close 或新 capacity 才能改变”的结论 superseded；新目标是 headroom-availability vs deadline/wake-eligibility race。server restart/profile change/flush/close 仍明确禁止。该文件冻结的是规则/解释，不表示已验证 R123。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md` → `.memory/rh-p1-durable-replay-eviction/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM-v2-CORRECTION.md`; SHA256 `cbd1cf5748146a6bf1e77bedb6586d99019ea48ccd791a9b0d0f2a47555decce`; source state `tracked`
