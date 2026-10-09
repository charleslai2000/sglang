# p2io-coder-e23

- **工作标题：** p2io-coder-e23
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e23.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e23.md`：**
Node 104 is a host-only L3-durable restored anchor orphaned by `drop_subtree_no_host`: the e16 tombstone-skip in the descendant walk `continue`d on a forced-miss tombstone, skipping the tombstone's whole subtree, so a live host-only child under it (never detached by `detach_miss_dropped`, or re-attached) survived in the arena with all four host registrations but unreachable from the root — firing the node-104 shutdown sanity check. Fix: still descend into the tombstone's children (free + deregister them) while skipping the dead node itself, then deregister the tombstone. RED→GREEN demonstrated on a node-104-shape repro; zero e16/e17/Z3/reserve/RH/instrumentation regression.

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e23.md`：- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py` — `drop_subtree_no_host` descendant walk fixed.
  - Before: a descendant with `forced_miss_tombstone=True` hit `continue`, skipping the tombstone's ENTIRE subtree. If the tombstone still carried live host-only children (a subtree never detached by `detach_miss_dropped`, or re-attached), those children were orphaned when the drop root was removed: they stayed in the arena + `evictable_host_leaves` + `full_host_duplicates` + aux-mamba `host_lru_lists` while becoming unreachable from the root → node-104 shutdown sanity shape (`H-leaf extra / Duplicate ghost / stale host_leaves / mamba host LRU`).…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e23.md` → `.memory/phase2-hicache-design/work/p2io-coder-e23.md`; SHA256 `0c67a53a638dbbc0e9e2442a89a7d11ecaceb17f87852315fb7ae71ff406cc45`; source state `tracked`
