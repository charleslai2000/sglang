# phase2-hicache-design-tester-fallback-e1

- **工作标题：** phase2-hicache-design-tester-fallback-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-fallback-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-tester-fallback-e1.md`：**
The patch is verified correct and 3090-verification ready. Diff review and
semantic review per the frozen adjudication:
- C1: resume_len comes from rank-synced `operation.storage_hit_count`
  (confirmed: prefetch_thread_func all-reduces MIN across ATTN groups at
  cache_controller.py:1332-1337; `_try_alloc_storage_hit` truncates hash_value
  and sets storage_hit_count=alloc_len at line 3515-3516), not per-rank
  extra_pool_hit_pages. The extra_pool_hit_pages test (rank zero-fetched still
  resumes) guards this.
- C2: single clamp `min(completed, usable)` (line 2803) flows to fetched_key/
  insert_host/host_indices/hash_value/commit/`prefetch_loaded_tokens_by_reqid`
  -- all same resume_len, no fork.
- C3: fallback success path returns before the discard block; no
  invalidate_beyond, no host release of fetched KV (L3 beliefs preserved).
- C4: `prefetch_loaded_tokens_by_reqid[req_id] = loaded_from_storage` = resume_len

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-fallback-e1.md`：Independent verification of the P2-Mamba partial-restore fallback patch
(`hicache_partial_restore_fallback` flag, default off). Performed on branch
`3090-24g-hicache`, repo
`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache`, venv
`/home/charles/sglang-venv/bin/python`. No trust of coder self-tests; all
re-run independently.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `_check_hybrid_prefetch_result` (line 2893) now returns `tuple[bool, int]`.
    Fallback branch (line 2951-2997): gated on
    `hicache_partial_restore_fallback and host_memory_mode != "buffer_only"`;
    `resume_len = min(completed_tokens, operation.storage_hit_count)` (line…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-fallback-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-fallback-e1.md`; SHA256 `15f59e44f4a167eb8f329bc6d52cffa84e3decf0a3307a60b9e08f3b14e448f6`; source state `tracked`
