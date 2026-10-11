# READ-ONLY capacity accounting + root-cause adjudication of the production Mamba L2

- **工作标题：** P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918.md`：**
HOST_ALLOC tail. Decide exactly one of (A) capacity insufficient, (B) split-ratio wrong,
(C) allocator reclaim/lifetime bug, and name ONE minimal lever. Enforce unit discipline on
`required 3436-3556` (corrected: 484-65347) vs `free_before=0` vs
`hicache_mamba_host_usable_tokens=142`.
Scope: read-only code + log investigation against the frozen prod tree
`/opt/sglang/local-prod-v1.2.1-candidate` (source_head `4f41f5bab562b99562f30c67540eb05344d13637`,
deployment_manifest_digest `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d`,
SGLANG_RUN_ID `prod-20260917T211800Z-1653969`) and worktree HEAD

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** (C) allocator reclaim / lifetime bug.; DONE

**`phase2-hicache-design/agents/P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918.md`：**
**Verdict: (C) allocator reclaim / lifetime bug.** Not capacity, not split ratio.
**Single minimal lever:** fix the **mamba host-pin lifetime** — the host-lock pin acquired when an
L3 backup op is submitted and released only on its ack drain. Decisive line (prod tree, = worktree):
```
src/python/sglang/srt/mem_cache/unified_radix_cache.py:5006
        self.ongoing_backup[operation_id] = (
            node_id,
            self.inc_host_lock_ref(node_id).to_dec_params(),
        )
```
Release exists only on ack drain (`:7135`) / storage-failure (`:7971`) / detach
(`storage_attachment.py:395-399`). No in-run watchdog releases a pin whose ack never drains, so a
pinned mamba host node is never evictable again.
**Coupled secondary defect (does not change the verdict, must not be conflated with the lever):**


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918.md` → `.memory/phase2-hicache-design/agents/P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918.md`; SHA256 `fa3f22b385164093ae23d0bb108638f38ff92700eead64ea42fc264899f9c890`; source state `tracked`
