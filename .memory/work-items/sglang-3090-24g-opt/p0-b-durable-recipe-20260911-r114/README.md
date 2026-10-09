# P0-B-DURABLE-RECIPE-20260911-R114

- **工作标题：** P0-B-DURABLE-RECIPE-20260911-R114
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-DURABLE-RECIPE-20260911-R114.md`：**
- Task ID: `P0-B-DURABLE-RECIPE-20260911-R114`
- Invocation: `ses-p0b-durable-recipe-r114-20260911` (fresh)
- Role: `tester`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only, not modified): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
(HEAD `4f41f5bab562b99562f30c67540eb05344d13637`)
- Server (read-only, never started/stopped/restarted/killed/reconfigured): PID `48746`

## 实际改了什么
在健康、既有 local 3090 server 上仅用 public HTTP 和读取 server/probe logs；未启动/停止/重配服务、未改源码、未加 instrumentation 或 synthetic events。两阶段 workload 先以独特 Unicode 首 token 产生 durable barrier，再在相同 session generation 建 target、用独立压力 sessions 驱动 HOST_ALLOC FIFO waits；14 POST+4 GET，共 18 请求、约 8 分钟。

## 生成结果与验收
报告状态 **VERIFIED，11/11 predicates，reducer exit 0**。R113 predicate 4 缺口由 target 同 generation 10 的 `storage_persisted`/`durability_barrier` 补齐；target lifecycle `d4cd…:10` 的 HOST_ALLOC park、allocability generation advance、与真实 predecessor terminal 关联的 grant、accepted all-or-nothing finalize、READY 均在冻结窗口内。Server 保持健康。验收仅依据该冻结窗口和 reducer/证据 bundle；无产品实现变更。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-DURABLE-RECIPE-20260911-R114.md` → `.memory/rh-p0b-harness-durability/P0-B-DURABLE-RECIPE-20260911-R114.md`; SHA256 `c53dbd6a7da8cb38d91f49266983d33baf63189efb8607cec6b8e34c4f28330c`; source state `tracked`
