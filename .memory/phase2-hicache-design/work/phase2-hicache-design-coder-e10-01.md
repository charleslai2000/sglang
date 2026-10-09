# phase2-hicache-design-coder-e10-01 — P2-1 B 任务：t5 missed-wake 归因 + denied_rate_limit 语义判定

## status
done（四步链断点定位完成 + 依赖映射结论 + rate-limit 语义结论 + 最小修复 + 测试 + 双侧 md5 + 远端真实 torch 回归）

## 1. 四步链断点定位（专家四步链：frontier dependency registered → anchor frontier advance → wake candidate selection → retry eligibility）

### 归因结论：t5 的 60s 不是 frontier missed-wake，是 WAIT[REVALIDATE] 死等待

**K=1 t5 = rid `b4d560a0`**（join.log turn 5：prompt 20911、device_hit=20864、wall 60.969s）：
- 18:05:03 `_prefetch_kvcache` 首次重过 gate（anchor 已 backuped）→ 存储查询 suffix=46（20911−20864−1）< prefetch_threshold 256 → `declined_too_short`（unified_radix_cache.py:1900-1913）
- scheduler.py:2950-2952 原逻辑：`_restore_potential_for(req)` 为 True（rid 刚被 1911 行 `_storage_prefetch_missed_rids.add` 注册 = 自证意图；且 anchor is_backuped）→ 喂 DENIED_SHORT → `next_restore` → **WAIT_CAPACITY/REVALIDATE**（engine log 18:05:03 `state=WAIT_CAPACITY reason=REVALIDATE`）
- **REVALIDATE 无任何 wake 路径**：① `capacity_wake_applies(REVALIDATE)=False`（hicache_restore.py:209-225，scheduler.py:3055-3060 跳过）② paced retry 块 `if interval > 0`（scheduler.py:2990）——M2 默认 `hicache_storage_prefetch_retry_poll_interval=0`（server_args.py:2834）→ 整块不执行，REVALIDATE 的唯一重发源不存在 ③ 无 prefetch 在途（无 FINALIZED/REVOKED 事件）→ **唯一出口 = T13 60s 超时**（18:06:03 `restore_recompute cause=timeout`）
- 断点：**scheduler.py:2950-2952（DENIED_SHORT 无条件进入 WAIT，未校验其唯一出口 paced retry 是否武装）**；e12 修复只覆盖重发腿（T11/T12 wake 后 too_short 终态），首拒腿不受益

**frontier 机制本身无 bug**：全 log 6 次 frontier_wait → 5 次 wake 配对（K=1 t8 `a086b28f` node=24 1.06s；K=8 `8a3a16f2` node=77 10s、`2a66916c` node=96 8s、`21d47768` node=115 7s、`6e244cf9` node=121 1s），未配对的第 6 个 `4fa93c2e` node=125（18:10:34）在引擎 18:10:48 SIGTERM 前 14s 注册——run 截断伪影，非映射失败。e13 followup 的"frontier_anchor_ready 谓词未满足"假设不成立。

## 2. dependency 映射结论：同 dependency（wait node = ACK node = anchor 自身）

- 注册：scheduler.py:2966 `register_frontier_waiter(req.rid, last_host_node)` —— key = anchor（最深 host 匹配节点）
- 推进：`_drain_backup`（unified_radix_cache.py:2785-2813）弹 `ongoing_backup[operation.id]` → `(node_id, ...)` → `advance_storage_persisted(node_id)`（2799）→ `_wake_frontier_waiters(node_id)`（2804）—— **同一 node_id**
- 写源：注册时 `write_backup_storage(node_id)`（2355）为同一 anchor 提交 L3 写（gap 填充分 dedupe 跳过已写祖先）→ **ACK 即 anchor 自己的写的 ack**（自依赖，非 ancestor）
- wake 门：`is_storage_persisted(node_id)`（tree_core:1946-1949，node.storage_persisted 仅在自身 ACK 落地且父链连续时置位——unified_tree_core.py:1928-1940）→ 祖先 ACK 不可能满足
- 机制说明：`advance_storage_persisted(node)` 只处理 node 自身的 ACK；waiter 的谓词兜底 `frontier_anchor_ready`（1795-1799）同样以 `is_storage_persisted(anchor)` 为门（非 is_backuped——D→H 提交早于 L3 写，premature wake 是 e8 修掉的旧 bug）
- 证据：5/5 非截断 wait 全部 wake 且各随 `restore_retry cause=frontier`；`a086b28f` wake 后重发腿 declined_too_short → 立即终态 recompute（e12 生效，2.0s）

## 3. denied_rate_limit 语义结论：**被唤醒 restore，非永久放弃**（RATE_LIMITED 已是 RETRYABLE）

- 代码：`declined_rate_limited` → scheduler 喂 DENIED_RATE → `next_restore` T2 无条件 → WAIT_CAPACITY/PREFETCH_BUDGET（状态机 hicache_restore.py:99-100 已是 RETRYABLE）
- T11 唤醒存在且生效：`capacity_wake_applies(PREFETCH_BUDGET)=True`；`_restore_wait_capacity_fits` 检查 `prefetch_rate_limited()`（cache_controller.py:1241-1259，cache 模式 = `prefetch_tokens_occupied >= 0.5*host_pool`，瞬态——finalize 时回减，evidence 中 "HiCache prefetch success ... occupied=N" 序列证实）
- 现场 16 个 denied_rate_limit rid：**11 个被 `restore_retry cause=capacity` 唤醒并 restore**（1f2421de 14s、4d88ffd5 56s、acfdaaa8/aa0d8b6b 超时后经 DEVICE_QUOTA 重进再唤醒……）；5 个撞 T13 60s（90d6607a、4be439fd、a6eccf98、b5355ceb×2、839d45e0——除 839d45e0 外均在截断尾窗）
- 12 个 timeout 构成：REVALIDATE 2（b4d560a0=K1 t5、0b2a44f9）+ PREFETCH_BUDGET 10（预算饥饿：limit=41820≈2 个 20910 跨度，同 pass 内先到者重发即回填预算，队尾在 K=8 突发下 60s 轮不到——设计的有界退化 T13，非 bug）
- **唯一需修**：`_log_restore_disposition` 对 rate-limit 拒绝标 "RECOMPUTE"（unified_radix_cache.py:1923）与状态机 WAIT 矛盾（tester 的 RECOMPUTE 44 计数被污染）；aux_alloc_failed（1992）同款

## 4. 修复清单（最小改动，不缩短 timeout；未 commit 未 push）

| 文件 | 位置 | 改动 |
|---|---|---|
| python/sglang/srt/managers/scheduler.py | 2951-2962（+227 import） | DENIED_SHORT 加门 `too_short_wait_armed(get_memory().hicache_storage_prefetch_retry_poll_interval)`：interval=0（M2 默认）时首拒 = 终态，立即 recompute，不进死等待 |
| python/sglang/srt/managers/scheduler_components/hicache_restore.py | 209-222 新增 | `too_short_wait_armed(poll_interval) -> bool` 纯函数（REVALIDATE 唯一出口 = paced retry，未武装不得进入） |
| python/sglang/srt/mem_cache/unified_radix_cache.py | 1923-1928、1992-1998 | denied_rate_limit / aux_alloc_failed 的 disposition 标签 RECOMPUTE → **WAIT**（如实反映 T2/T3 状态机；too_short 在默认配置下经修复后确为终态，标签不变） |
| 3090-dev/test_hicache_restore.py | +3 测 | 见下 |
| 3090-dev/test_storage_regression.py | +1 测 | 见下 |
| /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-1-design.md | §2.2 T4 行 + §2.5-2 | REVALIDATE 行前提 = too_short_wait_armed(interval)；新增"interval=0 首拒 = 终态"分离判据行 |

## 5. 新增测试（torch-free；RED→GREEN 已做：helper 缺失 AttributeError RED → 实现后 GREEN）

- `test_t4_too_short_wait_requires_paced_retry`：too_short_wait_armed(0)=False / (1)=True（钉住 t5 根因门）
- `test_rate_limited_wake_cycle_never_recomputes`：DENIED_RATE→WAIT[PREFETCH_BUDGET]→CAPACITY_FITS→RESTORING+RETRY_PREFETCH（钉住"被唤醒非放弃"）
- `test_denied_rate_never_degrades_to_recompute`：任意状态喂 DENIED_RATE 永不出 ADMIT_RECOMPUTE
- `test_wake_requires_same_node_ack_not_ancestor`（test_storage_regression.py）：r1 等 anchor 42；祖先 41 ACK+persisted 不唤醒（反例）→ 42 自身 ACK 唤醒并 pop 一次（正例）——专家假说的回归钉

## 6. 证据（验证命令与真实输出）

- 本机 torch-free：`test_hicache_restore.py` **43/43 OK**（40+3）、`test_storage_regression.py` **37/37 OK**（36+1）、`test_drain_reentry.py` **12/12 OK**（既有不回归 ✓）
- 本机 `python3 -m py_compile` 3 源文件：PY_COMPILE_OK
- 部署 `/root/sglang-b1-continuity/`（3090，ssh 24052），**双侧 md5 六文件全一致**：hicache_restore.py `0d24bb9f…`、scheduler.py `30e9e0c7…`、unified_radix_cache.py `5f9d3f76…`、test_hicache_restore.py `2d901b72…`、test_storage_regression.py `6eaed9d5…`、test_drain_reentry.py `39dc2687…`
- 远端真实 torch 2.13.0+cu130：REMOTE_PY_COMPILE_OK + 43/37/12 全绿
- 引擎未启动（本机 ps EXIT=1 无命中）

## followups
1. **⚠️ 3090 上有并发引擎在跑**（非本 epoch 启动）：`engine-p2b0-1f2.log`，launch 21:46:57（PID 124024，port 8024），21:47:10-11 完成模块 import、21:48:45 ready——**早于本 epoch 21:48 的部署，跑的是旧代码**（21:49:26 日志 `disposition=RECOMPUTE … denied_rate_limit` 为旧标签佐证）；未触碰该进程。下一轮 run 将自然加载新代码
2. PREFETCH_BUDGET 队尾饥饿（10/12 timeout）：预算 limit=41820 与同 pass 内联重发回填 + arrival 先于 reconcile 消费预算的排序效应——T13 有界退化按设计工作；是否要给 waiters 优于新 arrival 的优先级，留 p2-0-10 归因输入
3. K=8 74 failed 截断污染（e13 followup 2）仍待完整窗口 run；4fa93c2e 的 frontier wait 未配对 = 截断伪影，无需修
4. 设计文档 §3.1 已含"anchor 自身 ACK = 可靠信号"；本 epoch 无 frontier 代码改动

## open_issues
- 引擎 1f2（旧代码）与本 epoch 部署（新代码）同时存在于 3090 磁盘/进程两侧——若 tester 以 1f2 结果对照新行为会不一致，需 orchestrator 排程下轮 run 用新代码
- `_storage_prefetch_missed_rids` 在 interval=0 时仍被 too_short 拒绝注册（1911）——无害（准入/abort 清理），且保证 interval>0 配置兼容；未改
