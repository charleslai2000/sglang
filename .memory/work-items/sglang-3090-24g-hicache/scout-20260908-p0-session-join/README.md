# SCOUT-20260908-P0-SESSION-JOIN

- **工作标题：** SCOUT-20260908-P0-SESSION-JOIN
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/SCOUT-20260908-P0-SESSION-JOIN.md`：**
- Task ID: `SCOUT-20260908-P0-SESSION-JOIN`
- Epoch: `E20260908-P0P1P2`
- Role: `scout`
- Invocation status: `done`
- Admission: `ACCEPT`
- Scope: read-only exploration; this report is the only file written.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/SCOUT-20260908-P0-SESSION-JOIN.md`：**
The current active `sglang-3090-24g-opt` trace cannot safely produce the required
live join. It has operation/node/hash correlation, and the runtime already has
request `session_id` state, but there is no path from the vehicle's build request
identity into deferred storage/residency operations. There is also no current
`durability_barrier(combined_durable=true)` event. A timestamp or event-order
join would therefore be non-authoritative and violates the P0 contract.
The smallest safe solution is an additive, marker-gated trace context attached
to the request, retained on the cache node, copied onto storage operations and
pool transfers, and copied into every trace event. It must be observational only:
no cache key, allocator decision, LRU order, fold, acceptance, or scheduling
behavior may read this context.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/SCOUT-20260908-P0-SESSION-JOIN.md` → `.memory/phase2-hicache-design/work/SCOUT-20260908-P0-SESSION-JOIN.md`; SHA256 `6f4059a1ff685533f1c9b1f03c460f01996412b7dec5507894d3b3f7e221529d`; source state `tracked`
