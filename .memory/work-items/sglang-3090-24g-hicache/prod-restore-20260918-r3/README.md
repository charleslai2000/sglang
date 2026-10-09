# PROD-RESTORE-20260918-R3

- **工作标题：** PROD-RESTORE-20260918-R3
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/PROD-RESTORE-20260918-R3.md`：**
Operational recovery: restore a healthy serving instance on `:30000` after the
`MAMBA-F12-PARK-REGRESSION-20260918` task (GPU-window authority) stopped production and failed to
restore it, then leave the host in a clean, documented, healthy state.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/PROD-RESTORE-20260918-R3.md`：**
**`:30000` is UP and healthy, serving M2 (OmniCoder-9B GPT4 INT4).** Verified by real commands:
loopback `/health` = 200, LAN `/health` = 200, `GET /v1/models` returns the M2 model id, and
`POST /v1/chat/completions` succeeds over both loopback and LAN.
**Important attribution fact (not a claim of my own action):** I did NOT start the live server, and I
did NOT kill anything. During first-pass reconnaissance (12:43:18Z) a **concurrent actor**
started M2 via the last-resort `/tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh`; by the time
I had finished diagnosis, production was already up. Process ancestry shows that actor was launched
by an `opencode` process (PID 1758196) — i.e. orchestrator-side, not this task. I verified the
result end-to-end rather than disrupt it.
The **preferred M2 scaffold path does not exist** in the installed scaffold: `start.sh` accepts only
`prod|test` and rejects `m2` (exit 2). The `m2` role exists only in an *unapplied staged diff*
(`/tmp/opencode/M2-ARCH-STAGE-20260918/patch/b/bin/start.sh`) and `conf/service.env` has no `M2_*`
variables; only a draft `bin/stop-m2.sh` was installed. Therefore the fallback M1 path (which would
have restored M1) could not be used while M2 already held the single GPU, and switching would have


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/PROD-RESTORE-20260918-R3.md` → `.memory/phase2-hicache-design/agents/PROD-RESTORE-20260918-R3.md`; SHA256 `7d86ebf4e2d2ab4e2861e394f5045fcc7b001ddad550a1438523a1d5ec87aeb2`; source state `tracked`
