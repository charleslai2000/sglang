# phase2-hicache-design-tester-gate2-fbe-rerun

- **工作标题：** phase2-hicache-design-tester-gate2-fbe-rerun
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-fbe-rerun.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-fbe-rerun.md`：**
**Primary gate (aggregate effective cache ratio >= 95%, exact-restore
methodology): FAIL.** K=16 L0 exact restore ratio 0.7843 (well below 0.95) and
33% (16/48) genuine full-miss; the L0 0-hit cliff was NOT closed to ~0 as the
dispatch's core expectation predicted.
**FBE verdict: correct but insufficient.** The HOST->L3 break-hop that FBE was
built to close (sidecar dropped at host eviction before deferred L3 persist)
is real and one contributing full-miss mechanism, but it is NOT the dominant
one in this load. The dominant defect is a restore-side issue: the L3 restore
lookup returns 0 pages for a chain even when that chain's KV was written to L3
before the query (958/958 such queries zero-hit). Because the restore can't
read the mamba back from L3 regardless of durability, making it more durable
(FBE) has roughly no effect on the aggregate cliff: full-miss went K16 45% ->
44.5% (phase-B), L0 41.7% -> 33.3%. The tiny improvement (41.7 -> 33.3) likely
reflects the genuine FBE-covered cases (host-eviction sidecar loss), which are

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-fbe-rerun.md`：Gate-2 re-run on 3090 after the flush-before-evict (FBE) fix, K=4/8/16 three
tiers, same config as the gate2-saturation baseline (write_back + extent +
HICACHE_SIZE=0 pool 106 slots + extra_buffer + int8 mamba OFF). Verified FBE
deployed (mamba_component.py md5 MATCH local, unit tests 8/8 green on the live
3090 tree). **Pure verification, no code changes.** Report path
`phase2-hicache-design-tester-gate2-fbe-rerun.md` (3090 + local copy). 3090
left clean (no engine, GPU 15MiB, no locks); three fresh experiment namespaces
`/data/l3/p2io-gate2-fbek{4,8,16}` remain as evidence.
Deliverables / evidence (all on 3090):
- Run dirs: `/root/evidence-gate2-fbek4/run-20260904-132353`,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-fbe-rerun.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate2-fbe-rerun.md`; SHA256 `3c58497c6c9c1d9251bc0aa6ca76670363d5be35254b01f93c6bc33251c3cd26`; source state `tracked`
