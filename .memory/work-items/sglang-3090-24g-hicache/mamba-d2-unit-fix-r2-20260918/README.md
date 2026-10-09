# MAMBA-D2-UNIT-FIX-R2-20260918

- **工作标题：** MAMBA-D2-UNIT-FIX-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-D2-UNIT-FIX-R2-20260918.md`：**
Replace the botched D2 WAIT_CAPACITY unit-mismatch fix. Reconcile the ACTUAL bytes on
disk (do not trust prior reports), express `required_aux_units` for the failing aux pool in
REAL HOST SLOT units — never a prefix-token count, never a forced 0 — add non-vacuous
regression tests that fail under both wrong behaviors, and delete the vacuous
`tests/unit/test_mamba_unit_fix.py`.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-D2-UNIT-FIX-R2-20260918.md`：**
**The D2 producer is now unit-correct.** The failing auxiliary pool's requirement is the
REAL host-slot demand captured at the allocator's reclaim seam and is compared against
`free + evictable` slots by an unchanged scheduler consumer.
Design (all in `unified_radix_cache.py`):
1. `evict_host(num_tokens, component_type)` now records `num_tokens` per component before
   running the eviction walk (`_note_host_alloc_reclaim_enter` /
   `_note_host_alloc_reclaim_exit`, depth-guarded first-write-wins). This is the
   authoritative slot demand because `MambaComponent.prepare_prefetch` calls
   `host_pool_group.alloc(1, pool=MAMBA, reclaim=lambda size: cache.evict_host(size, MAMBA))`
   and `SWAComponent.prepare_prefetch` calls `alloc(num_tokens, pool=SWA, reclaim=...)`;
   `HostPoolGroup.alloc` (pool_host/group.py:108-127) invokes `reclaim(need_size)` on
   alloc failure. Capture happens before the buffer-mode early return so it is always
   recorded.
2. Site A (`prefetch_from_storage`) builds `required_aux_units` via the new

### 报告列出的产物/证据
- `phase2-hicache-design/agents/MAMBA-D2-UNIT-FIX-R2-20260918.md`：All commands run CPU-only with `/opt/sglang/local-prod-v1/env/bin/python`,
`CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`, in
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-D2-UNIT-FIX-R2-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-D2-UNIT-FIX-R2-20260918.md`; SHA256 `fc3648d0a462aa10d3bc9bcf219d9fa1a799e8d5272c3fe37e915fa87d4b945c`; source state `tracked`
