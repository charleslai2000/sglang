# P1-TEMPORAL-DISCRIMINATION-R121

- **工作标题：** P1-TEMPORAL-DISCRIMINATION-R121
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-TEMPORAL-DISCRIMINATION-R121.md`：**
Evidence source: `work/R121-bundle/raw.log` (sha256 `2bdca1c2…cca9`), the closest
run — which DID exhibit T's park + release + wake (C1–C3 real). R123 could not
reproduce T's park at all, so it yields no temporal data; R121 does.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DECISIVE FINDING

**`phase2-hicache-design/work/P1-TEMPORAL-DISCRIMINATION-R121.md`：**
`t_feasible < t_deadline` AND T was held with `decision=hold_no_generation`
because the **mamba** generation did not advance (1853->1853) while **kv**
advanced (1229->1230) — even though mamba's requirement was already satisfiable
(free 75 >= required 1). Per the frozen rule this is:
> **PRODUCT LIVENESS FAIL** — `_host_alloc_wait_eligible`'s blocked-domain
> semantics starve a restore that is capacity-feasible.
Root cause (source, already recorded in
`work/P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md`):
`_host_alloc_wait_eligible` (scheduler.py:3716-3727) requires ALL
`blocked_domains` generations to advance; a generation advances only when that
pool's host evictable signature changes (`_bump_changed_host_allocability`,
unified_radix_cache.py:3823-3835). mamba was never a real constraint
(free 75 >= 1) yet was admitted into `blocked_domains` at
unified_radix_cache.py:6503-6519 because its sidecar hit was incomplete


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-TEMPORAL-DISCRIMINATION-R121.md` → `.memory/phase2-hicache-design/work/P1-TEMPORAL-DISCRIMINATION-R121.md`; SHA256 `a457c91c7f03ddd27604f7b51f50c52e2fe6d74ff4de523e6229f3b1d34642a9`; source state `tracked`
