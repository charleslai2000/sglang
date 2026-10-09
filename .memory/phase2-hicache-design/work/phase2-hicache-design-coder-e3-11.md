# P2-0a 插桩缺口修复 — prefetch 生命周期观测（coder e3-11）

## status

**done** — 读码定位 prefetch 全生命周期（issue → storage query → drain/alloc → IO → sync → ack → finalize/revoke），
补 4 处 log-only 插桩（I7 IO 线程 io_finished / I8 finalize 入口 / I9 revoke 漏斗 / I10 abort 清理）；
本机 py_compile exit 0、git diff 审查通过（2 文件：3 行日志 + 1 行返回值捕获，0 逻辑改动）；
已部署 3090 双侧 md5 一致、远端 py_compile exit 0；未启动引擎（GPU 15 MiB 空闲、0 进程）。

## artifacts

| 文件（本机 + 3090 部署同路径） | 改动 | 行数 |
|---|---|---|
| `python/sglang/srt/managers/cache_controller.py` | I7（IO 线程 io 完成点） | +2（1 行返回值捕获 + 1 行 logger） |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | I8 + I9 + I10 | +3（均单行 logger） |

3090 部署路径：`/root/sglang-b1-continuity/python/sglang/srt/managers/cache_controller.py`、
`/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_radix_cache.py`。
未 commit 未 push（与 I1-I6 同为临测件）。

## 插桩清单落地表（本次新增）

| ID | 位置（本机行号） | 事件 | 内容 | 行数 |
|---|---|---|---|---|
| I7 | cache_controller.py:1185-1186（`_page_transfer` 后、completed_req ack 入队前，IO 线程） | `evt=prefetch_io_finished rid=%s n_tokens=%d` | rid=operation.request_id；n_tokens=`n_pages * page_size`（_page_transfer 实际完成页数 × 页大小）。**真正 IO 完成时刻**（scheduler 侧 I3 之前 2 跳：sync/reduce + 队列） | 1 logger + 1 捕获赋值 |
| I8 | unified_radix_cache.py:2021（`_handle_prefetch_result` 入口，docstring 后、t38c 前） | `evt=prefetch_finalize rid=%s completed_tokens=%d mode=%s` | rid + operation.completed_tokens + host_memory_mode。**finalize 发生/尝试的确定标记**（含 buffer_only 提前返回 2057-2062 与 hybrid 丢弃 2044-2055 两分支——success 行不发射的路径也可见） | 1 |
| I9 | unified_radix_cache.py:2347（`revoke_pending_prefetch` 弹出 info 后——全部 6 个调用点的唯一漏斗） | `evt=prefetch_revoke rid=%s terminated=%s storage_hit=%d requested=%d` | rid + operation.is_terminated() + storage_hit_count + stats_requested_tokens。三字段即操作原因：terminated=True=终止撤销（abort/策略）；terminated=False 且 hit=0=full-miss 撤销；terminated=False 且 hit≥threshold=alloc 失败撤销 | 1 |
| I10 | unified_radix_cache.py:2258（`release_aborted_request` 解包后——post-alloc 分支绕过 I9 漏斗，必须单独打） | `evt=prefetch_abort_cleanup rid=%s pre_alloc=%s` | rid + (operation.host_indices is None)。pre_alloc=True 时 I9 漏斗随后也会发射（双行配对）；pre_alloc=False 走 2267 直接 del，仅此行 | 1 |

格式统一：`logger.info("[P2A] ts_ms=%d evt=...", int(time.time() * 1000), ...)`，与 I1-I6 一致。
I7 的 `self._page_transfer(operation)` → `n_pages = self._page_transfer(operation)` 为唯一非日志
改动（捕获原本丢弃的返回值，零行为变化）。

## 插桩后 prefetch 生命周期路径图（事件点 → 观测行）

```
scheduler 线程                                       controller 线程
─────────────────                                    ─────────────────────────
请求到达 → _prefetch_kvcache → prefetch_from_storage
  │  门: enable_storage / len<threshold(256) / aux alloc fail
  ├─ cache_controller.prefetch() → prefetch_queue.put
  ├─ [P2A] prefetch_issued                (I6, urc:1933)      │ prefetch_thread_func(1242)
  ├─ ongoing_prefetch[rid] 登记            (urc:1947)          ├─ _storage_hit_query → batch_exists
  │                                                           │   → TP MIN all_reduce → storage_hit_count
  │                                                           └─ prefetch_hit_queue.put (1271)
  ├─ 每 pass check_hicache_events (sch:3447) → 排空            │
  │   └─ _drain_and_alloc_storage_hit (urc:2457)
  │       ├─ rid 不在 ongoing_prefetch → skip（已清理）
  │       ├─ is_terminated → revoke              → [P2A] prefetch_revoke (I9, terminated=True)
  │       ├─ hit < 256 → account(revoked) + revoke → [P2A] prefetch_revoke (I9, hit=0)  ◄── K=8 全 8 条死在此
  │       └─ _try_alloc_storage_hit(2398):
  │           ├─ terminated → revoke             → [P2A] prefetch_revoke (I9)
  │           ├─ alloc 失败(cache) → revoke      → [P2A] prefetch_revoke (I9)
  │           ├─ rate_limited(buffer) → park（pending_hit_allocs，不 revoke）
  │           └─ 成功: host_indices 赋值 + prefetch_buffer.put (2446)  │
  │                                                                │ prefetch_io_aux_func(1176):
  │                                                                ├─ _page_transfer(1080): 逐批读 L3
  │                                                                │   → 每批 prefetch_sync_queue.put(ack completed_tokens)
  │                                                                └─ [P2A] prefetch_io_finished (I7, cc:1186)  ← 真·IO 完成
  │                                                                    → sync_queue.put(ack completed_req=True) (1187-1193)
  │                                                                │ prefetch_sync_thread_func(1345):
  │                                                                └─ reduce(TP/PP MIN) → ack_prefetch_queue (1353)
  ├─ _drain_ack_prefetch (urc:2506)
  │   ├─ completed_tokens ack → operation.completed_tokens (2509-2512)
  │   ├─ [P2A] prefetch_io_done (I3, urc:2523)  ← scheduler 侧收到 completed_req（=I7+2 跳延迟）
  │   └─ rid in ongoing_prefetch → _handle_prefetch_result
  │       └─ [P2A] prefetch_finalize (I8, urc:2021)  ← finalize 确定标记
  │           ├─ hybrid 检查失败 → discard（del ongoing_prefetch 2195, warning 日志）
  │           ├─ buffer_only → stage（2057-2062 提前返回，success 行不发射——I8 覆盖此缺口）
  │           └─ cache → insert_host + commit → del ongoing_prefetch (2102)
  │               → "HiCache prefetch success/dropped" 行 (2104-2113)
  └─ 旁路终态（无 finalize 无 success）:
      ├─ check_prefetch_progress (1984): wait_complete 下 can_terminate=False → 惰性
      │    （best_effort/timeout 下 host_indices 已设 → 直接 _handle_prefetch_result = 第二 finalize 入口）
      ├─ release_aborted_request → [P2A] prefetch_abort_cleanup (I10)
      └─ revoke_pending_prefetch 全部 6 调用点 → [P2A] prefetch_revoke (I9)
```

ongoing_prefetch 全部移除点核对（grep 2102/2195/2267/2336）：2102=finalize(I8 覆盖)、
2195=hybrid discard（I8 覆盖 + 既有 warning）、2267=abort post-alloc（I10 覆盖）、
2336=revoke 漏斗（I9 覆盖）——**任何 rid 从 ongoing_prefetch 消失都有且只有一条观测行**。

## 8 条 issued / 0 finalize 的解释（读码结论）

**最可能路径：全部在 drain 阶段因 L3 全 miss 被撤销（revoked_full_miss），IO 从未启动。**

K=8 run 事实：32 请求全完成（L0/L1 grow/downgrade）、wait_complete 策略（launch-l3-3090.sh:113）、
L3 全新空库（/data/l3/p2b0-0a）、retry_poll_interval=0（retry 关闭）、t38c 未启用。

代码时序（全部行级核实）：
1. 8 条 prefetch 于 run 早期发出（host 锚点尚存），`ongoing_prefetch[rid]` 登记（urc:1947），
   请求被 admission 门控（scheduler.py:3585-3588 `check_prefetch_progress` → wait_complete →
   `can_terminate_prefetch` 恒 False → 每 pass skip；样本 7274d0e3 admission 14 次一致）。
2. controller `prefetch_thread_func`（cc:1242）执行 `_storage_hit_query`（cc:1217，batch_exists）：
   空 L3 → 首批 0 命中 → `storage_hit_count=0` → `prefetch_hit_queue.put`（cc:1271）。
3. 下一 pass `check_hicache_events`（sch:3447，每 step 在 admission 扫描前）→
   `_drain_and_alloc_storage_hit`（urc:2457）→ `0 < prefetch_threshold(256)`（urc:2477）→
   `_account_prefetch_outcome(revoked=True)` + `revoke_pending_prefetch`（urc:2491）→
   从 ongoing_prefetch 移除。
4. 请求解除门控 → `pop_prefetch_loaded_tokens`=0 → 全量 recompute（样本 7274d0e3：
   issued len=20910、input_delta=20911、无 pa_lb_init——完全吻合）。
5. 从未进入 `prefetch_buffer`（cc:2446 只在 alloc 成功后 put）→ IO 线程从未取到 →
   无 completed_tokens ack、无 completed_req ack → **io_done=0、success=0**。
6. 撤销本身无 [P2A] 日志 + t38c 关闭 → 观测上"8 issued 后凭空消失"。

排除项：
- **(a) abort/revoke？** — abort 可排除：32 请求全部正常完成（join.log grow/downgrade），
  无 abort；`release_aborted_request`（sch:3019/3050/3187）未被触发。revoke 是**唯一**发生的事
  （步骤 3），只是此前不可见。
- **(c) run 截断？** — 可排除：prefetch 全在 run 前 ~2 分钟发出，请求 wall 6.2-49s 内完成，
  其 prefetch 在窗口内即已解决（被撤销）；3 分钟 SIGTERM 截断的是尾段请求，与 8 条 prefetch 无关。
- **(b) 插桩位置漏捕获？** — I3（ack.completed_req 分支，urc:2523）是 scheduler 侧收到
  completed_req 的唯一入口，而 completed_req=True 只由 IO 线程在 `_page_transfer` 返回后发出
  （cc:1185-1193）——**若 IO 曾运行，I3 必然发射**。io_done=0 ⇒ IO 从未运行 ⇒ 撤销发生在
  prefetch_buffer 之前。I3 位置语义正确，无需移动。

**I3 语义与"io 完成"的差异（任务第 4 问）**：ack.completed_req 分支 = io 完成通知在 scheduler
线程的落点，比 IO 线程真完成点晚 2 跳（sync 线程 reduce + ack_prefetch_queue + 下一 pass 排空）。
wait_complete 部署下它是**唯一** finalize 触发入口（check_prefetch_progress:2011 的第二入口因
can_terminate_prefetch=False 而惰性）；best_effort/timeout 部署下 2011 会以
`completed_tokens` 可能仍为 0 的状态提前 finalize（潜在 premature-finalize，本次不适用，登记
open_issues）。修正动作：不移动 I3，补 I7（IO 线程真完成点）→ 配对 I7/I3 即得 sync+reduce 延迟。

**本轮插桩后 K=8 复跑的预期签名**：8 × `prefetch_issued` → 8 × `prefetch_revoke`
（terminated=False, storage_hit=0）→ 0 × `prefetch_io_finished`、0 × `prefetch_finalize`——
可一锤定音。

## evidence

1. 本机 `python3 -m py_compile`（cache_controller.py / unified_radix_cache.py）：`exit=0`。
2. git diff 审查：本次任务在 e3-10 未提交的 I1-I6 之上净增 2 文件 5 行（4 行 `[P2A]` logger
   + 1 行返回值捕获 `n_pages = self._page_transfer(operation)`）；零删除、零逻辑改动；
   所有引用变量（operation.request_id / n_pages / self.page_size / operation.completed_tokens /
   self.host_memory_mode / operation.host_indices / operation.is_terminated() /
   operation.storage_hit_count / operation.stats_requested_tokens / rid）均经行级 Read 确认
   作用域内（storage_hit_count=PrefetchOperation.__init__ cc:311、stats_requested_tokens=
   StorageOperation.__init__ cc:280、host_memory_mode=urc:2334 同属性、page_size=cc:1034/1099、
   import time=cc:19、logger=cc:1047 同模块）。
3. 部署前基线：远端 cache_controller.py md5 `b97978cebd9b514c69e6fa6553197d1d` == 本机
   HEAD `b97978cebd9b514c69e6fa6553197d1d`（上游原状，0 处 P2A）；远端 unified_radix_cache.py
   md5 `7632cb7d48706ad657b866a0d0bcbee1` == e3-10 部署记录（I3+I6，2 处 P2A）。
4. 部署后双侧 md5 一致：
   - unified_radix_cache.py `2c5d948bab06550081ecad89a181cd2b`（双侧一致）
   - cache_controller.py `6923aa1d24f3db397321e9a0c8fe3edb`（双侧一致）
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.12）两文件
   `exit=0`；远端 `grep -c '[P2A]'` = unified_radix_cache 5 / cache_controller 1，与本机一致。
6. 3090 引擎进程：`ps -eo pid,args | grep -iE 'launch_server|engine.*server'` = 0；
   nvidia-smi 显存 15 MiB/24576 MiB（空闲）；**未启动引擎**（实验启动归 tester）。
7. ongoing_prefetch 移除点全量核对：`grep -n 'del self.ongoing_prefetch\|ongoing_prefetch.pop'`
   命中 2102/2195/2267/2336，全部被 I8/I10/I9 覆盖，无盲区。
8. 56-regex-safety：全程行级 `grep -F`/`grep -n -E`，无跨距正则。

## summary

读码完成 prefetch 全生命周期七段链路（issue → storage query → drain/alloc → IO → sync →
ack → finalize/revoke），确认 K=8"8 issued 0 finalize"的根因路径：**空 L3 全 miss → drain
阶段 0<256 阈值撤销（revoked_full_miss）→ 从未进入 IO 线程 → io_done/success 永不发射**——
I3（ack.completed_req）位置语义正确（completed_req 只由 IO 线程产生，IO 未跑则 I3 必静默），
无需移动；差异仅在 I3 比 IO 线程真完成点晚 sync/reduce 2 跳，已补 I7 闭合。新增 4 处插桩
使 ongoing_prefetch 的每个终态（finalize/discard/revoke/abort）都有唯一观测行，且 revoke
行携带操作原因三字段（terminated/hit/requested）。全部 log-only，未 commit 未 push。

## followups

- tester 复跑 K=8（同冻结参数 + 空 L3 或预热 L3 各一次）：预期空库签名 = 8×issued →
  8×revoke(terminated=False, storage_hit=0) → 0×io_finished/0×finalize；预热库可顺带验证
  I7→I3→I8→success 完整链与 sync/reduce 延迟量级。
- 解析侧配对键 = rid，时间键 = ts_ms；revoke 行与 issued 行配对即得"issue→revoke 滞留时长"
  （K=8 下 ≈ 请求排队时长）。
- 若未来切 best_effort/timeout 策略，复读 open_issues 的 check_prefetch_progress:2011
  premature-finalize 风险（completed_tokens=0 时以空 key finalize）。
- 本分支插桩（I1-I10）为临测件：P2-0a 裁决后按结果保留或回退（git checkout 受限，回退需
  `git show HEAD:<path>` 恢复或按 git diff 逆操作——本任务未 commit，HEAD 即原始状态）。

## open_issues

- `n_pages = self._page_transfer(operation)` 是唯一非日志改动（捕获返回值），零行为变化；
  若裁决要求"纯新增行"，可改 `n_tokens` 为 `len(operation.hash_value) * self.page_size`
  （请求跨度，非实际完成数）并回退该捕获——建议保留捕获，实际完成数更有价值。
- check_prefetch_progress:2011（best_effort/timeout 下的第二 finalize 入口）存在
  premature-finalize 隐患：op 已进 prefetch_buffer 但 ack 未回时 completed_tokens=0，
  finalize 将以空 prefix 入树。wait_complete 部署不受影响；如 P2-1 切策略需先行处理。
- 远端部署环境 conda sglang-patch（Python 3.10.12）与本机 Python 版本差异不影响 py_compile
  结果（双侧均 exit 0）。
- 既有 I1-I6 属 e3-10 临测件，与本任务新增行同树共存；是否整体保留待 P2-0a 裁决。
