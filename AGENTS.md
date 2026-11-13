## Work Areas

* `control/` — manage Goals, Plans, Tasks, current frontier, and cross-session integration; do not perform substantial professional work here.
* `design/` — develop and maintain architecture, proposals, and confirmed design decisions.
* `review/` — independently review an explicitly assigned claim, deliverable, or stage; review is not a mandatory workflow step.
* `experiments/` — create new empirical evidence through controlled experiments, benchmarks, reproductions, or prototypes.
* `ops/` — manage runtime environments, services, deployment, infrastructure, operational procedures, and material operational records.
* `research/` — investigate and synthesize existing evidence and external sources; create an experiment when new measurements are required.

Ordinary implementation, debugging, and direct verification remain repo-root work unless a more specific directory instruction applies.

## Language Server Usage

- For Rust, Python, C/C++/CUDA and Markdown work, prefer the configured Pi LSP server for symbols, definitions, references, hover/type information and diagnostics whenever supported. Use the lsp tool for semantic navigation instead of broad text searches.
- Confirm Pi is rooted at this repository and issue a concrete file-level LSP request before relying on a server. LSP idle alone is not evidence of failure or success; /lsp doctor is supplementary, not a substitute for the real operation.
- For clangd, confirm the compilation database and repo root. All generated build products, compilation databases and clangd indexes/caches must be outside the checkout under /data/sglang-hicache/; do not generate .cache/clangd, compile_commands.json, object files or build directories in the repo. This host /data is a root-filesystem directory, not a separate mount; preserve the repo-outside-cache boundary.
- If a server is unavailable, file routing is unsupported, or compile metadata makes diagnostics unreliable, state the limitation and fall back to targeted source inspection. Do not describe fallback parsing or server initialization as semantic LSP verification.

## Control Directory

This repository uses `control/` as its work-control area. The full Goal, Plan, Task and Frontier discipline is defined below.

## Execution Continuity and Resource Authority

- Do not stop work merely because an intermediate result was achieved or one subtask is blocked. Continue until the authorized stage/Goal completion conditions are met, or a concrete, material blocker prevents all meaningful authorized progress. A blocker scoped to one operation does not block the rest of the Goal; keep advancing independent work.
- The user has authorized GPU use for this project; do not request additional GPU authorization. Before GPU workloads, acquire and hold the project-designated exclusive lock and follow its operational safeguards. If the lock is unavailable or another concrete resource conflict exists, defer only that GPU operation and continue other work.
- The user has explicitly authorized this agent/session to use the workstation CPU exclusively for this project. CPU-only work, tests, builds, and analysis do not require further coordination.

# Control Discipline

## Execution Continuity and Resource Authority

- Do not stop work merely because an intermediate result was achieved or one subtask is blocked. Continue until the authorized stage/Goal completion conditions are met, or a concrete, material blocker prevents all meaningful authorized progress. A blocker scoped to one operation does not block the rest of the Goal; keep advancing independent work.
- The user has authorized GPU use for this project; do not request additional GPU authorization. Before GPU workloads, acquire and hold the project-designated exclusive lock and follow its operational safeguards. If the lock is unavailable or another concrete resource conflict exists, defer only that GPU operation and continue other work.
- The user has explicitly authorized this agent/session to use the workstation CPU exclusively for this project. CPU-only work, tests, builds, and analysis do not require further coordination.

`control/` owns durable Goal, Plan, Task, and Frontier state.

```text
control/
├── AGENTS.md
├── frontier.md
└── <goal-id>/
    ├── goal.md
    ├── plan.md
    └── tasks/
        └── TNNN-<slug>.md
```

1. One control session MAY manage multiple Goals.

2. Each Goal MUST use one stable `<goal-id>` directory. Goal IDs and Task IDs MUST NOT be reused.

3. `goal.md` defines the authorized Goal, scope, constraints, exclusions, and completion condition. It is not a progress log.

4. Create a new Goal when the intended outcome, completion condition, object, or authority materially changes. Do not stretch an existing Goal merely because later work is related.

5. A completed Goal MUST NOT be reopened for ordinary follow-on work; create a new Goal and reference the prior result. Reopen only to correct that Goal itself.

6. `plan.md` is the current state of the Goal: established results, decisive frontier, active/blocking Tasks, and next action. It is not history.

7. Obsolete assumptions, plans, and unnecessary future Tasks MUST be removed rather than accumulated.

8. Each Task represents one coherent professional problem and uses `TNNN-<slug>.md`.

9. Every Task MUST state:

```text
Status: READY | ACTIVE | DONE | BLOCKED
Work area
Objective
Inputs
Completion
Result
Remaining
```

10. The Task file is both instruction and handoff. The working session writes the result into the same file; do not create duplicate control reports.

11. Tasks MUST be coarse enough for one professional session to own end-to-end. Do not split reconnaissance, implementation, ordinary verification, and reporting into procedural stages without a real professional boundary.

12. Create Tasks only for work necessary to advance the Goal. Do not create Tasks for reassurance, status, generic review, or additional evidence without a concrete need.

13. Professional work belongs in its applicable work area. The control session owns Goal, Plan, Task boundaries, integration, and frontier; it does not perform substantial design, implementation, experiment, research, review, or operations work.

14. `DONE` means the Task's stated Completion is satisfied. `BLOCKED` means a concrete condition prevents further progress and that condition is recorded.

15. Completed Task results MUST be integrated into `plan.md` by conclusion, not copied as history.

16. `frontier.md` is the authoritative cross-Goal view of current unfinished work.

17. `frontier.md` MUST contain only active or intentionally deferred work. DONE, cancelled, superseded, obsolete, or inactive entries MUST be deleted immediately.

18. Each frontier entry uses:

```text
<goal-id>
- <task-id> <title> — READY | BLOCKED | DEFERRED
  - frontier: <current decisive issue or next action>
  - task: <task-file>
  - unblock/reopen: <condition, when applicable>
```

19. Every change to the decisive frontier MUST update `frontier.md` in the same control transition.

20. `frontier.md` is not history or backlog. Task detail, evidence, results, and past state belong in Goal/Plan/Task files; keep the frontier short by deleting obsolete state.

21. Before acting on a Goal, read its `goal.md`, `plan.md`, relevant Tasks, and current frontier entry. Do not rely on conversational memory from another Goal.

22. Stop managing a Goal only when it is complete, genuinely blocked, or requires a material user decision.

针对这几天反复出现的问题，设定以下硬约束：
1. 严禁只完成源码审查、编译检查、少量单测，就结束任务。
2. 严禁因为 fixture、IPC、Profiler、Launcher、LSP 或普通测试失败而停工等待新指令。
3. 严禁在 GPU 已获授权且资源可用时，未经真实运行验证就宣布本轮工作结束。
4. 严禁把 PARTIAL、NOT_RUN、NOT_VERIFIED 当作正常的阶段性交付。
5. 严禁反复认证已通过的 ACK、锁、缓存恢复和单节点驱逐，偏离当前性能目标。
6. 严禁用静态推测、跨 Run 拼接或不完整遥测冒充真实 GPU 性能数据。
7. 严禁汇报一次进度就停止执行；汇报后必须继续推进。
8. 严禁擅自建立新工作树、清理既有 Dirty Tree，或把未经验收的代码混入提交。
只有真正的架构/Ownership 决策冲突，或无法自主解决的外部硬阻断，才允许停工。

# 控制文档

控制文档必须精简，每个文档只说一个事项，内容必须简明扼要，严禁长篇大论，严禁在一个文件中反复添加内容，文档名称应当体现内容，以方便寻找，markdown文档应当保持精细的内部标题目录结构，以方便查找。
