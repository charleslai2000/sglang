# DEBUG-20260908-P0-R3-V3-GAP

- **工作标题：** DEBUG-20260908-P0-R3-V3-GAP
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260908-P0-R3-V3-GAP.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/DEBUG-20260908-P0-R3-V3-GAP.md`：**
R3 is not using a stale V2 deployment, and its durable-trace marker is active. The direct cause of the all-V2 event stream and the vehicle wait is a **runtime configuration/instrumentation activation gap**: the live engine was launched with `enable_session_radix_cache=false`. The V3 context path refuses to create a context without a scheduler-assigned `session_generation`; the scheduler only assigns that generation for a top-level `session_id` when session-radix cache is enabled. Consequently every durable record has no attached context, falls back to `p0_durable.v2`, and cannot produce a keyed V3 durability barrier.
The vehicle is correctly waiting: it rejects all 405 events at its schema gate before any session state can advance.
There is also a separately confirmed contract gap that will remain after configuration correction: no product-side `build_complete` V3 emitter was found, while the vehicle requires that event to establish its ordered build identity. Thus enabling the runtime flag is necessary to expose V3 contexts/barriers, but it is not by itself sufficient for this vehicle to issue a warm request.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260908-P0-R3-V3-GAP.md` → `.memory/phase2-hicache-design/work/DEBUG-20260908-P0-R3-V3-GAP.md`; SHA256 `108161f1d612e646b1f21bbb1880c60ce2e7bcb1eab15a695584af2eedb0dcf2`; source state `tracked`
