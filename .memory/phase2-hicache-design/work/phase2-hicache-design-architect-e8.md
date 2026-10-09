# phase2-hicache-design-architect-e8 — P2-1 最小版设计细化（M1 + M2 落地规格）

## status
done

## artifacts
- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-1-design.md`（主交付，9 节 + 开放问题）
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

## evidence（设计依据的代码事实，全部当前工作树核实）
- 准入门全长计费 + rem_total_tokens：schedule_policy.py:1234-1246（门 1）、1286-1288（门 2）、671-693（rem 定义）、506-509（AddReqResult）
- load_back 设备配额静默回落：unified_radix_cache.py:1535-1542（evict_for_alloc 后仍不足 → False）；init_load_back 空匹配：2933-2982
- prefetch issue 三拒绝：unified_radix_cache.py:1824-1846（too_short / rate_limited → missed_rids）、1896-1921（alloc_failed）；注册表 395；ongoing_prefetch 392
- finalize/occupied 回减/loaded 登记：unified_radix_cache.py:2014-2117（2103/2105）；revoke 路径 2468-2495（terminated 2471 / below-threshold 2493）
- admission ongoing-prefetch skip：scheduler.py:3584-3592；deny 处理 + break：3621-3650
- 重试 no-op：scheduler.py:2912-2940；默认 interval=0 / max_attempts=4：server_args.py:2830-2836
- is_backuped 前置门纯跳过：scheduler.py:2885-2892；gate 内重匹配：2843
- frontier ACK 推进唯一站点：unified_radix_cache.py:2537-2560（2551 advance_storage_persisted）；tree 语义：unified_tree_core.py:150-152（backuped）、1928-1940（storage_persisted）、505（node_exists）
- F1（1400-1407 evict 重试）/ F2（drain exactly-once，2bdfcb5327）/ KeyError 修复（caeadcf492）已核实
- abort 清理出口：unified_radix_cache.py:2238-2280 release_aborted_request；事件循环 pass 结构：scheduler.py:1813-1845、3446-3449
- torch-free 测试先例：3090-dev/test_drain_reentry.py（stubenv 引导，真实类 + stub 协作者）

## summary
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
   K=8 主判据验证前用 N1/N2 埋点裁决——M1 对该异常只兜底不解决。
5. **实现顺序**：M1a（增量计费，独立先行）→ M1b（状态机+唤醒，主力 1.87M→0）→ M2（42ms-gap 型）
   → 收口回归（CHAIN_GAP / t38 / drain reentry / K=1 基线）。

## followups
- coder 按 §5 改动面 13 项 + §6 顺序实施（Step 1 M1a 可立即开工，torch-free 单测先行）
- tester：Step 1 K=1 基线回归 + K=8 deny 计数观察；Step 2 K=8 主判据；Step 3 42ms-gap 场景
- 专家拍板 §10 O1（增量计费默认开）与 O2（超时 60s 默认值）

## open_issues
- O1/O2/O4：增量计费开关、超时默认值、状态机模块化（设计已给建议，待拍板）
- O3：WAIT 超时（退化 RECOMPUTE）与 SGLANG_REQ_WAITING_TIMEOUT（abort）正交性确认
- O5（= R8）：P2-0a A/B 未定案 → N1/N2 埋点裁决为 Step 2 前置依赖
- O6：engine 修复并行中，§5 五处 ⚠ 行号按实现时新树重新定位
