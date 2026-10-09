# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124

- **工作标题：** P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124.md`：**
- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124`
- Role: independent tester; owns the experiment. No child agents.
- Bundle: `work/R124-bundle/` (raw.log, probe.log, chain.json,
condition-evidence.md, manifest.json, sha256sums.txt, driver124.py,
requests.jsonl, state.jsonl).

## 实际改了什么
independent tester 在 rebuilt server (PID 3082643/scheduler 3086752) 上执行一次 R121-faithful controlled-eviction recipe，并做独立 durability diagnostic probe；只用现有 endpoints/events，无 server restart/signal/profile/cache/session 变更、无产品编辑或新 instrumentation。保存 `work/R124-bundle/`。

## 生成结果与验收
状态 **BLOCKED → P1 NOT_VERIFIED**：rebuilt server 的 L3 durable publish/ack path 未工作——L3 bytes 有写入但 `storage_persisted`/barrier 无成功记录，storage queries full miss。Target T durable coverage 0，虽曾 SPEC_BUDGET park，但未走 HOST_ALLOC wait/wake；host-allocation wake fix 未在 target 上触达。一次独立 17,647-token probe 重现 `storage_hit=0/miss`，报告据此排除该 recipe 是 blocker，但未判 product regression vs L3-store state（启动时载入大量既存 entries）vs infrastructure。未花第二次 run budget。需要另获授权作 read-only root-cause、server restart/L3 reset 或 backend internals inspection，不能从本报告擅自执行。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124.md` → `.memory/rh-p1-durable-replay-eviction/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124.md`; SHA256 `9c599adf4399177efff3f9f61bd1156951abb016702a44017d368406b743aac3`; source state `tracked`
