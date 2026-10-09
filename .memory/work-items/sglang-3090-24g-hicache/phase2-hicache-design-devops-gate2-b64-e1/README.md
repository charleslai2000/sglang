# phase2-hicache-design-devops-gate2-b64-e1

- **工作标题：** phase2-hicache-design-devops-gate2-b64-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-devops-gate2-b64-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-devops-gate2-b64-e1.md`：**
Phase-0 64G result — **the three-branch verdict is: ORIGINAL Gate-2 FAIL WAS AN L3 CAPACITY TEST DISTORTION (branch 1), with one important nuance at K=16.**
- **At K=4 and K=8: branch 1 cleanly.** extent_recycle=0, L3 restore now functional (storage_hit>0 rows: k8 41/96), and **K=8 L0 exact-restore = 0.9599 ≥ 0.95 PASS**. Original 20G FAIL (6144 recycles, L0 0.7843, storage_hit=0) is eliminated — this is precisely the budget-mismatch root-cause hypothesis confirmed.
- **At K=16: L3 capacity pressure reappears (3716 recycles) and L0 drops to 0.8810 <0.95.** With 16 agents the cumulative write stream exceeded the 64G×0.9=57.6G watermark mid-run → GC recycled committed keys again → L0 restore degraded. So raising the budget to 64G fixes K≤8 but the K=16 workload still outstrips 64G L3.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-devops-gate2-b64-e1.md`：- Local evidence: `.memory/phase2-hicache-design/work/gate2-b64-evidence/b64k{4,8,16}-verdict.json`
- Remote evidence (kept): `/root/evidence-gate2-b64k{4,8,16}/` (run-*/verdict.json, runs.csv, t38c-probe.log, engine-events.txt) + `/root/engine-gate2-b64k{4,8,16}.log`
- Config applied (verified via engine log ExtentFileBackend line, ALL THREE runs): `extent=67108864 B slots=1430 max_size=64000000000 min_free=10000000000` → **file 96G (1430 slots), MAX_SIZE 64G**, as decided. file_size was raised; nominal 64G is actually usable.
- All three runs GATE2_b64k{4,8,16}_COMPLETE rc=0.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-devops-gate2-b64-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-gate2-b64-e1.md`; SHA256 `026e567d995788d642ec85b3979850515c9a5910c75bae80466691a775005c26`; source state `tracked`
