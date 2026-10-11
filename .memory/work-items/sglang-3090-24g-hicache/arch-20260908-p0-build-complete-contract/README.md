# ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT

- **工作标题：** ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
定义 P0 durable V3 的 `build_complete` 生产契约：在 radix 插入成功、最终节点和节点侧身份绑定已核验后，记录逻辑 build identity；明确事件与后续 KV/Mamba durability、residency、HTTP 完成及多 rank 完成之间的语义边界，避免消费者自行制造 build 证据。

## 实际改了什么
这是只读架构工作。报告的唯一写入是本架构备忘录；没有修改产品代码、测试、launcher、vehicle、gate、ledger 或远端产物。报告建议后续实现最小范围为 `python/sglang/srt/mem_cache/unified_radix_cache.py`，可选授权测试 `3090-dev/test_p0_trace_context_v4.py`，但这些是建议范围，不是本工作已改文件。

## 生成结果与验收
交付 `phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`。契约建议仅对 marker 开启且成功完成的 radix-native 首次 build，在最终非 root 节点、V3 context 绑定读回一致且 `req.rid` 匹配 build RID 时发出 `p0_durable.v3/build_complete`。事件表示 cache build 已提交并绑定节点身份；不代表持久化、驻留释放、HTTP 完成或全 rank 完成。架构报告明确由 orchestrator 决策，不构成实现授权或 gate 验收；实现准入/最终接受状态未由该报告确认。

### 报告列出的产物/证据
- 唯一报告产物：`phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`。
- 报告明确未改产品、launcher、vehicle、gate、ledger 或远端产物；没有运行测试或运行时验收结果。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md` → `.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`; SHA256 `2ba65c3f6bbc543c5978caa3abc7b9d78515231006287216d6192adfc5b75cce`; source state `tracked`
