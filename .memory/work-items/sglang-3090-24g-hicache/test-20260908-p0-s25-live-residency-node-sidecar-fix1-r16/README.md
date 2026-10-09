# TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16

- **工作标题：** TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16.md`：**
The fresh remote run deployed the accepted FIX1 source with matching SHA-256
hashes and passed the remote focused emitter and V4.3 fixture checks. The
engine reached health 200 with the frozen configuration and the required
markers were present before engine and vehicle requests.
The live product path emitted exact identities for 23 target builds and 15
durability barriers, but emitted **zero strict `residency_barrier` events**.
It emitted 751,914 `residency_barrier_outcome` records with
`reason=node_lookup`, `exception_type=KeyError`, and `result=false`. Warm and
restore were therefore never admitted. This is runtime product evidence of a
residency-fold/node-lookup failure, not evidence of a queue or marker failure.
The vehicle and engine were stopped only for this run after the retry telemetry
grew the trace to 937 MB and the root filesystem reached 96% used (4.4 GB
free). The native vehicle bundle was not written before that safety stop, so
this run cannot verify the native HTTP `response.id`/finished, TTFT, or restore

### 报告列出的产物/证据
- `phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16.md`：Remote evidence root:
`/data/evidence-gate3-parked/p0-s25-v43-residency-node-sidecar-fix1-live-r16`
Key artifacts:
- `verdict.json`
- `source-hashes.txt` and `evidence-manifest.sha256`
- `engine/launcher.log`, `engine/launch-command.txt`, `engine/pid`
- `vehicle/launch-command.txt`, `vehicle/pid`, `vehicle/vehicle.stdout.log`
- `raw/trace-post-stop.jsonl`
- `raw/per-target-identities.jsonl`
- `raw/per-target-summary.json`
- `raw/runtime-metrics.json`
- `raw/event-counts.json`
- `raw/live-monitor.txt`
- `raw/pre-stop-audit.txt`, `raw/pre-engine-stop-trace.txt`,

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16.md` → `.memory/phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-RESIDENCY-NODE-SIDECAR-FIX1-R16.md`; SHA256 `fb7b9ce0dec640485d128aa70079dd78e9cc5a93e4015b6ceff9d5789427d707`; source state `tracked`
