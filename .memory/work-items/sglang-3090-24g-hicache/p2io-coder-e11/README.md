# p2io-coder-e11

- **工作标题：** p2io-coder-e11
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e11.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e11.md`：**
3.1 交付完成：M1（spec 子预算 `prefetch_speculative_capacity_limit` + `inflight_speculative_tokens` 计数器，物理计数保留原名）、M5（`PrefetchReservation` + `reserve_prefetch`/`release_prefetch` 单 helper，finalize/revoke/abort/hybrid-discard/detach 五路径 exactly-once，upstream #31445 泄漏类 bug 防护）、M2（speculative staging alloc 失败静默 decline，仅 DEMAND/off 基线可 evict_host——`evict_host` 在 prefetch 路径唯一调用点 `_try_alloc_storage_hit` 已确认）、scheduler 接线（T11/T12 wake re-issue 在 flag on 时全部 demand 分类，T15 票池不动）。off 语义逐字节论证见 open_issues 附注；双模测试证明。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e11.md`：本机 venv（torch 2.13.0+cu129），`PYTHONPATH=python:3090-dev` 强制本地树（`sglang.__file__` = 仓库 python/ 已核）。
RED→GREEN（TDD）：新测试文件先于实现运行 → 3 failures + 18 errors（PrefetchKind/reserve/release/两轨全缺，scheduler 接线 [False]≠[True]）；实现后 24/24 OK。
全门（实现后最终跑）：
| 套件 | 结果 |
|---|---|
| 3090-dev.test_hicache_restore（64→实际 69） | Ran 69 OK |
| 3090-dev.test_drain_reentry（30） | Ran 30 OK |
| 3090-dev.test_hicache_restore_scheduler_feed（7） | Ran 7 OK |
| 3090-dev.test_storage_regression（94） | Ran 94 OK |
| 3090-dev.test_prefetch_budget_split_unit（新 24） | Ran 24 OK |
| test_extent_file_backend_unit（70）+ test_hicache_file_lru_unit（34） | Ran 70 OK / Ran 34 OK |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e11.md` → `.memory/phase2-hicache-design/work/p2io-coder-e11.md`; SHA256 `bc0c55a64912ac70d9e9b2cd9f91ed4dafce98da3c22d0f6ada5609257550bd3`; source state `tracked`
