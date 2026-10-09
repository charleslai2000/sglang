# MAMBA-SWEEP-48-56-64-20260918 (RE-ISSUED replacement owner)

- **工作标题：** MAMBA-SWEEP-48-56-64-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-SWEEP-48-56-64-20260918.md`：**
Determine the SMALLEST `max_mamba_cache_size` (sweep 48=control / 56 / 64) that removes or
materially suppresses the production `mamba_available_tokens == 0 -> WAIT_CAPACITY -> extreme TTFT
tail`, with no OOM and safe VRAM, by cloning the captured production argv verbatim on a different
port (30160) and varying only `--max-mamba-cache-size`. Then unconditionally restore production on
:30000 and verify.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** BLOCKED (terminal)

**`phase2-hicache-design/agents/MAMBA-SWEEP-48-56-64-20260918.md`：**
**No mamba size can be recommended from this invocation's measurement. The sweep is incomplete
(cells 48 and 56 completed; cell 64 never completed) and — more fundamentally — the completed
cells did not reproduce the production failure signature, so 48 vs 56 does not test the defect.**
- **Recommended smallest `max_mamba_cache_size`: none determinable.** The task explicitly forbids
  guessing; the measured data does not isolate the production failure mode.
- **KV trade needed?** None was applied by me. `--max-total-tokens 524288`, `--context-length
  131072`, `--max-running-requests 8` were held byte-identical across all cells. Raising the mamba
  size does shift the fixed 32 GB `--hicache-size` split: 48 -> KV host 1,509,560 tok / 24.73 GB,
  mamba host 7.31 GB; 56 -> KV host 1,455,589 tok / 23.85 GB, mamba host 8.19 GB (a ~53,971-token,
  ~3.6% KV-host reduction for +0.88 GB mamba host). This is an automatic side effect, not a manual
  KV trade.
- **Production restored? NO — production is DOWN at terminal write.** Phase 3 restore was
  attempted but correctly failed closed because a concurrently dispatched sibling task holds the
  GPU (see Defects). The restore is owned by the active sibling task `P6-MAMBA-CORRECTED-AND-PROD-START-20260918`.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-SWEEP-48-56-64-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-SWEEP-48-56-64-20260918.md`; SHA256 `5eb43401f6a8cff6bc27f0af5c2eedadb0b93ceb50f5005c8d35b76af52dbf8a`; source state `tracked`
