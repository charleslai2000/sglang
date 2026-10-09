# P1-R122-HEADROOM-GATE-ADDENDUM

- **工作标题：** P1-R122-HEADROOM-GATE-ADDENDUM
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md`：**
- Applies to `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122`, binding ADDITIVE
to `work/R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
(sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`,
unmodified). Where they differ, THIS addendum governs the host-capacity gates.
- User ruling (2026-09-11): the R121 core causal chain is proven; the only
remaining P1 gate is whether host staging capacity is available AT THE CORRECT
TIME. A single pre-window `F1+T+margin` gate is WRONG because F1's stage may
still hold host slots, and because `F1+T > host_allocable` is structurally

## 实际改了什么
冻结的 user-ratified binding addendum：为 R122 规定双时点顺序 Gate A（F1 staging 前）/Gate B（T wake 后、T staging 前）与 sequential chain；它是合同文本，不是代码实现或运行结果。该版本后被独立正式 invalidation：pool measurement basis 错误，原文保留供审计，不可用于 HOST_ALLOC capacity claims。

该文件记录冻结的 gate 设计及后续 invalidation 状态，不是实验报告或验收结果；具体 v2 correction 和正式 invalidation 见关联卡。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md` → `.memory/rh-p1-durable-replay-eviction/R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md`; SHA256 `92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`; source state `tracked`
