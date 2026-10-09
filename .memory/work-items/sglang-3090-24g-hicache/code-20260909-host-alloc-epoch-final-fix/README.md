# CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX

- **工作标题：** CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX.md`：**
ENTRY: ACCEPT
status: done
Task ID: `CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX`
Orchestration epoch: `20260909-P4`
Branch: `3060-12g-qwen35-4b`
Commit: `ebaf9e5c49` (`fix(hicache): close host alloc epoch follow-up findings`)

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX.md`：**
- F-03: effective `lock_release_evictable` signature changes now advance the pool generation exactly once even when returned units are zero; telemetry serializes numeric zero values. Unchanged lock releases remain no-ops. Existing generation tests cover zero direct-free, effective direct-free, and changed-signature behavior.
- F-07: auxiliary staged transfers are released before the HOST_ALLOC failure snapshot is captured. The cleanup path records the post-cleanup generation boundary, clears owned transfer handles, and the scheduler arbiter regression verifies that the same RID cannot wake from its own cleanup generation.
- F-06: HOST_ALLOC telemetry now carries the required request/cache/trace identity, attempt IDs, monotonic and wall timestamps, generation vectors, wait deadlines, per-pool required/free/evictable values, failed domains, and retry outcomes. `restore_hybrid_finalize` emits KV and per-sidecar expected/fetched values plus all-or-nothing and terminal state. Wake-decision telemetry is coalesced by RID/attempt/generation signature, capped for repeated holds, and bounded by key-map eviction; it remains observational and is not used by fit or wake authority.
- F-08: `HostPoolGroup` always frees owned slots first; the callback is optional observation. A callback-absent rollback regression was added.
- Cleaned the verified 3090-dev fixture gaps for `_t38c_residency_lock`, the two-value digest API, fake tree component-device lookup, and the adjacent current API surfaces required for the fixture to execute. No production 3090 files were changed.…（节选；见来源报告）

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX.md`：Changed and committed only the authorized 3060 product/test files:
- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/pool_host/group.py`
- `3090-dev/test_drain_reentry.py`
- `3090-dev/test_hicache_restore.py`
- `test/registered/unit/managers/test_hicache_host_allocability.py`
- `test/registered/unit/mem_cache/test_mem_pool_host.py`
Pre-existing untracked `.memory/`, `review/gates/`, and `storage/` artifacts in the 3060 repository were not staged or modified by the commit.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `ebaf9e5c49`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX.md` → `.memory/phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX.md`; SHA256 `d96869632d91b6c413045aa09c96cbae3b75c6798a7d8e9ed6ac542bcc0b04fc`; source state `tracked`
