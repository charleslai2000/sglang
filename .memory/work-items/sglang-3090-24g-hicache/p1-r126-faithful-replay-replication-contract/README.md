# P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT

- **工作标题：** P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md`：**
- Applies to `P1-DURABLE-PREFIX-REPLAY-20260912-R126`.
- Additive superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
(`2ac86b5a…b3b`), `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`
(`bf7b09ee…1e1f8`), and `R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`
(`f78a2fc6…3c1f`). Gate basis is v2 (L2 host pool via `host_alloc.v1`).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md`：**
- PASS a run iff Gates 0,1,2,3 all hold.
- If a run reaches the chain but Gate 2 is NON-EVIDENCE, run the next replay.
- BLOCKED/NOT_VERIFIED iff all replays are exhausted without a Gate-2 hit, or the
  chain cannot be re-established (report exact missing transition).
- No mutation of R121–R125 artifacts; no product code change; no profile change;
  no server restart; forbidden `/flush_cache`, `/close_session`; no new
  instrumentation. <= 3 live replays; <= 60 min; <= 200 HTTP.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md` → `.memory/phase2-hicache-design/work/R126-bundle/P1-R126-FAITHFUL-REPLAY-REPLICATION-CONTRACT.md`; SHA256 `13ba59c06902d9e7cb2bc205ee7b9118776122e67f3eee107980ce8fdc1667b7`; source state `tracked`
