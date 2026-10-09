# G3-PROFILE-C-PLAN-20260908

- **工作标题：** G3-PROFILE-C-PLAN-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
把授权的 Profile C sweet-spot 评估转成单 RTX 3090 的串行 fail-closed DAG，定义 C1→C2→C3，及 C4 需独立 GO/NO-GO；每点包含启动 admission、decode、restore、独立 verify 与最终 scorecard。

## 实际改了什么
仅写 execution plan；明确没有远端命令、benchmark、service transition、download 或 product write。此前 Profile B over-capacity 作为启动 gate 的理由，不授权改变质量、graph、prefill 或 allocator flags。

## 生成结果与验收
计划给出有条件 GO：第一个 failed candidate 即停止后续点，恢复 v1 并独立核验；C4 默认不准入，须 C3 独立接受且 fresh decision 证明更高容量仍必要。锁定 workload/runner/指标/telemetry、候选容量 envelope 与证据留存方式。它是计划，不是执行记录或性能结论；后续逐阶段需要独立任务与验收。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-PLAN-20260908.md`：Observed inputs used for planning were the repository `AGENTS.md`, local G3
context/plan and handoff, the accepted Profile-B runbook, Profile-B launch/OOM
reports, and the v1 restoration report. They establish that v1 restoration is
possible, that B failed before traffic during graph capture, and that admission
must prove allocations and effective capacities from actual process/server
evidence.
No product files, ledger, context, plan, remote artifacts, or service state were
changed. The only artifact produced by this invocation is this report:
`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/G3-PROFILE-C-PLAN-20260908.md`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-PLAN-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-PLAN-20260908.md`; SHA256 `b96a58aec8d4c128b3a9f12793be685f5b8a89d542a80d11c664ab009ff6ffe5`; source state `local-only`
