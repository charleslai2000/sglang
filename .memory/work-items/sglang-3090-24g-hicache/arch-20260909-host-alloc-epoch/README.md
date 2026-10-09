# ARCH-20260909-HOST-ALLOC-EPOCH

- **工作标题：** ARCH-20260909-HOST-ALLOC-EPOCH
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`：**
The proposed contract makes the cache mutation boundary the sole owner of a
monotonic primary-host allocability generation and separate required
auxiliary-pool generations. It requires bumps after successful direct KV
frees, completed queued KV release drains, and host lock releases that change
primary evictable leaves/amount; it explicitly forbids bumps on failed alloc,
reservation release, scheduler polling, or unrelated epochs.
A HOST_ALLOC waiter captures a post-cleanup generation vector with exact
failed resource domains and holds no prefetch reservation. A scheduler-owned
FIFO arbiter grants at most one global retry for each newly observed relevant
generation vector. The retry uses the existing bounded full-span
`alloc -> evict -> alloc` authority, never arbitrary crop, miss
classification, or lower-checkpoint inference. Failed retries snapshot all
self-generated frees before parking, preventing self-spin. KV and Mamba/other
auxiliary domains are independent, and hybrid READY still requires complete

### 报告列出的产物/证据
- `phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`：- Versioned proposed gate contract:
  `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md`
- This specialist report:
  `.memory/phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`
No product code, remote host, storage, or 3090 path was modified.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md` → `.memory/phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`; SHA256 `3b69a61fbbe608133c1c9ae4721325fd4cd15413f3ed82defb671a1b00bba944`; source state `tracked`
