# P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE

- **工作标题：** P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md`：**
`t_feasible` timeline. No product code changed; read-only inspection.

## 实际改了什么
只读检查 `scheduler.py` 的 `_host_alloc_wait_eligible` 与 cache generation 更新路径，以及 R121 观测；未改产品源码。

## 生成结果与验收
- **原报告状态：** SUPPORTING-EVIDENCE ONLY (not a verdict). Decisive proof requires R123's

结论仅为 supporting evidence / hypothesis：wake eligibility 要求每个 blocked domain generation 均推进，但该 pool generation 仅在自身 evictable signature 改变时更新；R121 有一次 mamba requirement 已够、generation 未动而 wait 被 hold 的记录。若 R123 `t_feasible < t_deadline` 能证明 KV 可行期间因无关 Mamba epoch 被阻塞，才可判 genuine liveness defect。本 note 本身不是 verdict，不能外推为产品缺陷确认。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md` → `.memory/rh-p1-durable-replay-eviction/P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md`; SHA256 `1b40782d1e4601591d919fe232db98ae5653a3684fb5324b5f91def7ba2bd211`; source state `tracked`
