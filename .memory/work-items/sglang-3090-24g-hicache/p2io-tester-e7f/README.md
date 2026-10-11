# p2io-tester-e7f

- **工作标题：** p2io-tester-e7f
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7f.md`：**
**failed**
e16 修复已在 3090 生效（`forced_miss_tombstone`/`detach_miss_dropped`/`drop_subtree` skip 链路在档），**e7e 崩溃签名（`node X not host-only` AssertionError）已消除**（forced_drop_to_miss 从 e7e 的 59 降到 1），但本次 e7f 全量验证 **6 道硬门全部未过**，且**中途以新的断言崩溃（非干净退出）**：
- 我在 18:33:20 于 `on_idle → invariant_checker._check_tree_cache → tree_core.sanity_check` 触发 **`AssertionError: Sanity check FAILED (4 violations across 55 nodes)`**（node 68 孤儿注册：H-leaf stale / Duplicate ghost / host_leaves stale / mamba host LRU 残留）；引擎 SIGQUIT。驱动因所有 HTTP 请求已完成（最后 finish 18:33:20.8）仍报 `status=done / 96 ok / 0 failed`，但 scheduler 进程是**断言崩溃而非干净关闭**。
- Z3 硬门 FAIL：**1001 次** subtree drop（`KV subtree dropped without backup, root node 31..1077`），`host_pressure` dropped tokens **1,863,428 kv / 960 mamba**（终值）。
- Ready Horizon FAIL：ready_pool 全程仅 1 次、`size=0 tokens=0 watermark=[2,4]`；ready_stage=0——未准入任何请求，当前配置（8G + writeback_reserve 1.5G + safety_margin 0.3G + `hicache_restore_backup_park=False`）下 Ready Horizon 判定为**完全不生效**（与 e7d/e7e 同一结论）。
- Survivability FAIL：245 次 recompute 全部 `final_storage_survivability=host`；24 个 restore 轮次中 **16 轮全 miss（cached_tokens=null → 全量重算）**，仅 8 轮有部分 host/device 命中。
- 4 崩溃/OOM：无（dmesg 干净、`backup_failure=0`、`extent_recycle=0`）。
- **无崩溃跑完全程 FAIL**（新断言 18:33:20）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7f.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7f.md`; SHA256 `1bc616648424618a50f11bf0c812fd1ff4828e9998d23b79cc922a7bcd6f0ab3`; source state `tracked`
