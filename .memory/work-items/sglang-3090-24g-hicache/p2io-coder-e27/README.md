# p2io-coder-e27

- **工作标题：** p2io-coder-e27
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e27.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e27.md`：**
- The storage hash-chain (write `node.hash_value` vs query rebuilt `get_hash_str`) is **provably identical** on every page for all live shapes: single 2048-node, 4096 cross-batch, radix split, growth 1024->2048, live continuation-from-anchor. No divergence at 1024/1027.
- The only "divergence at 1024" found was a probe artifact (wrong seed). There is no cross-batch seed-reset mechanism in `_storage_hit_query` or `_page_backup` — the chain is position-continuous by construction.
- Therefore `storage_hit=0` is NOT a chain-generation bug in the UnifiedRadix layer either. The remaining live-side suspects: the backend scans ONLY the freshly reconstructed suffix `keys` (both `batch_exists`/`batch_exists_v2` IGNORE `prefix_keys`), so the storage hit is capped at what `get_hash_str(new_input_tokens, anchor.last_hash)` finds — the query-span/anchor-selection mismatch (prefetch `new_input_tokens` slicing, or the anchor not covering the written pages) is the only layer left.
- Permanent test added guarding the invariant (4096 pages + cross-1024 batch + split).

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e27.md`：- `test/registered/unit/mem_cache/test_storage_hash_chain_invariant.py` (NEW, untracked): permanent unit test for the storage hash-chain invariant. Guards that the query-side rebuilt hash chain equals the write-side `node.hash_value` chain page-by-page, across the STORAGE_BATCH_SIZE(1024) boundary and across a radix split, for 2048/4096-page prefixes. Uses the e7k oracle (`p2io_refhash`, native-verified 20/20) patched over `get_native_hash` so the test is deterministic on CPU-only CI (no C++ toolchain needed).…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e27.md` → `.memory/phase2-hicache-design/work/p2io-coder-e27.md`; SHA256 `9ae7774da488d0be6297c3f4f5a003d322494243e8f967ef0c716a853d4ed1d3`; source state `tracked`
