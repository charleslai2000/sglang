# p2io-coder-e12

- **工作标题：** p2io-coder-e12
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e12.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e12.md`：**
3.2 交付齐：ready_horizon 纯函数协作模块 + scheduler orchestration 接线（构造期 init、`_reconcile_restore_states` 后每 pass 调用、委托 `_prefetch_kvcache`、变化驱动 P3 日志）+ server_args 三旋钮 + 32 单测，全门 256 绿。M6 用 staged 标记（finalize 写入、准入 pop 消费的 `prefetch_loaded_tokens_by_reqid`）判定物理驻留，非简单 state==READY。M3 用 epoch 签名（资源计数器 + frontier 组成 + ready_count + running_bs，不含逐请求 state）实现事件驱动，5s safety reconciliation 兜底。M2 禁驱逐：策略/接线路径零 evict 调用，headroom 与预算不足均静默空 plan。headroom 语义：`host_headroom = available_size + ready_resident`（= pool.size − working_set），门 `ready + inflight ≤ headroom` ⟺ inflight ≤ 空闲页——READY 驻留不再被 0.5×pool inflight 预算否决（M1 验收 2×20.9K 成立）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e12.md`：- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` (new) — `ReadyHorizonPolicy` 纯函数协作类（frontier / ready_count M6 / ready_resident_tokens / staging_candidates / headroom_fits / refill_plan / should_refill）+ `ReadyHorizonView` / `RefillPlan`（msgspec.Struct）。领域逻辑全部在模块内，scheduler.py 只委托。…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e12.md` → `.memory/phase2-hicache-design/work/p2io-coder-e12.md`; SHA256 `6dfa094edf175d9549d4db80e1c9faae48b75acd3e6a95507ee22bcff50a5b2a`; source state `tracked`
