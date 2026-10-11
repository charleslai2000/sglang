# GATEA-CLOSURES-REVIEW-20260917

- **工作标题：** GATEA-CLOSURES-REVIEW-20260917
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/GATEA-CLOSURES-REVIEW-20260917.md`：**
Independently and adversarially validate the harness-only Gate-A/F1 closures under
`3090-dev/gates/production/`: (1) target-scoped drop predicate, (2) F1 relocation-destination
reserve preflight, (3) required pre-assertions return INVALID not FAIL and are proven without
re-warming the graded target. Every mandatory item A–I must end PROVEN-SOUND or a NAMED DEFECT.
The disqualifying failure class is **false-PASS** (a real graded-target durable page/ref loss
reported PASS); false-INVALID (conservative over-blocking) is acceptable if labeled.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** APPROVE-WITH-CONDITIONS; DONE

**`phase2-hicache-design/agents/GATEA-CLOSURES-REVIEW-20260917.md`：**
The closure is substantively correct and fail-closed on the cases I could reach: hashes match,
diff is confined, the decorative boolean is gone, CPU tests pass on the real functions, the F1
reserve preflight precedes the measured request, and the preserved r2 console independently
replays to `refs_intact=False -> INVALID`. I found **no confirmed, reachable false-PASS**.
I found one real permissiveness of ≤1% (inherited threshold reused for a predicate whose stated
standard is "ANY loss"), one falsified soundness claim (node-id ordering bound), one stale-evidence
call site (F1 cold window), and two latent fail-open traps. These are named below with conditions.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/GATEA-CLOSURES-REVIEW-20260917.md` → `.memory/phase2-hicache-design/agents/GATEA-CLOSURES-REVIEW-20260917.md`; SHA256 `2b2c3ffcc898a88f50a015b46f9f5bad2b706abdd036580f691704aebebf02e6`; source state `tracked`
