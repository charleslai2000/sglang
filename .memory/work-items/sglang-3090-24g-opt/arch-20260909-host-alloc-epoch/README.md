# ARCH-20260909-HOST-ALLOC-EPOCH

- **工作标题：** ARCH-20260909-HOST-ALLOC-EPOCH
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
为 HOST_ALLOC 等待与重试定义基于 allocability generation 的因果唤醒契约，解决 KV 与辅助池资源域的独立变化、重试公平性、失败后自旋及 hybrid all-or-nothing 完成等问题，并给出实现准入和测试要求。

## 实际改了什么
这是架构设计工作。交付 proposed gate contract 和 specialist report；明确没有修改产品代码、远端主机、storage 或 3090 path。报告中提及的 scheduler、tree、allocator 等文件是分析/建议边界，不是已改文件。

## 生成结果与验收
契约建议由 cache mutation boundary 维护 primary-host 与所需 auxiliary-pool 的单调 generation；仅成功释放或改变可驱逐资源的边界推进 generation。HOST_ALLOC waiter 保存 cleanup 后的资源域/generation 向量，不保留 prefetch reservation；scheduler FIFO arbiter 对每个新相关向量最多发起一次全 span `alloc → evict → alloc` 重试，拒绝任意裁剪和低 checkpoint 推断。失败重试需纳入自身释放变化再 park，避免 self-spin；hybrid READY 仍须完整原子化完成。

报告将机制判为 NOVEL_MECHANISM，并明确实现准入仍 BLOCKED：需完整 Pattern Intake / Novel Mechanism 及权威接受后才能实现，随后还需 HAE-01..15 测试、独立 review 和另行批准的 live 证据。该报告是设计交付，不是实现或运行验收。

### 交付物
- proposed gate contract：`review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md`
- specialist report：`phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH-20260909-HOST-ALLOC-EPOCH.md` → `.memory/hicache-l3-extent-storage/ARCH-20260909-HOST-ALLOC-EPOCH.md`; SHA256 `3b69a61fbbe608133c1c9ae4721325fd4cd15413f3ed82defb671a1b00bba944`; source state `tracked`
