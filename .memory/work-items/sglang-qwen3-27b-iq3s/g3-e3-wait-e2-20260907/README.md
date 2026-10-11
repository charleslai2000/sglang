# G3-E3-WAIT-E2-20260907

- **工作标题：** G3-E3-WAIT-E2-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读监测既存 E2 Production A wrapper 是否结束、全部计划 repeats 与 artifacts 是否完整，以便 E3 在确认 drain/idle 后决定是否可开始；不把 E2 数据自动视为 E3 证据。

## 实际改了什么
仅监测授权 host 上已运行 wrapper 与 run directory；没有发起 benchmark、信号/重启、改服务或其他远端状态。产出本地监测报告。

## 生成结果与验收
E2 wrapper 正常退出，progress log 有 C1/C4/C5 共九次 repeats 且 rc=0，目录中有完整所需 raw result、命令、metadata、loads、telemetry 与 PID evidence。此报告只确认 E2 完成及 E3 admission 参考状态，明确不将 E2 measurements 纳入 E3 matrices；任何跨 epoch 使用需独立 admission decision。
The pre-existing E2 production-A wrapper completed normally and exited. The wrapper's
progress log contains all nine scheduled repeats, each with `rc=0`, followed by
`all scheduled repeats attempted` at `2026-09-07T13:47:12.638552287Z`:
| Point | Repeat 1 | Repeat 2 | Repeat 3 | Raw result sizes |
|---|---:|---:|---:|---:|
| C1 | rc=0, 12:12:54–12:20:27Z | rc=0, 12:20:29–12:27:50Z | rc=0, 12:27:52–12:35:14Z | 307614 / 307588 / 307508 bytes |
| C4 | rc=0, 12:35:17–12:45:59Z | rc=0, 12:46:01–12:56:35Z | rc=0, 12:56:38–13:07:09Z | 565942 / 565953 / 565957 bytes |
| C5 | rc=0, 13:07:12–13:20:15Z | rc=0, 13:20:18–13:33:14Z | rc=0, 13:33:16–13:46:11Z | 692677 / 692710 / 692691 bytes |
All repeat directories contain the required raw runner output, result JSONL, command,
metadata, pre/post loads snapshots, 1-second query telemetry, `nvidia-smi dmon`,
server-log delta, PID records, and invariant record. Each repeat has 35 files; no
required file was missing. Raw artifacts remain at the authorized remote path:
`/data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530/`
This report does not admit the E2 measurements into the E3 matrices; it only confirms


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-WAIT-E2-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-E3-WAIT-E2-20260907.md`; SHA256 `555b9c7b26b3ebaa4a94cbae0e065282937d0b0f464e159cbbdc749404956d36`; source state `local-only`
