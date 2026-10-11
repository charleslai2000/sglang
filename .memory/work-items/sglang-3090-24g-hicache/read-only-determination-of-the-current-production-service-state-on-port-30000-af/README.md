# Read-only determination of the CURRENT production service state on port 30000 after the failed

- **工作标题：** PROD-STATE-PROBE-20260918-R2
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/PROD-STATE-PROBE-20260918-R2.md`：**
M2-replacement window task, so the orchestrator can decide the next step (restore M1 vs continue M2).
Scope: Status probe only. No stop/start/restart/signal/kill, no GPU allocation, no config or git
changes. Only an HTTP GET to `/health` and `/v1/models` was issued to 127.0.0.1:30000 (and one GET to
the LAN IP). Evidence window: 2026-09-18 08:36:00Z–08:40:40Z UTC.
Result: **SERVICE_DOWN** — nothing is serving port 30000 (or any 3000x port). M1 was deliberately
stopped at 08:33:53Z by the failed window task; M2 was never started.
Terminal state: DONE
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/PROD-STATE-PROBE-20260918-R2.md`：**
| Item | Finding |
|---|---|
| `:30000` listener | **NONE**. `ss -ltnp` shows only :53 and :22. `/proc/net/tcp` has no `:7530` (=30000). `fuser -n tcp 30000` exit 1. `curl /health` → HTTP 000 (curl exit 7, connection refused). |
| Live `--model-path` | **N/A** — no process exists to read. Last served model was M1 `/data/models/qwen35-9b-w4a16`. |
| M1 (`/data/models/qwen35-9b-w4a16`) | **NOT RUNNING**. 0 non-self processes. |
| M2 (`/data/models/omnicoder-9b-gptq-int4`) | **NOT RUNNING and NOT partially started**. 0 non-self processes; no listener on 30000/30001 or any other port; no M2 launcher script or log was ever created. |
| GPU | **IDLE**: 1 MiB used / 24124 MiB free / 24576 MiB total; **no compute apps**. |
| Canonical lock | `/tmp/opencode/gpu-3090.lock` is **stale** (owner PID dead) and the flock is **FREE**. |
| M1 stop time | 08:33:53Z (supervisor log) → graceful exit completed 08:34:19Z; state published `role=free` at 08:34:25Z. |
| M2 start attempt | **Never happened**. The worker died at 08:34:26Z on `AI_APICallError: Provider error 502 ... Provider unreachable` because it had just stopped the very provider (port 30000) it depended on. |
**Causal chain (from the live OpenCode log `/home/ubuntu/.local/share/opencode/log/opencode.log`), session `ses_f4c5ad6efffe7KANI5qHcdOEBS`, agent=devops-executor, model=worker:**
1. `08:33:09.987` — `cat /proc/1750878/environ >/tmp/m1_env.txt` (captures live M1 env).
2. `08:33:28` — reads `/proc/1750878/cmdline` and `/proc/1750878/environ`.…（节选；见来源报告）


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/PROD-STATE-PROBE-20260918-R2.md` → `.memory/phase2-hicache-design/agents/PROD-STATE-PROBE-20260918-R2.md`; SHA256 `41520d62a11acb39c7d80012f6048d3657a603d5d02e8cba4f4db20daec3d6c5`; source state `tracked`
