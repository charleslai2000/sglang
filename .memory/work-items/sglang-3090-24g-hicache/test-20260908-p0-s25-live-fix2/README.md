# TEST-20260908-P0-S25-LIVE-FIX2

- **工作标题：** TEST-20260908-P0-S25-LIVE-FIX2
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-FIX2.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-FIX2.md`：**
The frozen S=25 RH-off live run was started successfully after remote cleanup,
source synchronization, focused-fixture verification, and exact engine
environment verification. The engine reached health 200 and served 9 HTTP
requests with HTTP 200 responses. Eight initial sessions emitted valid V3
`build_complete` identities.
The run could not reach durable restore acceptance. All eight vehicle build
workers blocked in the vehicle's `wait_for(ready_for_warm)` before submitting
the ninth session. Consequently the engine never received enough subsequent
traffic to evict the final build leaves; the only storage events were V2
ancestor events on nodes 26/27 with `context_complete=false`, not accepted
evidence for the final build identities. No exact final-node KV/Mamba durable
events, durability barriers, warm requests, or restore successes were
observed. This is a confirmed vehicle scheduling/test blocker with missing
live acceptance evidence, not an infrastructure capacity failure and not

### 报告列出的产物/证据
- `phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-FIX2.md`：- Remote raw engine log: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/engine/launcher.log`
- Remote raw event trace: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r10/raw/t38c-probe.log.final`
- Post-stop identical trace copy: `raw/t38c-probe.log.poststop`
- Final per-session analysis: `raw/live-analysis-final.txt`
- Environment capture: `raw/launcher-env.txt`, `raw/proc-engine-environ.txt`
- Metrics: `raw/metrics-final.txt`
- Process and disk evidence: `raw/processes-before-stop.txt`,
  `raw/processes-after-stop.txt`, `raw/df-before-stop.txt`
- Evidence hashes: `raw/md5-final.txt`, `raw/sha256-final.txt`,
  `raw/evidence-sha256-final.txt`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-FIX2.md` → `.memory/phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-FIX2.md`; SHA256 `02c553447d7addff756d728dbb97518434a1c6be4d0fa22d6c01986343594e3a`; source state `tracked`
