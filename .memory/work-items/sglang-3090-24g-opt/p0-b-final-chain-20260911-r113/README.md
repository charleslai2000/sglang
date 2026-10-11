# P0-B-FINAL-CHAIN-20260911-R113

- **工作标题：** P0-B-FINAL-CHAIN-20260911-R113
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-FINAL-CHAIN-20260911-R113.md`：**
- Task ID: `P0-B-FINAL-CHAIN-20260911-R113`
- Invocation: `ses-p0b-final-chain-r113-20260911` (fresh)
- Role: `tester`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only, not modified): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
(HEAD `4f41f5bab562b99562f30c67540eb05344d13637`)
- Server (read-only, never started/stopped/restarted/killed/reconfigured): PID `48746`

## 实际改了什么
tester 对已经运行的 local 3090 server 只用 public HTTP 与读取既有 server/probe logs；无 server/GPU lifecycle、repo、instrumentation 或 synthetic event 改动。两次 bounded run 共 18 HTTP requests，约 23 分钟，server 保持健康。

## 生成结果与验收
实际完整链中目标 T 经 HOST_ALLOC park/wake，第二 waiter grant 真实关联先前 FIFO waiter 的 TIMEOUT terminal，随后 all-or-nothing full KV+Mamba finalize 与 READY。冻结 R111 reducer 为 **10/11，NOT_VERIFIED**：唯一失败 `positive_full_hit` durable barrier 对 target session_generation 缺失（其它 session 的 pre-window barrier 不算）。因此无 P0-B PASS。另两 waiter 未同时处于 parked；waiter-A HTTP response 未写 requests transcript、rid 由 server log 恢复；large-session backup events 未见 `storage_persisted`/`durability_barrier`，需查 producer/config。raw log/hash 与行号见原报告。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-FINAL-CHAIN-20260911-R113.md` → `.memory/rh-p0b-harness-durability/P0-B-FINAL-CHAIN-20260911-R113.md`; SHA256 `95f142dfcf22e9a01b254bedcb33d5f6ad0c7cc18542d5fc2a3e78fe1f9037d5`; source state `tracked`
