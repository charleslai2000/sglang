# P1-DURABLE-PREFIX-REPLAY-20260912-R126

- **工作标题：** P1-DURABLE-PREFIX-REPLAY-20260912-R126
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md`：**
Three faithful R121-p3 replays were executed against the running rebuilt server.
All three reached the FULL live chain (`non-resident T -> HOST_ALLOC park ->
F1 release+1 -> RH issue -> HOST_ALLOC grant -> kv_fetched==D_req`), and **Gates
0, 1 and 3 hold on every run**. **Gate 2 is NON-EVIDENCE on all three runs**: at
T's `restore_host_alloc_wake_decision decision=grant`, **both** blocked domains'
generations had advanced, so the original generation/invalidation branch would
also grant and the fix's NEW capacity clause was never the grant-deciding
condition. The new clause was consulted only at the intermediate *holds* (where

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md`：**
**P1 NOT_VERIFIED.** All three replays reached the full durable-restore chain
with Gates 0/1/3 PASS, but Gate 2 was NON-EVIDENCE in every run (both blocked
domains' generations advanced at T's grant), so the HOST_ALLOC wake-liveness
fix's new capacity clause was never runtime-exercised as the deciding grant
condition. Replication budget (3/3) is exhausted. Classification:
harness/workload timing (a race on mamba-generation quiescence), not a product
defect; no product change is licensed.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md`：`work/R126-bundle/`: `run1/`, `run2/`, `run3/` (each with `raw.log`,
`probe.log`, `requests.jsonl`, `state.jsonl`, `driver.out`,
`baseline-offsets.txt`, `run-context.txt`, `watch.log`, `server-capture.log`,
`sha256sums.txt`), `run1-aborted-timeout/` (literal-command timeout, evidence
only), and `sha256sums.txt` (bundle-level). No R121–R125 artifact was modified.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md` → `.memory/phase2-hicache-design/work/P1-DURABLE-PREFIX-REPLAY-20260912-R126.md`; SHA256 `23ed5d488d66a84f5e52c35601161b714b328c4c1be0811547345bb2830267e2`; source state `tracked`
