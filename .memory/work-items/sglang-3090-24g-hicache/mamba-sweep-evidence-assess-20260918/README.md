# MAMBA-SWEEP-EVIDENCE-ASSESS-20260918

- **工作标题：** MAMBA-SWEEP-EVIDENCE-ASSESS-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-SWEEP-EVIDENCE-ASSESS-20260918.md`：**
Determine whether the mamba-pool sweep evidence already captured on disk is sufficient to pick
`max_mamba_cache_size` (candidates 48 / 56 / 64) for production, **without re-running** the sweep.
The sweep was aborted by a higher-priority production restore. Required: inventory the preserved
evidence, tabulate per-cell metrics with sources, compare cells, and decide whether the size is
already determinable (recommend a size, or name the exact missing measurement). Also record the
cell launch parameters and any KV-pool trade evidence.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-SWEEP-EVIDENCE-ASSESS-20260918.md`：**
**IS THE ANSWER ALREADY DETERMINABLE?  NO.**
The preserved evidence does **not** contain a completed measurement of the production failure mode,
and the one completed 48-vs-56 pair does not show suppression. Three concrete reasons:
1. **The production tail was a mamba *host/L2* pool exhaustion (`WAIT_CAPACITY reason=HOST_ALLOC`,
   `failed_domains=["mamba"]`), but neither completed sweep cell reproduced it.** In the production
   run there were exactly **42** `state=WAIT_CAPACITY reason=HOST_ALLOC` entries and **42**
   `restore_host_alloc_retry_result` records with `"failed_domains": ["mamba"]` (free_before=0,
   required≈3436–3556 tokens), each parked for a full **60 s** (T13 clock). In the two completed
   sweep cells the 117+117 `WAIT_CAPACITY` entries are **all `reason=FRONTIER`** (an ordering/ACK
   wait), and there are **zero** `HOST_ALLOC`/`failed_domains`/`aux_alloc_failed` records. The sweep
   therefore did **not** exercise the mechanism the fix is supposed to address, at either size.
2. **The device availability signal named in the dispatch does not discriminate.** `cell-48` and
   `cell-56` both reach `mamba_available_min = 0.0` (the pool's *schedulable* free-slot gauge), both
   hit 0 in a similar fraction of samples (27/242 vs 22/203), and both show `mamba_used_max = 32`.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-SWEEP-EVIDENCE-ASSESS-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-SWEEP-EVIDENCE-ASSESS-20260918.md`; SHA256 `e909ef7b436283d455cc434aa6364581f08a859d3af07ac4e4862c11cb532155`; source state `tracked`
