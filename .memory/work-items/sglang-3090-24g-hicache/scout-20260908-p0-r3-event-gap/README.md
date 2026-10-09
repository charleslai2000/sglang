# SCOUT-20260908-P0-R3-EVENT-GAP

- **工作标题：** SCOUT-20260908-P0-R3-EVENT-GAP
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/SCOUT-20260908-P0-R3-EVENT-GAP.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/SCOUT-20260908-P0-R3-EVENT-GAP.md`：**
The exact wait contract is: same-session V3 records, exact `(session_id, build_rid, node_id, final_kv_hash)`, ordered build/KV/Mamba evidence, then `durability_barrier.combined_durable=true` followed by `residency_barrier.cold_residency=true`. R3’s reported 405 probe lines and zero V3 durable lines do not meet that contract. The strongest current explanation is a V2/probe-versus-V3 event/schema mismatch, with emitter deployment/activity still unconfirmed.

### 报告列出的产物/证据
- `phase2-hicache-design/work/SCOUT-20260908-P0-R3-EVENT-GAP.md`：- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/trace_context.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
- `.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-S25-LIVE-R3.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-SESSION-BARRIER-VEHICLE.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-DURABILITY-TRACE-V2.md`
- `.memory/phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V3.md`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/SCOUT-20260908-P0-R3-EVENT-GAP.md` → `.memory/phase2-hicache-design/work/SCOUT-20260908-P0-R3-EVENT-GAP.md`; SHA256 `5644341aedb839c1829077c5aa78cb63fa5f40be656f2cc087a6634fc146b36a`; source state `tracked`
