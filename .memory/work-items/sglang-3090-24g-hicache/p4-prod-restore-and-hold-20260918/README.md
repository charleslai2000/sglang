# P4-PROD-RESTORE-AND-HOLD-20260918

- **工作标题：** P4-PROD-RESTORE-AND-HOLD-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/P4-PROD-RESTORE-AND-HOLD-20260918.md`：**
Restore the orchestrator-owned production service on :30000 and keep it up. Authority:
`OWNER-APPROVAL-20260918-PROD-START` (ledger.md line 9520) plus the owner's final ruling
(ledger ~line 9597): this line owns :30000; GPU authorization belongs to the owner; the other
session handles "other content" and must not contend for :30000. A competing session had
SIGTERM'd a prior production instance and relaunched a mamba-sweep cell (sweep3) holding the
canonical lock and GPU. Procedure: verify state, preserve sweep evidence, identity-checked stop
of the sweep cell, clean-state verify, start production, verify, hold/re-check ~90 s.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** BLOCKED (KILLED-AGAIN); KILLED-AGAIN (not UP-PERSISTENT).

**`phase2-hicache-design/agents/P4-PROD-RESTORE-AND-HOLD-20260918.md`：**
- **Sweep cell stopped: YES.** sweep3 cell-64 (run `sweep3-mamba64-20260917T235029Z-1737059`)
  was stopped identity-checked; `:30160` free; lock released; GPU cleared.
- **Production started: YES.** `start.sh prod` reached `/health` 200 at 23:56:27,
  run `prod-20260917T235414Z-1738571`, server pid **1738819**, cold start **133.0 s**,
  lock generation 14.
- **Production UP-PERSISTENT or KILLED-AGAIN: KILLED-AGAIN.** At **23:56:30**, ~3 s after
  reaching health 200, a competing session ran an identity-checked kill script
  (pid 1740056, `pgrep`-captured) that TERM'd the prod client/supervisor and killpg'd the
  server process group. The production server logged `SIGTERM received ... Draining requests`.
  At **23:56:48** the same competing session re-acquired the canonical lock as
  **generation 15** and launched a new sweep cell (`sweep4-mamba48-...`, server pid 1740265,
  `:30160`).
- Per STEP 7 instruction, **no second production start was attempted**.
- New production pid: 1738819 (now dead). Run id: `prod-20260917T235414Z-1738571`.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/P4-PROD-RESTORE-AND-HOLD-20260918.md` → `.memory/phase2-hicache-design/agents/P4-PROD-RESTORE-AND-HOLD-20260918.md`; SHA256 `5be13c998a944f6baf0bbd01ec3da6e085b3021971b3cafacff423282630256f`; source state `tracked`
