# COD-20260908-P0-TRACE-CONTEXT-V4.2

- **工作标题：** COD-20260908-P0-TRACE-CONTEXT-V4.2
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V4.2.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V4.2.md`：**
- F1: Added a controller-owned release handoff lock. Marker-on producers publish
  the existing page payload and exact token together; the unified P0 drain takes
  the pair under the same lock. The exact drain has no digest fallback. Marker-off
  release behavior remains the original page FIFO path with no trace registration.
- F2: Removed `_t38c_durability_current` as an authority. Candidates remain
  keyed by node/operation/attempt, and promotion selects exactly one node/hash
  candidate. Same-hash ambiguity remains pending and emits no barrier.
- F3: Added complete context validation for session ID, non-null generation,
  build RID, node, and final hash before a barrier can be emitted. Missing context
  remains diagnostic-only.
- F4: Mamba durability now requires a non-empty ordered key set and exact
  succeeded-page count. ACK/candidate/barrier evidence includes key digest/count,
  operation/attempt identity, and rank-set metadata or `rank_set_unavailable`.
- F5: Session retirement replaces queued tokens for that session with inert

### 报告列出的产物/证据
- `phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V4.2.md`：Authorized product/test changes are limited to:
- `python/sglang/srt/mem_cache/trace_context.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `3090-dev/test_p0_trace_context_v4.py`
This report is the requested deliverable. Review reports, vehicle files, ledger,
plan, context, and the live vehicle were not modified or run.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V4.2.md` → `.memory/phase2-hicache-design/work/COD-20260908-P0-TRACE-CONTEXT-V4.2.md`; SHA256 `6d0a62eadf9456cc6c2027df10f34b33466345b6c9d1940c92119e57e645506d`; source state `tracked`
