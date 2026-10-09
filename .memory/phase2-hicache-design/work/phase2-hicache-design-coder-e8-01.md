# phase2-hicache-design-coder-e8-01 — P2-1 M2 wake 广播链修复（frontier_wait 29/29 → wake 0）

## status
**done** — M2 wake 链双断点已修复（写触发缺失 + T11 提前唤醒），torch-free 全绿
（35/36/12，含新增 5 测 + RED→GREEN 突变验证 ×2）；部署 3090 双侧 md5 4 文件一致；
远端真实 torch（2.13.0+cu130）35/36/12 全绿；引擎未启动（GPU 15 MiB、0 进程）。
未 commit 未 push。

## 根因定位（唤醒链双断点，证据 /root/evidence-p2b0-1c/）

**断点 1 — 无人触发 anchor 的 L3 写（K=1 阶段一 60s 超时的根因）**
- `unified_tree_core.py:866-867`：`_inc_hit_count_and_check` 在 `is_write_back` 下
  **直接 return False**——write_back 模式中 hit-count 写穿备份永不触发；节点只由
  device 驱逐触发 D->H + L3 写。
- `unified_radix_cache.py:2310-2325`（M2 注册）：纯表插入，不请求写。gate skip 时
  anchor 连 D->H 都未提交；K=1 顺序负载无驱逐 → anchor 链永远到不了
  `storage_persisted` → `_wake_frontier_waiters`（2346-2367）无 ACK 可响应 →
  T13 60s 超时。设计前提（§3.1"链写已提交/在途"）在 write_back 运行时为假。
- 证据：`state-machine.txt` 阶段一 frontier_wait node=27/30/32/40 均整 60s 后
  `restore_recompute cause=timeout`；其间零 prefetch_io_done（p2a-lines.txt）。

**断点 2 — T11 容量谓词提前唤醒（阶段二 retry→miss 成对 + frontier_wake=0 的根因）**
- `scheduler.py:3147-3155`（旧）：FRONTIER 谓词查 `is_backuped(anchor)`；但
  `backuped` 在 **D->H 提交时**即置位（unified_radix_cache.py:1417 commit_backup），
  L3 写要到 D->H ACK 后才提交（`_finish_write_through_ack` 1491-1503 →
  `_pending_storage_writes` → `_flush_pending_storage_writes`）——谓词比 L3 就绪
  早数十秒（3090 实测 L3 写 3-16s）。
- 提前唤醒 → scheduler.py:3054-3055 `discard_frontier_waiter` 丢弃 waiter →
  `_prefetch_kvcache` 重发 → L3 空 → revoke → T9 真 miss → RECOMPUTE；等 L3 ACK
  真正到达时 waiter 已不在注册表 → `frontier_wake` 永远 0。
- 证据：`state-machine.txt` 阶段二 `restore_retry cause=capacity` → `restore_recompute
  cause=miss` 每 ~0.5-5s 成对（如 67cdbf39 @17:06:45-17:07:10 五对），直至某次重发
  恰逢 L3 写完成才 `restore_ready`（17:07:13）。

**排除项**：唤醒钩 `_drain_backup`（unified_radix_cache.py:2755-2783，wake 挂 2774）
本身可达且正确（阶段二 L3 写完成过 29 次 restore_ready）；注册节点 = anchor 正确；
T12 消费（scheduler.py:3013-3028 pop→guard→FRONTIER_READY→RETRY_PREFETCH）wiring 正确。

## 修复清单（2 源文件 + 2 测试文件，语义）

| 文件:行 | 改动 | 语义 |
|---|---|---|
| `mem_cache/unified_radix_cache.py:2310-2355` | `register_frontier_waiter` 末尾加写触发：`node_exists` 守卫后调用 `write_backup_storage(node_id)` | **等待即推进 frontier**：write_back 只在驱逐时写 L3，wait 注册必须自己请求 anchor 链的持久化（gap fill 按 is_backuped/is_storage_written 去重；anchor 已删则跳过，waiter 走 re-match 自愈）——设计前提"写已在途"由注册本身变为真 |
| `mem_cache/unified_radix_cache.py:1781-1800` | 新增 `is_storage_persisted` wrapper + `frontier_anchor_ready(node_id)`（persisted / deleted→True / root→True；**刻意不用 is_backuped**） | T11 谓词与 ACK 唤醒同条件：L3 就绪才唤醒，消除提前唤醒 |
| `managers/scheduler.py:3147-3155` | `_restore_wait_capacity_fits` FRONTIER 分支改调 `tree_cache.frontier_anchor_ready(anchor)` | 同上；删 anchor / root 自愈分支保留（并入 cache 方法，torch-free 可测） |
| `3090-dev/test_drain_reentry.py`（+3 测） | `test_register_trigger_persists_anchor_chain`（注册→gap fill D->H+L3→ACK 推进→wake→ready 全链）/ `test_register_trigger_dedupes_already_submitted_chain`（重注册不重复写）/ `test_register_trigger_skips_deleted_anchor`（stale anchor 不崩） | 钉住断点 1 的修复 |
| `3090-dev/test_storage_regression.py`（+2 测 + fake 升级） | `test_frontier_anchor_ready_requires_persisted`（**回归反例**：backuped 但未 persisted → False，旧谓词 True）/ `test_frontier_anchor_ready_self_heals_deleted_or_root`；`_FakeTreeCore` 加 `collect_storage_gap=lambda: []`（注册表 harness 无链模型，触发变 no-op） | 钉住断点 2 的修复 |

## evidence

1. 本机 `python3 -m py_compile`（4 文件）：`PY_COMPILE_OK`。
2. 本机 torch-free：`test_hicache_restore.py` **35/35**、`test_storage_regression.py`
   **36/36**（既有 34 + 新 2）、`test_drain_reentry.py` **12/12**（既有 9 + 新 3）。
3. **RED→GREEN ×2（突变验证）**：① `frontier_anchor_ready` 改回 is_backuped →
   `test_frontier_anchor_ready_requires_persisted` 失败（`True is not false`）；
   ② 删掉注册触发 → `test_register_trigger_persists_anchor_chain` 失败；还原后全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 4 文件，
   误放根目录已 mv 纠正），**双侧 md5 逐文件一致**：
   - unified_radix_cache.py `5f07791c343e6e11e67ea78542e6df86`
   - scheduler.py `2bb64a91641c1133910dd4c3e14f04cf`
   - test_drain_reentry.py `39dc2687248fbba330f51dac4e93e9be`
   - test_storage_regression.py `60526fc07270fb50cb692127649ed52d`
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）：
   `REMOTE_PY_COMPILE_OK`；torch `2.13.0+cu130` 真实回归：35/35 + 36/36 + 12/12 全绿。
6. 3090 引擎未启动：`nvidia-smi` 15 MiB、0 引擎进程。
7. git diff 审查：本 epoch 改动 = 上述 4 文件 5 处编辑，叠加于既有 M1a/M1b/M2
   未提交遗产之上；未触碰 cache_controller/hiradix_cache/hybrid_cache_controller/
   schedule_policy。

## summary

M2 wake=0 是双断点而非单点：write_back 模式下无人推进 L3 frontier（等待永远等不来），
且 T11 容量谓词用 is_backuped（D->H 提交即真）比 L3 就绪早数十秒——wait 被提前唤醒
丢弃、重发打进空 L3 变 miss→recompute，等真 ACK 到达时 waiter 已注销。修复 =
① 注册即触发 anchor 链 gap-fill 写（等待本身推进 frontier，设计前提"写在途"变真）；
② T11 谓词与 ACK 同条件（storage_persisted / deleted / root，刻意排除 is_backuped）。
两处都是最小语义改动，全部逻辑落在 cache 层可 torch-free 测试。

## followups

- tester 复测（42ms-gap 场景）：应见 **frontier_wait→frontier_wake 配对**；K=1 应回到
  ~20-55s（不再有 4×60s）；K=8 p95 应回 ~53s；restore_recompute cause=timeout 应趋 0；
  restore_recompute cause=miss 仍会存在（L3 无链 / suffix 未写是 T9 真 miss 语义）。
- 集成验证点：engine log 中 `evt=frontier_wake` 出现（此前 0）；`restore_retry
  cause=capacity` 中 FRONTIER 型应在 persisted 后才有；T11/T12 同 pass 双触发不双发
  （T12 先消费 → 态转 RESTORING → T11 跳过）。
- 已知边界（不改）：注册触发的 `write_backup_storage` 内联等 D->H ack 为毫秒级阻塞
  （scheduler 线程，链小、有界）；REVALIDATE 60s 超时问题（e7 open_issues）仍在范围外。

## open_issues

- 写触发在 K=1 顺序负载下每 turn 写前一 turn 链（L3 积累、frontier 滞后一拍）；
  若实测 L3 写开销显著，可评估"锚点已在驱逐在途（storage_written）时不重复触发"
  的窄化——当前 gap fill 已去重，先观察。
- out-of-order L3 ACK（子先于父）会滞留子节点 waiter（lazy promotion 无链式唤醒）；
  设计前提为链写 FIFO（file backend 串行），本修复未动。
