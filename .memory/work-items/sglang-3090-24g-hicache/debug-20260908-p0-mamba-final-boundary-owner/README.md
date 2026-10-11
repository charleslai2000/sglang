# DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER

- **工作标题：** DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER.md`：**
R8 is best explained by a **lifecycle/provenance loss at the finalization
boundary**, not by a 55K workload that never crossed a legal Mamba checkpoint.
The build vehicle uses `max_tokens=12`.  R8 directly records extra-buffer
Mamba, page size one, and 2048-token prefill chunks.  The current Qwen3.5
configuration/default in this workspace has `mamba_track_interval=256`; R8's
preserved summary does not include a full resolved-argument record showing that
field.  Under that configuration, a prefill chunk creates a Mamba checkpoint candidate at its page-aligned
checkpoint grid; when that chunk is cached as unfinished, the Mamba component
donates/records that state and then deliberately clears the request-local
`req.mamba_last_track_seqlen`.  The subsequent at-most-12-token decode cannot
reach a 256-token decode tracking boundary, so it does not repopulate the
field before `release_kv_cache()` calls final `cache_finished_req()`.
At R8's historical finished boundary, `None` was converted to zero, producing
an empty radix key.  TreeCore returned root for that key, the finished path

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER.md`：- R8 direct chronology and root theorem:
  `.memory/phase2-hicache-design/work/DEBUG-20260908-P0-R8-ROOT-NODE.md`.
- R8 cleanup/preservation record:
  `.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-S25-LIVE-R8-CLEANUP.md`.
- V3 producer contract and exact finalized-node requirement:
  `.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`.
- Mamba semantic contract and fail-closed prior-node invariants:
  `.memory/phase2-hicache-design/work/DOMAIN-20260908-P0-MAMBA-FINISH-LENGTH.md`.
- Accepted unit gates consulted: `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX1.md`,
  `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX2.md`, and…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER.md` → `.memory/phase2-hicache-design/work/DEBUG-20260908-P0-MAMBA-FINAL-BOUNDARY-OWNER.md`; SHA256 `731556aa56458f193ad6ff05b38cc2c65b4c18dc370d0303bc9009c6de2be53c`; source state `tracked`
