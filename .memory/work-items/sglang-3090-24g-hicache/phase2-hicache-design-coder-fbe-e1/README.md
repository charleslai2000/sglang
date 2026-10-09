# phase2-hicache-design-coder-fbe-e1

- **工作标题：** phase2-hicache-design-coder-fbe-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-fbe-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-fbe-e1.md`：**
Implemented the frozen-scope FBE invariant in
`MambaComponent.drive_host_eviction`: a mamba host victim that is not
L3-durable (and not already pinned) is spared and queued; after the walk its
`write_backup_storage` is triggered, which pins the host copy to the storage
ack, so the next eviction round skips it and only after durability (ack
release) is it evicted. This closes the gate2 HOST->L3 break hop: the mamba
sidecar is persisted before the host copy can be reclaimed. Flush is deferred
post-cursor_end to avoid a reentrant-walk cursor corruption. Minimal diff: one
file, one method; read path / BACKUP_STORAGE gate / eager persist untouched.
8 new unit tests + 175 regression tests green.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-fbe-e1.md`：- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
  (`drive_host_eviction`, :849-936): added flush-before-evict (FBE) — a mamba
  host victim that is not yet L3-durable is spared this round, its node id is
  queued, and after the walk `self.cache.write_backup_storage(node_id)` is
  called (which pins the host copy to the storage ack). No other production
  file changed.
- `3090-dev/test_fbe_flush_before_evict.py` (new): 8 unit tests driving the
  real `MambaComponent.drive_host_eviction` / `evict_component` against a real
  `UnifiedTreeCore` + real host LRU.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-fbe-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-fbe-e1.md`; SHA256 `f39234bec796b90c39c25732c9817969865244374110945677d179374f1f32dd`; source state `tracked`
