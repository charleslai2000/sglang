# p2-0-02 coder-e1 报告（恢复路径日志/探针字段盘点）

- 任务: phase2-hicache-design / p2-0-02（Batch 1 并行，只读勘察）
- agent: coder（epoch 1，后缀 -02）
- status: done

## 1. 交付物

- 产出文档: `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/log-field-inventory.md`（新建，目录已创建）
- 未修改任何引擎文件（只读勘察）；未 commit 未 push

## 2. 清单要点

### 2.1 mem_quota 压缩路径调用链（≥3 处，实际 8 处）
- 定义: `base_prefix_cache.py:161-168`（`InitLoadBackParams.mem_quota: Optional[int] = None`）
- 调用点: `schedule_policy.py:1320-1327`（prefill，未传 mem_quota）、`decode_hicache_mixin.py:207-213`（decode，未传）、`unified_radix_cache.py:2941-2942`（buffer 分派）、`streaming_session.py:627-628`（delegate）
- 门判点: `unified_radix_cache.py:1528-1533`（阈值+mem_quota 全有全无门）、1535-1542（avail/evict 门）、1554-1556（cc.load 失败）；legacy 对照 `hiradix_cache.py:1418-1420`（"load it all or not at all"）、1446-1453（失败告警）
- **关键修正**：全仓 `mem_quota` 仅 13 行、无任何调用者传非 None → **mem_quota 门当前 inert**；"restore quota 压缩"的现役机制 = ① L3→H 预算门 `prefetch_rate_limited`（cache_controller.py:1197-1215，cache 模式 `prefetch_tokens_occupied >= prefetch_capacity_limit`）② L3 部分命中截断（cache_controller.py:1235-1236 遇缺页 break）③ load_back avail/evict 门（1535-1542）。归因设计（p2-0-04）应映射这三机制而非 mem_quota。

### 2.2 b15 探针事件表（7 evt，pa_* 4 + pb_* 3）
| evt | 发射行 | 字段 |
|---|---|---|
| pa_lb_init | unified_radix_cache.py:2936-2938 | rid, host_hit_length |
| pb_load_submit | cache_controller.py:984-987 | producer_id, n_tokens, n_nodes（无 rid） |
| pb_load_done | unified_radix_cache.py:2893-2895 | n_tokens, n_pending |
| pb_layer_wait | cache_controller.py:129-132 | consumer, ready_layer0, ready_all |
| pa_evict | unified_radix_cache.py:652-655 | ms, requested_tokens, mamba_num |
| pa_writing_check | unified_radix_cache.py:2821-2823 | ms, pending |
| pa_batch | scheduler.py:3917-3923 | step_kind, batch_size, forward_iter, consumer_index |
公共: 每行带 `ts`（wall clock 1ms），追加写 /tmp/b15-probe.log。

### 2.3 restore/recompute 日志签名（8 个，≥2 满足）
- `HiCache prefetch %s req=%s completed=%d matched=%d loaded=%d occupied=%d`（unified_radix_cache.py:2104-2112，%s=success/dropped，info）— t38sb "HiCache prefetch success" 实际格式
- `HiCache prefetch fill committed req=%s filled=%d occupied=%d locked=%d`（pipeline.py:941-947，info）
- `HiCache prefetch dropped %d-token refill...`（unified_tree_core.py:1833-1840，info）
- `HiCache load_back failed for rid=%s: ... (l1=%d, l2=%d, l3=%d)`（decode_hicache_mixin.py:216-226，warning）
- `load_back: FAILED to load...`（hiradix_cache.py:1446-1453，warning，legacy）
- `Prefill batch ... #cached-token: ...`（metrics_reporter.py:610-618 → 发射 658，info；`--enable-cache-report` 已冻结）
- debug 默认不可见 2 个: `init_load_back success`（2967-2971）、`HiCache storage prefetch retry`（scheduler.py:2935-2939）
- **时间戳：带** — configure_logger（utils/common.py:2336-2343）`[%(asctime)s] %(message)s`、datefmt `%Y-%m-%d %H:%M:%S`（SGLANG_LOG_MS 加毫秒）；server_args.py:11151-11156 同构。→ **L3→H wait 派生可行**：prefetch success 行（asctime/req）↔ pa_lb_init（ts 1ms/rid）。
- 补充: prefill 模式 load_back 失败**静默**（schedule_policy.py:1321-1330 无日志），只有探针签名。

### 2.4 锁语义（locked tokens 来源）
- 派生: locked = max_total − kv_used − kv_evictable；形态 `available_and_evictable_str`（unified_radix_cache.py:3182-3207 `Available full tokens: X (full_available_size=A + full_evictable_size_=E)`），OOM 现场引用 allocation.py:163
- 三锁机制（当前树行号）: host_lock_ref（L3 写 _write_backup_storage_node 1694/1722、load-back 1479、prefetch 锚 1865）、write_through_pending_id（_track_write_through_node 1414）、lock_ref device（1482/1460/1553/1567）；方法定义 unified 805/815/853/858、tree_core 570/589/634/644。与 backpressure-analysis.md §1.2 语义一致（该文行号略旧，已更新）

### 2.5 校验
- `grep -rn '"evt": "pa_' python/sglang/srt/ --include="*.py"` = **4 命中**（scheduler.py:3917、unified_radix_cache.py:652/2821/2936）= 表中 pa_* 4 项；全表 7 项与 `grep -rn -F '_b15_log('` 7 发射点一致。

## 3. 探针字段充分性结论
**聚合级可区分，per-req 有 1 处缺口**：
- 部分恢复: `HiCache prefetch success req=X completed=Y(<请求)` → `pa_lb_init host_hit_length≈Y` → `pb_load_submit/done n_tokens≈Y`；重算余量 = driver 侧 prefill_input_delta
- 配额拒绝(H→D): `pa_lb_init` 后无对应 `pb_load_submit`；decode 模式有 "HiCache load_back failed" warning（l1/l2/l3 分层）；prefill 模式静默
- 配额拒绝(L3→H): 无 prefetch success 行、无 pa_lb_init → 靠 metrics 计数 hicache_prefetch_aux_alloc_failed_tokens_total + prefetch_tokens_occupied 时序
- **缺口（P2-1 依赖候选）**: pb_load_submit/pb_load_done 无 rid/node_id（并发 DMA per-req 关联靠 ts+n_tokens 推断）；pa_lb_init 未含请求恢复量/配额值；prefill 模式失败无日志

## 4. 证据（命令与结果）
- `grep -rn '"evt": "pa_' ...` → 4 hits（上）
- `grep -rn -F 'mem_quota' python/sglang/srt/ --include="*.py"` → 13 行（全在 mem_cache/*，无外部调用者传值）
- `grep -rn -F 'init_load_back'` / `'load_back('` → 调用点全集（§2.1）
- Read 局部窗口: unified_radix_cache.py（123-159/1450-1571/2040-2154/2800-2977/3160-3234）、hiradix_cache.py 1390-1479、base_prefix_cache.py 150-189、schedule_policy.py 1300-1335、decode_hicache_mixin.py 140-330、scheduler.py 2905-2960/3425-3463/3560-3600/3900-3935、metrics_reporter.py 595-679、cache_controller.py 48-139/965-990/1193-1237、pipeline.py 430-469/900-960、unified_tree_core.py 1805-1849、pool_stats_observer.py 60-118、common.py 2325-2354、server_args.py 11140-11158、backpressure-analysis.md 20-69、fetched-hicache-upstream.md 55-104、launch-l3-3090.sh 100-142

## 5. Followups
- p2-0-04 归因设计输入: 三机制映射（§2.1）、事件签名规则（§3）
- p2-0-06 采集脚本解析目标: 8 个签名 grep 模式 + 7 evt 探针（log-field-inventory.md §2/§3）
- 01 侧交叉: prefetch 预算计数、prefetch_tokens_occupied 时序与 §2.1 三机制对齐

## 6. Open issues
- 无阻塞项。注意: `--log-level` 未冻结（默认 info），debug 级 restore 日志（2967/2935）不可见，若要采集需在实验启动参数中显式 `--log-level debug` 或接受仅 info 签名（建议 03/07 决策并记录）。
