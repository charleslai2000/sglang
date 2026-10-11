# DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING

- **工作标题：** DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md`：**
- Task ID: `DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING`
- Epoch: `phase2-hicache-design / 2026-09-08`
- Scope: read-only source and remote r12 evidence; this report is the only write.
- Snapshot boundary: r12 was still running. The remote trace was stable at approximately 1,386,369 r12 records when inspection stopped at the orchestrator's request.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md`：**
r12 does **not** provide valid cold-residency evidence for the strict vehicle gate. It proves that many individual allocator frees returned, but it contains no product-authored, exact-identity `residency_barrier` transition for any target. Under the frozen design, a client/vehicle must not synthesize that transition from `residency_free_complete` records. The minimal next action belongs to the **product emitter owner**: repair/complete product emission of the existing `residency_barrier` event after its authoritative keyed-detach/completion fold succeeds. A vehicle-only mapping change would both violate the frozen producer boundary and accept records that cannot make the required exact identity join.

### 报告列出的产物/证据
- `phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md`：- Local vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`.
- Local producers: `python/sglang/srt/mem_cache/unified_radix_cache.py`, `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`, and `python/sglang/srt/mem_cache/trace_context.py` in the authorized opt worktree.
- Remote raw trace: `root@175.155.64.171:24052:/tmp/t38c-probe.log`, filtered by the stated r12 run ID.
- Remote live bundle: `root@175.155.64.171:24052:/root/evidence-gate3-parked/p0-s25-v43-churn-fix1-live-r12/vehicle`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md` → `.memory/phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md`; SHA256 `23b72474454ced88d00bc143df744bde169a028dec0147c6e04a2d1c55135cb3`; source state `tracked`
