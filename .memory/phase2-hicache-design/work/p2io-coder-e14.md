# p2io-coder-e14 — P3 Ready Horizon v0 3.2/3.3 M3 重做（按用户升级规格重做）

## status
done

## artifacts
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — M3 按用户升级规格重做（替代 e14 之前的三修补 epoch_sig+cooldown+decline-park）：
  - 新 `DeclineReason(Enum)`：NO_L3 / NO_HEADROOM / SPEC_BUDGET（每 reason 订阅唯一 causal epoch：NO_L3→l3_publish、NO_HEADROOM→host_headroom、SPEC_BUDGET→spec_budget，`subscribed_epoch()` 订阅表）。
  - 新 `NegativeCacheEntry(msgspec.Struct)`：reason + 订阅 epoch cursor（decline 时刻）+ 请求身份指纹（prefix_len/generation）+ safety-fuse expiry。msgspec.Struct 符合 no-dataclasses 规则。
  - 新 `CausalEpochs(msgspec.Struct)`：l3_publish / host_headroom / spec_budget / waiting_frontier 四 causal epoch 快照；`epoch_event(prev, cur)` 只对可用性改善 delta 触发（l3 推进 / host 页释放 / spec 释放 / frontier 组成变化），refill 自身流量（issue 抬 inflight、耗 free pages）永不触发（e7 旋转根因）。
  - `entry_cleared()`：订阅 epoch 方向性比较（spec_budget: cur<cursor；l3_publish/host_headroom: cur>cursor）+ 身份变化 + fuse 过期；`subscribe_decline()`：无 entry = 从未尝试 = 该 causal epoch 的一次 fresh probe 资格。
  - `staging_candidates()`/`refill_plan()`：签名改为 `negatives=, epochs=, now=`（去掉旧 cooldowns=）；候选排除有 active park 的 rid；两 inflight budget 耗尽时全部排除（M3: park 至 budget-release epoch）。
  - v0 保守 staging（用户裁决 ④）：`_is_ready_resident` 增加 `full_prefix` 条件（READY && staged_tokens>0 && full_prefix）；`ReadyHorizonView` 增 `full_prefix/prefix_len/generation` 字段。partial L3 恢复永不进 READY 池。
  - `headroom_fits()` M1 不变（ready+inflight <= host headroom，2x~21K 链可达）；M2 无驱逐不变。
- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py` — 新增单调 `_l3_publish_epoch` 计数（reset 置 0；`_promote_persisted_subtree` 与 `mark_storage_restored` 中 `_bump_l3_publish()`；`l3_publish_epoch()` 读取）。NO_L3 的唯一清除事件之一。
- `python/sglang/srt/mem_cache/unified_radix_cache.py` — `l3_publish_epoch()` 委托 tree_core。
- `python/sglang/srt/managers/scheduler.py` — `init_ready_horizon` 改用 `_ready_horizon_negatives: dict`（rid→NegativeCacheEntry）+ `_ready_horizon_epoch_prev: Optional[CausalEpochs]`（取代 EpochSig/cooldowns）；`_ready_horizon_pass` 重做：建 views→`_ready_horizon_epochs()`→`epoch_event` 门→`should_refill`（event 或 5s 安全对账）→prune negatives 到 frontier→headroom→`refill_plan`→记 NO_HEADROOM park→issue 并记 ready_stage 日志（attempted/issued 区分，保留上轮 ⑤）→同步 decline 记 SPEC_BUDGET park→budget 耗尽 park 未试尾→ready_pool 变更日志；`_park_ready_decline()`（订阅 epoch cursor 快照 + fuse）；`_feed_restore_terminal` 在 REVOKED_MISS genuine_miss 时记 NO_L3 negative-cache（cursor=当前 l3_publish_epoch）——确定性 miss 不再下一 pass 重试；`policy_epoch_value()` 模块 helper。旧 EpochSig/cooldown 引用全清（grep 确认 exit=1 无匹配）。
- `3090-dev/test_ready_horizon_unit.py` — 重写至新 API（55 个单测，全绿）：M6 含 full_prefix（partial 不 stage，裁决 ④）；NegativeCacheTests（NO_L3 同 epoch 不重试/仅订阅 epoch 清除、订阅表映射、每 rid 每 causal epoch 一次 attempt、identity/fuse 独立断言）；CausalEpochEventTests（四 epoch 方向性、refill 自身流量非事件）；DeterministicMissParkTests（假时钟 `_FakeClock` + `mock.patch time.perf_counter`：fuse 活窗口挡 re-probe、fuse 过 + l3 推进才一次 fresh probe、re-park 新 cursor、同 causal epoch 不再试）；ReadyHorizonPassTests 跑真实 `_ready_horizon_pass`（含 off 模式零接线、ready_stage 日志 result=issued）。

## evidence
- RED：初版新单测失败 3（`pop_storage_prefetch_terminal` 桩缺失）→ 补桩后失败 2（DeterministicMissPark 无假时钟，fuse 活窗口挡 re-probe）→ 假时钟重写后 GREEN。逐次真实失败→修复（非伪造 RED）。
- 全门：`cd 3090-dev && PYTHONPATH=<repo>/python python3 -m unittest test_storage_regression test_hicache_restore test_drain_reentry test_hicache_restore_scheduler_feed test_prefetch_budget_split_unit test_ready_horizon_unit test_ready_horizon_partition` → `Ran 297 tests ... OK` exit=0。分文件计数：storage_regression 94 / hicache_restore 69 / drain_reentry 30 / scheduler_feed 7 / prefetch_budget_split 24 / ready_horizon_unit 55 / ready_horizon_partition 18 = 297（94+69+30+7+24+55+18 一致）。274 既有全在（ready_horizon_unit 旧 32 → 新 55，净增 23）。
- 单测独立复跑 `python -m unittest test_ready_horizon_unit` → `Ran 55 tests ... OK` exit=0。
- `python3 -m py_compile` 5 个改动文件 → `PY_COMPILE_OK` exit=0。
- `import sglang; sglang.__file__` = `<repo>/python/sglang/__init__.py`（PYTHONPATH 强制本地树）。
- on-disk 确认：`grep -n l3_publish_epoch` tree_core 4 处 / radix_cache 2 处；`grep -n ready_horizon_negatives|_park_ready_decline|policy_epoch_value|DeclineReason.NO_L3` scheduler.py 15 处；stale 引用扫描（EpochSig/cooldowns）exit=1 无匹配。
- M1/M2 不回退：prefetch_budget_split 24 单测全绿（PREFETCH_BUDGET 驻留约束）；ready_horizon 无任何驱逐路径（headroom/budget 耗尽 silent decline）；HeadroomConstraintTests 2 链 41,820>21,392 证明旧 inflight 上限已被 headroom 模型取代。

## summary
M3 按用户裁决重做完成：三修补（epoch_sig 排除+cooldown+decline-park）整体替换为 **per-rid causal negative-cache / event-driven eligibility**。每个 decline reason 订阅唯一能改变它的 causal epoch，cursor 方向性比较，确定性 miss 不再瞬态重试；cooldown 降级为 1s safety fuse（仅异常风暴 rate 上限，正确路径节奏是 causal epoch 推进而非等待）；每 rid 每 causal epoch 至多一次 staging attempt（cursor 记录天然保证）；v0 保守 staging 只对完整前缀（storage_hit==requested_prefix）进 READY 池，partial 不 stage。NO_L3 唯一清除事件：l3_publish 推进 / prefix 变 / generation 变 / fuse（保险丝，与订阅事件叠加）；普通 pass、running batch、READY pool 变化不解除。M1（headroom 模型 2x21K 链可达）与 M2（spec eviction=0）成果不动。ready_stage 日志保留 attempted/issued 区分。

## followups
- 3090 同步（ready_horizon.py / scheduler.py / unified_tree_core.py / unified_radix_cache.py + 测试，md5 双侧、.bak-v0 备份）由 orchestrator 执行。
- 3.4 集成验证（tester）：READY_HORIZON=1 M4T 完整 run；B≤1.2s 硬门；M3 事件驱动在真实 L3 推进节奏下的 re-probe 频率观测（对比 e7 的 141/s 与 1289 issue/9.04s 基线）。
- 后台 agent a435c909a56982771（e8 后整链 p50/p90 重测）仍在跑，勿重复派发。

## open_issues
- 无阻塞项。注意点：safety fuse 1s 是用户裁决的保守初值，若真实场景 NO_L3 与 l3_publish 推进间隔 <1s，re-probe 会被 fuse 额外限速（保守方向，安全）。
