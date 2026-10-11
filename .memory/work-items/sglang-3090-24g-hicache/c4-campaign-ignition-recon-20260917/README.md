# C4-CAMPAIGN-IGNITION-RECON-20260917

- **工作标题：** C4-CAMPAIGN-IGNITION-RECON-20260917
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/C4-CAMPAIGN-IGNITION-RECON-20260917.md`：**
- task_id: `C4-CAMPAIGN-IGNITION-RECON-20260917`
- role: scout — READ-ONLY reconnaissance. Facts with file:line / verbatim command evidence only.
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`)
- authority: ledger entry `### 2026-09-17 — OWNER RULING (Option A)` §3 (6-step campaign) and
`### 2026-09-17 — C4 点火准备` (this recon), `.memory/phase2-hicache-design/ledger.md:7852-7891`
and `:8052-8070`.
- Dispatch validation: the repo-root `AGENTS.md` is **ABSENT**; the only in-repo `AGENTS.md` is
`docs/AGENTS.md` (upstream Mintlify documentation guide, lines 1-30 — not applicable to

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/C4-CAMPAIGN-IGNITION-RECON-20260917.md`：**
- **Steps 1, 3, 4** have a citable CLI surface (README + argparse) **subject to the in-flight
  harness change**; verdict artifacts and exit-code vocabulary are identified.
- **Step 2 (Gate A 128K) is ABSENT** as an invocation: the current harness pins the server to a
  65536-token device pool and only asserts `>=64K`. Whether the in-flight writer adds a 128K knob
  is unknown and was not assumed.
- **Step 5 (native 128K perf) has a documented definition/threshold but no repo tool**; the only
  driver is a `/var/log` artifact testing a `/tmp` overlay and a third tree (`/opt/sglang/local-prod-v1`),
  not the v1.2.1 frozen runtime.
- **Step 6 (short canary) has a reference driver but it is not in the repo** (deployed `/var/log`
  artifact; imports deployed `gate_common`).
- **No six-step campaign orchestrator exists** in repo, `/var/log/sglang`, or `/tmp/opencode`
  (searched read-only).
- Production stop/start is well-defined, identity-checked, and free of `pkill`.
- GPU lock path/idiom and L3 namespace policy are citable and consistent across harness, scaffold,


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/C4-CAMPAIGN-IGNITION-RECON-20260917.md` → `.memory/phase2-hicache-design/agents/C4-CAMPAIGN-IGNITION-RECON-20260917.md`; SHA256 `12e7d3e689290bc3edb8fc6060160dbf07b8a9061c6555a916f2826892311e3d`; source state `tracked`
