# REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1

- **工作标题：** REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`：**
The r16 failure mode is fixed at the intended boundary: a serialized decimal
node ID can resolve the actual integer TreeCore handle, while missing,
wrong-node, and distinct int/string alias resolutions fail closed. The helper
does not alter the six-field identity tuple, parent/hash binding, queue guard,
barrier predicates, deduplication, scheduler, vehicle, or Ready Horizon
behavior. The narrow implementation gate is accepted.

### 报告列出的产物/证据
- `phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`：- Gate contract: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md
- Reviewed product: python/sglang/srt/mem_cache/unified_radix_cache.py
- Reviewed focused test: 3090-dev/test_p0_residency_barrier_emitter.py
- Inputs: coder FIX1 report, r16 evidence summary in the phase2 ledger,
  prior node-sidecar FIX1 gate/report, prior R15 debugger diagnosis, current
  source, and focused test.
The product checkout is an aggregate dirty worktree with no task-specific
commit boundary. Review attribution is path- and behavior-scoped. Product
source and tests were not modified. No SSH, remote, live, vehicle, or…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md` → `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`; SHA256 `656673e2e39db885ea2e59d2edee8186544642106807d5cacc62e496c6452016`; source state `tracked`
