# P1-R122-GATE-V1-INVALIDATION

- **工作标题：** P1-R122-GATE-V1-INVALIDATION
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`：**
- Artifact invalidated: `work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md`
sha256 `92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`.
- Status: **INVALIDATED** (not merely "corrected"). The gate *intent* (two
moments; sequential chain; Gate B = "F1 released so T is genuinely
allocatable") remains user-ratified, but its **measurement basis is wrong and
must not be used again**.
- Reason: v1 defined `host_allocable := full_free + full_evictable`, which reads
the **device** KV pool (`_component_available_size(ComponentType.FULL)` =

## 实际改了什么
只读机制对账并新增正式 invalidation marker；未修改被废止的 R122 v1 addendum bytes，以保留 SHA256 chain。

## 生成结果与验收
**R122 host-headroom gate v1 正式 INVALIDATED，不是一般修订**：其 `full_free + full_evictable` 测的是 device KV pool (65,536)，而真正阻塞 HOST_ALLOC 的是 L2 `mem_pool_host` (131,073 logical)；报告当时实际 host allocable 2,786，v1 误报 device values 63,488/65,534。此后任何 HOST_ALLOC capacity/eligibility claim 必须基于 L2 host pool 的 `host_alloc.v1`/`host_allocability_snapshot`，禁止用 device `full_*` quantity。Gate intent 的双时点顺序仍保留；依据是单独 v2 correction，v1 原件/hash 留存。

R122 v1 invalidation 的正式状态与适用限制已在上文记录；本卡无测试结论。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md` → `.memory/rh-p1-durable-replay-eviction/R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`; SHA256 `db6e3e786204f188e60e63e83d4f93ff4d780109da0f9d8734dfb38ace57cfcb`; source state `tracked`
