# P5-MAMBA-FINAL-AND-PROD-START-20260918

- **工作标题：** P5-MAMBA-FINAL-AND-PROD-START-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/P5-MAMBA-FINAL-AND-PROD-START-20260918.md`：**
Execute the mamba-pool sizing experiment to completion (cells `max_mamba_cache_size = 48, 56, 64`),
pick the smallest size that removes/materially suppresses the `mamba_available_tokens==0 ->
WAIT_CAPACITY -> extreme TTFT tail` with no OOM and safe VRAM, then START production on :30000 and HOLD.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** WORKING

**`phase2-hicache-design/agents/P5-MAMBA-FINAL-AND-PROD-START-20260918.md`：**
IN PROGRESS. Cell-48 attempt (sweep4) was externally SIGTERM'd at 23:59:13 mid-load by a
competing session (see Evidence). Retrying cell-48.

### 报告列出的产物/证据
- `phase2-hicache-design/agents/P5-MAMBA-FINAL-AND-PROD-START-20260918.md`：- Approvals: `OWNER-APPROVAL-20260918-PROD-START` (ledger line 9520) + the 2026-09-18 entry
  "Mamba 定档必须真跑出来" (ledger ~9630).
- GPU takeover at 23:56:31-23:56:37: stopped the in-flight production start (client `start.sh prod`
  pid 1738571, supervisor pid 1738792, server pgid 1738819) identity-checked; GPU verified clean
  (no launch_server, ports 30000/30160 free, flock FREE, no compute apps).
- sweep4 cell-48: run `sweep4-mamba48-20260917T235645Z-1740204`, server pid 1740265, UP 23:58:39
  lock gen 15. Load 8/128 ok; server received external `SIGTERM` at 23:59:13 (console line 1136).

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/P5-MAMBA-FINAL-AND-PROD-START-20260918.md` → `.memory/phase2-hicache-design/agents/P5-MAMBA-FINAL-AND-PROD-START-20260918.md`; SHA256 `8425b77e789d5235c3fc0793d74dc711ca192a9ed390cdcab1270f51584ccaea`; source state `tracked`
