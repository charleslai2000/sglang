# M2-HICACHE-RELEASE-DESIGN-R2-20260918

- **工作标题：** M2-HICACHE-RELEASE-DESIGN-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`：**
Design (NOT implement) a single-GPU-window release that (i) installs an M2 frozen runtime whose
launcher serves with HiCache ON, and (ii) promotes the telemetry src revision (shared src ⇒ M1 also
gets it, M1 must remain correct). Answer D1..D7 with file:line anchors, exact literals, an ordered
runbook, and rollback. READ-ONLY: no product/frozen-tree/scaffold edits, no GPU, no signalling, no
port binds, no freeze execution.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`：- `M2-CONCURRENCY-DEGRADATION-RCA-20260918.md` (DONE): prefix retention on M2 is bound by the mamba
  slot pool (`--max-mamba-cache-size 48`, 4 slots/req): N≤14 holds, collapses to 1/16 at N=16 while
  KV had ~190k tokens free (X-c/X-d). Attaching HiCache gives 24/24 retained with mamba
  free/evictable flat (~2/42) and eliminates the cold-prefill queue. X-f isolated
  M2+HiCache on `:30164` with `--enable-hierarchical-cache --hicache-write-policy write_back
  --hicache-size 32` → console `hicache_attached=True`, retention 16/16, 24/24.
- `HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md` (DONE): internal cached-token accounting exists,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md` → `.memory/phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`; SHA256 `fcf16706fad466b8ea7f30ac92ca6ff0e3f025e26dbf43d3b404c4197ab3c938`; source state `tracked`
