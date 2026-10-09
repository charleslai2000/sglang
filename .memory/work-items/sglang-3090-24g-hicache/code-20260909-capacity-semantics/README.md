# CODE-20260909-CAPACITY-SEMANTICS

- **工作标题：** CODE-20260909-CAPACITY-SEMANTICS
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-CAPACITY-SEMANTICS.md`：**
invocation_status: done
admission: ACCEPT
task_id: CODE-20260909-CAPACITY-SEMANTICS
orchestration_epoch: 20260909-P4
role: coder
branch: 3060-12g-qwen35-4b
commit: 93e6f54871547f237b515f4e3b9c8bc7c489a692

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-CAPACITY-SEMANTICS.md`：**
Defect A: a positive storage hit whose complete validated host staging
allocation fails now uses the explicit `revoked_alloc_failed` terminal outcome
and feeds the existing `DENIED_ALLOC` / `WAIT[HOST_ALLOC]` transition. Revoke
still releases the prefetch reservation and staged resources, so the request
cannot block its own capacity wake. The wake checks availability for the
complete page-aligned requested span and retains the existing bounded timeout;
the existing `_storage_hit_crop_is_safe` guard and all-or-nothing discard
behavior are unchanged.
Defect B: when a device-resident historical prefix has no host restore
material and only a page-aligned suffix below the prefetch threshold remains,
the scheduler consumes the retry marker and uses the existing `DENIED_SHORT`
transition with an explicit immediate tail-admit judgment. The prefix remains
in `prefix_indices`, so only the suffix is recomputed and the request does not
enter the `REVALIDATE` busy loop. Other too-short cases retain their prior

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE-20260909-CAPACITY-SEMANTICS.md`：Changed files in commit `93e6f54871`:
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
- `3090-dev/test_hicache_restore.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- `3090-dev/test_drain_reentry.py`

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `93e6f54871`, `93e6f54871547f237b515f4e3b9c8bc7c489a692`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-CAPACITY-SEMANTICS.md` → `.memory/phase2-hicache-design/work/CODE-20260909-CAPACITY-SEMANTICS.md`; SHA256 `229b10ca02b82f6a0e3045952ed2083c380a9753ecac87649cac07d36efb0bdc`; source state `tracked`
