# phase2-hicache-design-coder-fallback-e1

- **工作标题：** phase2-hicache-design-coder-fallback-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-fallback-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-fallback-e1.md`：**
Implemented the Mamba/KV-granularity partial-restore fallback under the new `hicache_partial_restore_fallback` server arg. The core decision change is in `_check_hybrid_prefetch_result`: instead of all-or-nothing discard (usable=0) on a Mamba/SWA sidecar shortfall, a cache-mode fallback resumes at the rank-synced `operation.storage_hit_count` (the nearest node-tail checkpoint the extent backend's TRAILING reverse-scan already returned) and only the missing suffix is recomputed. The single clamp `completed_tokens = min(completed_tokens, usable_tokens)` in `_handle_prefetch_result` keeps the insert, host-node chain, sidecar commit and loaded-token marker on the SAME resume_len (C2/C4). The fallback path skips `invalidate_beyond` and the host-mem release (C3), so the KV beyond the boundary stays valid in L3. Off, and buffer_only mode (C8), stay byte-for-byte identical to upstream. The no-checkpoint sub-case was made to fall through to the shared discard cleanup rather than early-return, closing a prefetch-leak I caught while writing the tests.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-fallback-e1.md`：- `python/sglang/srt/server_args.py` — added `hicache_partial_restore_fallback: bool = False` (NS("memory")) with full help text. Off = byte-for-byte upstream all-or-nothing discard.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `init_hicache`: `self.hicache_partial_restore_fallback = server_args.hicache_partial_restore_fallback` (read once at init).…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-fallback-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-fallback-e1.md`; SHA256 `7b3eaf1b4b1eccb885baf24fdef8cfd8e09a77feb88b1179a6cfbc9a3933d069`; source state `tracked`
