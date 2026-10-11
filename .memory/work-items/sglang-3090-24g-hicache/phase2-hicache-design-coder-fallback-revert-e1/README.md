# phase2-hicache-design-coder-fallback-revert-e1

- **工作标题：** phase2-hicache-design-coder-fallback-revert-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-fallback-revert-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-fallback-revert-e1.md`：**
Reverted the P2-Mamba partial-fallback patch completely and precisely. The production logic in `_check_hybrid_prefetch_result` returns to the upstream-style all-or-nothing: a Mamba/SWA sidecar shortfall discards the whole prefetch (keep_pages computation + invalidate_beyond + host release + release_prefetch + marker=0 -> the scheduler recomputes ADMIT_RECOMPUTE). The flag, help text, init read, C2 clamp, fallback branch, patch-specific unit test, and the two mock-test adaptations are all removed. Verified the revert is byte-identical to HEAD for the test file, and functionally identical to HEAD for the reverted production regions (only P3 additions remain). Post-revert state = pre-patch state: all existing P3 regression suites green, TRAILING folding backend green, zero patch traces anywhere in python/ / 3090-dev/ / test/.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-fallback-revert-e1.md`：P2-Mamba partial-fallback patch (`hicache_partial_restore_fallback`) fully reverted to pre-patch (upstream-style all-or-nothing). Exact per-file changes:
1. `python/sglang/srt/server_args.py` — removed `hicache_partial_restore_fallback: A[bool, Arg(...NS("memory"))] = False` field + full help text (was at line 2866).
2. `python/sglang/srt/mem_cache/unified_radix_cache.py`
   - `init_hicache` (~:549-557): removed `self.hicache_partial_restore_fallback = server_args.hicache_partial_restore_fallback` + its P2-Mamba comment block.…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-fallback-revert-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-fallback-revert-e1.md`; SHA256 `c4889d1b331f210f234a42c82ec11d1f821a0949931edf1426c365ce4066e1b5`; source state `tracked`
