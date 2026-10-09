# phase2-hicache-design-architect-e8

- **工作标题：** phase2-hicache-design-architect-e8
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-architect-e8.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-architect-e8.md`：**
两机制已落成可实现规格。核心结论：
1. **M1 状态机**：Req 侧 `hicache_restore_state` 枚举（NONE/WAIT_CAPACITY/RESTORING/READY）+ wait_reason 子态
   （DEVICE_QUOTA/PREFETCH_BUDGET/HOST_ALLOC/FRONTIER/REVALIDATE）+ 14 条转换表。唤醒 = 每 scheduler pass
   的容量谓词重读（rem_total_tokens ≥ 增量 charge ∧ 非 prefetch_rate_limited）——事件循环本身即
   "device capacity changed" 事件，无需新事件机制。放弃判据与容量判据分离：真 miss（drain revoke
   below-threshold）→ RECOMPUTE；容量性拒绝 → WAIT（有界，默认 60s 超时兜底）。
2. **增量计费谨慎版**：charge = max(0, cand_extend − len(prefix_indices)) + max_new + page + mamba_gap——
   只减已 resident 的 device_hit，host/storage hit 仍全额计费；invariant 证明 Σ resident(active) ≤ pool；
   首访型 charge 不变 → width 仍 1（不违背"不优化 width"）。
3. **M2**：`_storage_frontier_waiters: dict[NodeId, set[str]]` + `_storage_frontier_ready`；注册在
   scheduler.py:2885-2892 gate else 分支（当前静默跳过的缺口）；唤醒挂在 _drain_backup:2551
   advance_storage_persisted 之后（只 set 操作，F2 exactly-once 不受影响）；消费走 reconciliation。
   事件驱动后 retry_poll_interval 可保持默认 0。
4. **关键前置**（R8）：P2-0a A/B 未定案（8 条 prefetch 过 rate-limit 门 + 0 finalize 根因）必须在

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-architect-e8.md`：- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-1-design.md`（主交付，9 节 + 开放问题）
  - §0 定案前提与四处分混淆点（C1-C4，quota deny ≠ recompute decision 的落点）
  - §1 现状机制核查（恢复管线三段 + quota 三门 + is_backuped/frontier 语义区分）
  - §2 M1 状态机（状态图 / 14 条转换表 / per-pass 唤醒 / 增量计费公式 + invariant 证明 / 边界与分离判据）
  - §3 M2 注册表 + ACK 唤醒（waiters/ready 数据结构、与 retry_poll_interval=0 的关系、风暴上限）
  - §4 数据结构与接口（Req 3 字段、UnifiedRadixCache 4 API、纯状态机模块、AddReqResult.RESTORE_DENIED、
    server_args 新参数）
  - §5 改动面清单 13 项（文件:位置:类型:风险:torch-free 标注；5 处 ⚠ 行号漂移）
  - §6 实现顺序（M1a 增量计费 → M1b 状态机 → M2 → 收口回归，每步独立验证点）
  - §7 风险与回退 9 项（R1-R9，含 F2 exactly-once、CHAIN_GAP 不变式专项）
  - §8 埋点 7 事件（P2A 风格）
  - §9 成功判据映射
  - §10 开放问题 6 项

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-architect-e8.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e8.md`; SHA256 `1231428d2564d0d8728b7cb5c1f78ee97fd936e659712196c19f600b149de18d`; source state `tracked`
