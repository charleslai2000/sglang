# DBG-20260909-POST-GUARD-CAPACITY

- **工作标题：** DEBUG-20260909-POST-GUARD-CAPACITY
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260909-POST-GUARD-CAPACITY.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEBUG-20260909-POST-GUARD-CAPACITY.md`：**
`5b61e63993` did what it was intended to do: no request in the post-seed
batch reached a cropped Mamba sidecar boundary.  The four remaining failures
are instead two separate availability/state-machine faults.
1. **R2_q/R2_x are valid, full-frontier L3 hits that fail host allocation.**
   The guard refuses the only available arbitrary crop, then the cache-mode
   path classifies a positive (`54,976`) hit as `revoked_miss`.  Scheduler
   consumes that as a *genuine L3 miss* and recomputes.  q's in-flight
   prefetch fills the physical prefetch budget; x is correctly woken when q
   releases it, but x then fails the same host allocation.  Thus the budget
   wake is present; it is not the terminal defect.
2. **R2_y/R2_z have a resident 54,976-token prefix and only a 24-token
   suffix.**  There is no L3 query to revalidate.  `declined_too_short` is a
   terminal statement about that current suffix, but the scheduler admits a
   `WAIT[REVALIDATE]` device-match-decay bet.  It repeats the same decline 121

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG-20260909-POST-GUARD-CAPACITY.md`：- Remote source (read-only):
  `/root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py`,
  `hybrid_cache/hybrid_cache_controller.py`,
  `managers/scheduler.py`, and
  `managers/scheduler_components/hicache_restore.py`.
- Remote logs (read-only):
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log` and
  `/tmp/t38c-probe.log`.
- Read prior reports: `DEBUG-20260909-MAMBA-FILE-MISMATCH.md`,
  `CODE-20260909-HYBRID-FRONTIER-GUARD.md`,
  `REVIEW-20260909-HYBRID-FRONTIER-GUARD.md`,
  `TEST-20260909-P4-FRONTIER-GUARD.md`, and
  `OPS-20260909-MAMBA-INVENTORY.md`.
- No product code, runtime process, storage, service configuration, or 3090

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260909-POST-GUARD-CAPACITY.md` → `.memory/phase2-hicache-design/work/DEBUG-20260909-POST-GUARD-CAPACITY.md`; SHA256 `6ab3b50655409849f35d999bb8179aef66177b60e0a9750c9a9cc1613c5156f3`; source state `tracked`
