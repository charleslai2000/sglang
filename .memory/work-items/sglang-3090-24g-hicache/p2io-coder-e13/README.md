# p2io-coder-e13

- **工作标题：** p2io-coder-e13
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e13.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e13.md`：**
M4 交付完成：调度链变为 calc_priority → partition_ready_first（稳定分区）→ PrefillAdder 准入。显式优先级判定：`enable_priority_scheduling` 开时以 `req.priority` 等值最大连续 run 为组（calc_priority 的排序键是 `priority * priority_sign`，sign 每次 pass 恒定，等值分组不受方向影响），READY 永不越过分组边界（两个方向都不越——run 边界双向成立），组内稳定前置；flag 关时 policy 根本不读 priority，整队列一个 run。off 门控在 scheduler 单点（`if self.enable_ready_horizon:`），零调用即逐字节等于今日。⑥ 验证：既有 continue 语义（ongoing/WAIT skip）不新增，分区只前置 READY。M6 标记复用 `_ready_horizon_views` 同一 lookup（buffer_only → staged_prefetch_tokens，否则 peek_prefetch_loaded_tokens）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e13.md`：- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — 新增 `ReadyHorizonPolicy.partition_ready_first()` + `_req_is_ready_resident()`（M4 稳定分区，显式优先级 > READY > 原 policy）+ 模块 docstring 追加 M4 说明。实现：按 `req.priority` 等值最大连续 run 分组（`priority=True` 时），run 内 READY（M6：state==READY && staged 标记>0）稳定前置，run 间保原序；`priority=False` 时整队列一个 run。返回新列表，输入不动。
- `python/sglang/srt/managers/scheduler.py` — `_get_new_batch_prefill_raw` 内 calc_priority（:4022）之后、TEST_RETRACT 块之后、PrefillAdder 构造（:4052）之前，插入一行门控调用：`if self.enable_ready_horizon: self.waiting_queue = self.ready_horizon.partition_ready_first(...)`（传 tree/buffer_mode/enable_priority_scheduling）。schedule_policy.py 零改动。…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e13.md` → `.memory/phase2-hicache-design/work/p2io-coder-e13.md`; SHA256 `36d661b4a425dab7b38ac141d2c93146920f79fd6726e3e4012a28172d5343ee`; source state `tracked`
