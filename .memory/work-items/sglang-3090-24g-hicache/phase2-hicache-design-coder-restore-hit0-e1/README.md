# phase2-hicache-design-coder-restore-hit0-e1

- **工作标题：** phase2-hicache-design-coder-restore-hit0-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-restore-hit0-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** B primary (1949/1951), C secondary (2/1951), A ruled out.

**`phase2-hicache-design/work/phase2-hicache-design-coder-restore-hit0-e1.md`：**
The dominant defect behind "958/958 durable-L3 KVs return storage_hit=0" is
**not** a write/read key mismatch (A) and **not** a Mamba sidecar TRAILING
fold of otherwise-present KV (C, only 2/1951). It is **B**: the extent
backend's watermark GC evicts committed keys before the restore query reads
them, because the aggregate logical write volume (~232GB across the gate2
run) exceeds the configured `max_size` budget (20G) by ~11.6x.
Code path (B): `_write_pages` (extent_file_backend.py:826) →
`_gc_evict` (:860) → `_allocator.evict_slot_lru()` (extent_allocator.py:174)
→ `_drop_slot` (generation++ + index entry removal). Query side:
`HybridCacheController._storage_hit_query` (hybrid_cache_controller.py:599)
→ `batch_exists_v2` (:618) → `_allocator.lookup(self._storage_key(key))`
(:628) returns None on the GC'd key → `kv_pages=0` → `sidecar_hits={}`.
C (secondary, 2/1951): same `batch_exists_v2`, mamba TRAILING scan (:648-668)
boundary=0 when the 51.5MB mamba checkpoint for the last page was GC'd →

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-restore-hit0-e1.md`：Root-cause analysis only — **no production code changed**. Read 3090 FBE-rerun
evidence over SSH (`root@175.155.64.171 -p 24052`, evidence
`/root/evidence-gate2-fbek{4,8,16}/`, engine logs
`/root/engine-gate2-fbek{4,8,16}.log`, extent file
`/data/l3/p2io-gate2-fbek16/hicache.data_qwen3.5-9b-gptq_0_1`) plus local
`3090-dev/evidence/gate2-k{4,8,16}/` and the gate1/gate2 reports.
Verdict: **B primary (1949/1951), C secondary (2/1951), A ruled out.**
- **B root cause = extent backend watermark GC eviction of committed keys.**
  `ExtentFileBackend._gc_evict` (extent_file_backend.py:860-889, watermark
  `used_bytes > max_size × eviction_ratio` = 20G×0.9 = 18G) evicts LRU slots…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-restore-hit0-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-restore-hit0-e1.md`; SHA256 `827be99368e69ffeaaedb95eb5e383819985e4cbc04a8c2cb77ea7dce4524ace`; source state `tracked`
