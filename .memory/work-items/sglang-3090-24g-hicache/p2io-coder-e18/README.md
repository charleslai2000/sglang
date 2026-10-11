# p2io-coder-e18

- **工作标题：** p2io-coder-e18
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e18.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e18.md`：**
P3 Ready Horizon 容量模型重构完成：RH 由 request-count 驱动的 READY_HOST 池维护改为 **KV-host TOKEN 容量核算**。核心模型 `KV_usable = KV_pool - writeback_reserve - margin`，RH 仅当 `working + ready + inflight_spec <= KV_usable` 才 admit；write-back reserve 语义从固定 GB 份额（22%/0.75GB）改为"至少一个目标写回态的 KV tokens"（runtime 按 state size 计算）。九 gauge 以 token 空间发布容量模型（无 GB 猜测）。迁移双轨：token 语义为生产默认（Watermark 1/2×State_p95），count 语义经显式 `*_count` args 保留（legacy 兼容），GB knobs 标记 LEGACY 仅在 token 值未设时生效。既有 311 测试零回归 + 14 新测试全绿（325 OK）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e18.md`：- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — capacity-model RH policy：
  - 类默认 `token_mode: bool = False`（legacy count fallback，直接策略构造保持 count 语义）；调度器经 `init_ready_horizon` 用新 server_args 启用 token 语义。
  - `_issue_budget(ready_count, ready_tokens)` 签名改（count 模式仍 `max(0, watermark_high - ready_count)`）；`refill_plan` call site 改 `budget = self._issue_budget(ready, tokens)`。
  - `describe_watermarks` 恒 `f"{low}/{high}"`（不再 append "count"，保持现有 `watermark=[2/4]` 日志）。
- `python/sglang/srt/managers/scheduler.py` — 容量核算接线：…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e18.md` → `.memory/phase2-hicache-design/work/p2io-coder-e18.md`; SHA256 `12c29e2c6214d5601e251bdef9f1d94f1dd7f2991de1e390ea66185e2242db46`; source state `tracked`
