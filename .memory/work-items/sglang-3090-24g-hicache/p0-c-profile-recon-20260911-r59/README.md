# P0-C-PROFILE-RECON-20260911-R59

- **工作标题：** P0-C-PROFILE-RECON-20260911-R59
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`：**
- ENTRY: ACCEPT
- task_id: `P0-C-PROFILE-RECON-20260911-R59`
- invocation: `ses-p0c-profile-recon-r59-20260911`
- role: `scout`
- epoch: `2026-09-11`
- status: `done`
- scope: read-only local reconnaissance of the launch/profile surfaces, capacity
and limit definitions, phase2 R32/R34/R52 telemetry, and the capacity-semantics

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`：**
The authorized 3060 profile is fully recoverable from the R32 raw bundle: model
`Qwen3.5-4B-AWQ` (compressed-tensors, fp8_e4m3 KV), TP/PP 1/1, context_len
262144 with `max-total-tokens 65536`, device Mamba `53` slots, host KV pool
`131073` tokens / 2.15 GB, host Mamba 5.51 GB, page size 1, physical prefetch
budget `65536` and speculative budget `39321`, and RH flags
`frontier_n=8`, watermarks `55000/110000`. All of these are pinned to source
`path:line` references and to durable artifact lines. They are classified
OBSERVED rather than FROZEN because no reviewed 3060 launch script exists and the
R32 run never demonstrated the capacity transition. Section 6 gives the minimal
bounded, fail-closed capture procedure to ratify them. P0-B and P0-C remain
NOT_VERIFIED; this report does not accept P0-C or bypass the hard gate.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`：- Primary: `.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`
  (repository `.memory` root).
- Mirror: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md` → `.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`; SHA256 `c68e763445f6798591a01702468fbba5f7a700548012f045cb58b77b033a0085`; source state `tracked`
