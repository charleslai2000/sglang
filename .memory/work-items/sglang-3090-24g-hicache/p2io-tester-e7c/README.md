# p2io-tester-e7c

- **工作标题：** p2io-tester-e7c
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7c.md`：**
done — **结论：NO_L3_FULL 主导**（L3 无完整长链 + 链从未在 RH 期间补齐，recompute 92% never-hit）；NO_HEADROOM 为次要约束；CAUSAL_BLOCKED 不可见但非主因。**需补 decline 分类埋点才能最终定案**（见建议）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e7c.md`：**
**因果账判定：NO_L3_FULL 主导。**
决定性证据链：
1. **L3 无完整链是根本**：93 个候选 rid 仅 10 个首次 full（10.8%），48 partial、35 nohit；最终 recompute 的 78 rid 里 **72 个（92%）从未拿到 storage_hit==requested**——链在 L3 根本未完整存在。
2. **RH 不是破坏者**：三时点 73/75 stuck + improve 仅 2 + dropped 0——RH 活动期间链既没被补齐也没被降级，完整链生态的"缺失"是入队时就存在的（首次 prefetch 已非 full），非 RH 造成。
3. **headroom 是次要约束，非第一原因**：ready_stage 全 issued（无 headroom 阻塞），headroom 小只限制了单次能 stage 的链长（issue p50=27811 > headroom p50=1750），导致 partial（48 rid），但真正卡死的是 L3 里这些超长链没有完整数据。
4. **CAUSAL_BLOCKED 不可见**，但推理上非主因：即使取消 epoch/negative-cache 抑制，被 stage 的 candidate 也多为 partial（51%），full 率不升——M3 门不是"池填不起来"的原因。
**NOT**：NO_HEADROOM 单独主导（headroom 未阻止 ISSUE）；NO_L3_FULL + NO_HEADROOM 两者都不主导时才有 CAUSAL_BLOCKED 空间——此处 NO_L3_FULL 明确主导，headroom 掺和限制规模层面。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e7c.md`：- 数据源：`/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（6736 行，e14 M3 重做后 run-20260901-115548）
- 事件总账：restore_state=1361 / prefetch_issued=481 / prefetch_revoke=345 / restore_recompute=348 / restore_retry=323 / ready_stage=162 / io_finished=136 / ready_pool=112 / frontier_wait=46 / frontier_wake=33 / restore_ready=136
- 分析：会话内联脚本（行级正则，无跨距）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7c.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7c.md`; SHA256 `a878eadb2bd45c3fa2c14102a2d3982823fe819c76d4eac65be6efd530b3fc37`; source state `tracked`
