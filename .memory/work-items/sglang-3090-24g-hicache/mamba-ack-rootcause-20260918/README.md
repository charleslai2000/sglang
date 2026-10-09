# MAMBA-ACK-ROOTCAUSE-20260918

- **工作标题：** MAMBA-ACK-ROOTCAUSE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-ACK-ROOTCAUSE-20260918.md`：**
READ-ONLY root-cause of the FIRST break in the Mamba ACK/unpin chain:
`backup submit (write_storage) -> ACK produced by backend -> ACK queued -> scheduler drains ACK -> unpin (ongoing_backup.pop -> dec_host_lock_ref)`
Classify the first break as exactly ONE of:
(a) ACK never produced by the L3 backend;
(b) ACK produced but dropped / never enqueued;
(c) ACK enqueued but the scheduler never drains the queue;
(d) ACK present but filtered/rejected by a generation/ownership/durability predicate;
(e) the only release path ever taken is shutdown detach (normal in-run drain structurally unreachable for Mamba backups).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-ACK-ROOTCAUSE-20260918.md`：**
**Primary verdict: (a) ACK never produced by the L3 backend.**
The L3 backend produced **zero durable commits for the entire failing run**. Because the controller-level ack
is enqueued only after `_page_backup` returns True, zero commits means the ack is never enqueued, the
`ack_backup_queue` never fills, the (fully reachable) scheduler drain has nothing to drain, and the
submit-time pin at `unified_radix_cache.py:5004-5007` is never released in-run. The pin is released only
later by shutdown detach, which is why 128 mamba nodes stayed pinned until 23:06:30.
Established components of the chain:
- **Submit: ESTABLISHED (submits occurred).** Pins are acquired only at `unified_radix_cache.py:5004-5007`,
  immediately after `cache_controller.write_storage(...)` returns (`:4974`). The 23:06:30 teardown event shows
  `pool="mamba", cause="lock_release_evictable", evictable_before 0 -> after 128, telemetry_mutation_count 128`
  from `dec_host_lock_ref` — i.e. 128 mamba nodes transitioned out of `host_lock_ref>0` in one coalesced burst.
  Known non-backup pin sources are far too small to account for that: `load_back_tokens_total{mamba}` = 38-40
  (`/tmp/opencode/mam_metrics{,2,3}.txt`) and `prefetch_issued` count = 13 (`server.console.log`). So the
  large majority are `ongoing_backup` entries and the submissions definitely happened.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-ACK-ROOTCAUSE-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-ACK-ROOTCAUSE-20260918.md`; SHA256 `03ff055344ae40bc5549f3006fbbf792f54d73f8ecf09dce2ad8e136540b8d4d`; source state `tracked`
