# MAMBA-D1-OWNERSHIP-FIX-20260918

- **工作标题：** MAMBA-D1-OWNERSHIP-FIX-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-D1-OWNERSHIP-FIX-20260918.md`：**
Step (2) of the owner's ordered plan (3 -> 1 -> 2). Repair the REAL Mamba L3-backup pin
ownership/lifecycle so that an in-run backend failure cannot leak a submit-time host pin until
shutdown.
Binding owner ruling (do NOT violate): route backend failure through the EXISTING storage-failure
ownership path (`_handle_storage_failure` / `storage_failure_reason`); restore fatal handling in
the hybrid `backup_thread_func`; make `_page_backup` failure ATTRIBUTABLE. A timeout / forced-unpin
watchdog MUST NOT become the normal lifecycle. An orphan-pin invariant guard is acceptable only as
a last-resort safety net, never as the mechanism.
Acceptance: (1) a backend failure that prevents the ack is observable, not silently swallowed;
(2) it is routed through the existing storage-failure path so the affected `ongoing_backup` pin(s)
are released in-run, exactly once, via the SAME ownership mechanism (not a new timer); (3) a
dead/failed backup thread likewise leads to in-run pin release; (4) exactly-once release; no
double-dec; no release of a pin whose write actually succeeded; allocator remains final authority.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-D1-OWNERSHIP-FIX-20260918.md`：**
**The pin-lifecycle break is repaired by making a failed L3 backup a terminal, attributable
storage failure that flows through the pre-existing degraded-storage ownership path.**
Minimal, localized change in `hybrid_cache/hybrid_cache_controller.py` (the only production file
I changed; frozen-tree counterpart `hybrid_cache/hybrid_cache_controller.py`, same class
`HybridCacheController`):
1. **Attributable failure helper** `_fail_backup(operation, reason, *, exc_info=False)` (new,
   `:1107-1127`). Records `operation.backup_failure_reason`, logs at ERROR with the operation id
   and node id, and always returns False. Every failure branch of `_page_backup` now returns
   through it instead of a bare `return False`:
   - `:1177` `sidecar_set_failed`
   - `:1215` `kv_set_failed`
   - `:1219` `group_commit_failed`
   - `:1222` `sidecar_set_failed`
   - `:1224-1229` `except Exception as exc -> exception:<Type>: <msg>` with `exc_info=True`

### 报告列出的产物/证据
- `phase2-hicache-design/agents/MAMBA-D1-OWNERSHIP-FIX-20260918.md`：All commands run CPU-only in `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` with
`/opt/sglang/local-prod-v1/env/bin/python`, `CUDA_VISIBLE_DEVICES=999`,
`PYTHONDONTWRITEBYTECODE=1`.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4462403d`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-D1-OWNERSHIP-FIX-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-D1-OWNERSHIP-FIX-20260918.md`; SHA256 `277bedfe1910653f55442bdc048cb7f47fb51e9232f7376ecb7d2b05223f3d8a`; source state `tracked`
