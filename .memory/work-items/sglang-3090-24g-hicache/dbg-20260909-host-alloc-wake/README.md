# DBG-20260909-HOST-ALLOC-WAKE

- **工作标题：** DEBUG-20260909-HOST-ALLOC-WAKE
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260909-HOST-ALLOC-WAKE.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEBUG-20260909-HOST-ALLOC-WAKE.md`：**
The live bundle has already fixed the *classification* defect: a positive
54,976-token storage hit whose cache-mode host allocation fails becomes
`revoked_alloc_failed -> DENIED_ALLOC -> WAIT_CAPACITY/HOST_ALLOC`, not a
storage miss.  It has **not** proved that the required full host span becomes
available before T13.
The remaining liveness gap is narrower than the dispatch premise:
1. The active `capacity_wake_applies()` **does include `HOST_ALLOC`**.  The
   older source that excluded it is a timestamped remote backup, not the
   deployed file.  Therefore changing that enum membership is neither the
   missing fix nor an explanation of this run.
2. `_reconcile_restore_states()` does run the HOST_ALLOC predicate every
   scheduler pass.  It did not issue a later retry because its active
   predicate requires both no prefetch-rate limit and
   `mem_pool_host.available_size() >= full_requested_span`.  For q/x/w this


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260909-HOST-ALLOC-WAKE.md` → `.memory/phase2-hicache-design/work/DEBUG-20260909-HOST-ALLOC-WAKE.md`; SHA256 `b191ed962b9775575d89a2b8ed15bcbf14396bc8a008f306e6629da6b3df20c3`; source state `tracked`
