# DBG-20260908-T38C

- **工作标题：** DBG-20260908-T38C
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DBG-20260908-T38C.md`：**
- Task / epoch: `DBG-20260908-T38C` / `2026-09-08`.
- Scope observed: read-only inspection of active worktree cache/storage code and
the designated 24052 evidence (`/root/evidence-gate3-parked/s25-durable-settle-t38c`,
`/tmp/t38c-probe.log`). No product or control-plane files were changed.
- Status: **done**.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DBG-20260908-T38C.md`：**
The observed `extra_pool_hit_pages={"kv": 55145}` is **not** a successful
sidecar result.  It is the raw, contiguous attention-KV prefix discovered before
the auxiliary-pool fold.  The active extent backend then folds the usable prefix
with `min(final_pages, boundary)` for each auxiliary transfer.  For the T38C
Mamba model, the only such transfer is the Mamba checkpoint transfer.  Its
TRAILING_PAGES scan returns `boundary=0`; therefore the returned
`kv_hit_pages` is zero and the scheduler revokes the prefetch as a full miss.
Thus the direct cause of the zero is **the Mamba trailing-checkpoint input to
the generic `batch_exists_v2` fold**, not loss of the direct KV pages and not an
ALL_PAGES-policy fallback.  The generic fold is operating as designed: it must
not declare an attention-KV prefix restorable without the recurrent state needed
to continue it.
The evidence does **not** yet distinguish these two sub-causes of the zero
Mamba boundary:


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DBG-20260908-T38C.md` → `.memory/phase2-hicache-design/work/DBG-20260908-T38C.md`; SHA256 `34cea5e438e02212431af71d7aadfd7d9168473468214268679df7b03f96bfd9`; source state `tracked`
