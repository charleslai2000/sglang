# REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5

- **工作标题：** REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md`：**
FIX5 repairs the FIX4 race rejection. The tailer publishes sticky parse errors
and notifies waiters while holding the same condition used by `wait_for`.
`wait_for` checks the error before and after predicate evaluation and holds the
condition through the final success decision. The prior concurrent malformed
line boundary now fails closed, incomplete fragments remain retryable, and
complete malformed records remain fatal for readiness waits.
Independent inspection found no weakening of the exact `p0_durable.v3` schema,
the `(session_id, build_rid, node_id, final_kv_hash)` identity join, ordered
KV/Mamba/durability/residency barriers, or accepted V3 emitter guards.

### 报告列出的产物/证据
- `phase2-hicache-design/work/REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md`：- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-R7-JOIN-ROBUSTNESS-FIX5.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed focused fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md` → `.memory/phase2-hicache-design/work/REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5.md`; SHA256 `cb67875cdf194e25f2139e4a0b1437a0fdf0cc55f011c54fcff12f390eb97b84`; source state `tracked`
