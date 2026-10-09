# KILLER-ATTRIBUTION-RECON-20260918

- **工作标题：** KILLER-ATTRIBUTION-RECON-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/KILLER-ATTRIBUTION-RECON-20260918.md`：**
STRICTLY READ-ONLY forensic attribution of the process tree(s) associated with the
`mamba-sweep` experiment (`/tmp/opencode/mamba-sweep-20260918/`) and any identity-checked kill
actions against production SGLang on `:30000`. Attribute WHO is doing the killing using
process-lineage evidence only. No process is started, stopped, signalled, or modified; no write
occurred except this result artifact.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/KILLER-ATTRIBUTION-RECON-20260918.md`：**
- **`:30000` is DOWN.** At first read (00:03:58Z) and final read (00:06:24Z): `/health`=000,
  `/v1/models`=000, LAN `192.168.20.250:30000/health`=000. No listener on `:30000` at any read.
- **The running sweep belongs to the single live agent-host process `opencode` PID 1644932**
  (tty `pts/0`, started Thu 2026-09-17 20:44:27). Top-level ancestor chain:
  `sshd /usr/sbin/sshd -D` (PID 1272, PPID 1) → `sshd: ubuntu [priv]` (298128) →
  `sshd: ubuntu@pts/0` (298243) → `-bash` (298244) → **`opencode` (1644932)** →
  `bash -c ...bash run_cell.sh 48...` (1743336) → `run_cell.sh` (1743340) →
  `cell_supervise.sh` (1743344) → `sglang.launch_server --port 30160` (1743374).
- **There is exactly ONE live `opencode` host process on this host** (`pgrep -c -x opencode` = 1),
  with one controlling login session (`pts/0`). No second `opencode`/`node`/`bun` agent host is
  running. Both "automated sessions" therefore share one PTY/SSH session; they are logical
  sub-sessions within PID 1644932, not separable as distinct live process trees.
- **No M-line gate is running.** The named `.memory/agents/` artifacts
  (`GGUF-GATE-M4M3-20260918`, `PROD-STATE-CHECK-R2-20260918`, `G-COMMIT-ROSTER-VERIFY-20260918`,


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/KILLER-ATTRIBUTION-RECON-20260918.md` → `.memory/phase2-hicache-design/agents/KILLER-ATTRIBUTION-RECON-20260918.md`; SHA256 `395e0a8d90049957d2003a0524fa9bf33bc52f386186091f48f6c0bbbd8a0594`; source state `tracked`
