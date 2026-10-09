# P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT

- **工作标题：** P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
冻结 R126 faithful replication contract，针对 R125 run 1 因所有 blocked-domain generation 都前进而无法证明新 Gate 2 条款的 NON-EVIDENCE，使用不变 R121 p3 recipe 最多三次重放，区分新条款是否决定 grant。

## 实际改了什么
仅形成验收/执行合同，无产品代码或 profile/workload 修改、无运行实验。Gate basis 采用 v2 的 `host_alloc.v1` L2 host pool；冻结 nonce=p3、同一 R125 driver defaults 与单独 run 输出目录，并澄清 R125 `p1` 是转录错误。

## 生成结果与验收
四门合同：Gate0 固定 T keyset/hash 与 27,328 KV pages；Gate1 release 前不得消费且 issue epoch 不早于 release；Gate2 grant 时至少一个 blocked domain generation 不变但容量已满足，否则记 NON-EVIDENCE 并进入下一 replay；Gate3 durable boundary 的完整 KV+Mamba restore/零 recompute-discard/http 完成，并允许请求 durable-boundary 外 11-token tail 的已知 PARTIAL 语义。只有四门同 run 全过为 PASS；三次无 Gate2 hit 或链无法复现才 NOT_VERIFIED/BLOCKED。禁止改 R121–R125 artifacts、产品、profile、重启、flush/close、新 instrumentation；最多 3 runs/60min/200 HTTP。此文为 frozen contract，不是 R126 执行结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md` → `.memory/rh-p1-durable-replay-eviction/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md`; SHA256 `13ba59c06902d9e7cb2bc205ee7b9118776122e67f3eee107980ce8fdc1667b7`; source state `tracked`
