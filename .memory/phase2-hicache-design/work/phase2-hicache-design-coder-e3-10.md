# P2-0a 归因插桩实施 — log-only 观测插桩落地（coder e3-10）

## status

**done** — 5 项插桩（I1/I2/I3/I5/I6）全部落地：本机 3 文件 18 行纯新增（16 行日志 + 1 行
条件包装 + 1 行 import），git diff 逐行审查通过（0 删除/0 修改）；py_compile 本机/远端均
exit 0；scp 部署 3090 后双侧 md5 一致；3090 当前无引擎进程（GPU 15MiB 空闲）。

## artifacts

| 文件（本机 + 3090 部署同路径） | 改动 | 行数 |
|---|---|---|
| `python/sglang/srt/managers/scheduler.py` | I1（6 行）+ I2（1 行）+ I5 调度侧（1 行） | +9（1 个 if 包装 + 8 行 logger） |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | I3（1 行）+ I6（1 行） | +2 |
| `python/sglang/srt/managers/schedule_policy.py` | I5 原因粒度 6 门（6 行）+ `import time`（1 行） | +7 |

3090 部署路径：`/root/sglang-b1-continuity/python/sglang/srt/managers/{scheduler,schedule_policy}.py`、
`/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_radix_cache.py`。
未 commit 未 push（临测件，按裁决保留或回退）。

## 插桩清单落地表

| ID | 位置（本机行号） | 事件 | 内容 | 行数 |
|---|---|---|---|---|
| I1 | scheduler.py:3451-3452（reset 前） | `evt=bif_reset` | 仅当旧值 True 打（`if running_batch.batch_is_full:` 包装，纯读不写） | 1 logger + 1 if |
| I1 | scheduler.py:3483 后（allocatable≤0 set） | `evt=bif_set reason=allocatable` | 无 rid（循环前，批级） | 1 |
| I1 | scheduler.py:3564 后（can_run≥allocatable set） | `evt=bif_set reason=can_run rid=%s` | req.rid | 1 |
| I1 | scheduler.py:3569 后（disagg prefill set） | `evt=bif_set reason=disagg rid=%s` | req.rid | 1 |
| I1 | scheduler.py:3619 后（NO_TOKEN+hicache set） | `evt=bif_set reason=no_token_hicache rid=%s` | req.rid | 1 |
| I1 | scheduler.py:3623 后（NO_TOKEN else set） | `evt=bif_set reason=no_token rid=%s` | req.rid | 1 |
| I2 | scheduler.py:3555 后（FCFS 扫描循环内，admit 前） | `evt=admission rid=%s pos=%d qlen=%d running_bs=%d can_run=%d` | pos=`self.waiting_queue.index(req)`（扫描期队列不突变，等价 enumerate）；qlen=len(waiting_queue)；can_run=len(adder.can_run_list) | 1 |
| I3 | unified_radix_cache.py:2518 后（`if ack.completed_req:` 分支首行） | `evt=prefetch_io_done rid=%s completed=%s` | rid=operation.request_id；completed=ack.completed_tokens（io_done 时间点） | 1 |
| I5 | scheduler.py:3616 后（NO_TOKEN 分支首行） | `evt=no_token rid=%s res=%s can_run=%d` | res=AddReqResult 枚举（%s） | 1 |
| I5 | schedule_policy.py:1243 门内 | `evt=prefill_deny rid=%s reason=rem_total_tokens total=%d rem=%d` | 锁前 total 门 | 1 |
| I5 | schedule_policy.py:1256 门内 | `evt=prefill_deny rid=%s reason=swa_budget swa_needed=%d rem=%d` | SWA 门 | 1 |
| I5 | schedule_policy.py:1270 门内 | `evt=prefill_deny rid=%s reason=rem_input_tokens real_input=%d rem=%d` | 无 chunked 时 input 门（OTHER） | 1 |
| I5 | schedule_policy.py:1282 门内 | `evt=prefill_deny rid=%s reason=rem_total_tokens_lock total=%d rem=%d` | 锁后 total 门（budget 移动信号） | 1 |
| I5 | schedule_policy.py:1292 门内 | `evt=prefill_deny rid=%s reason=swa_budget_lock swa_needed=%d rem=%d` | 锁后 SWA 门 | 1 |
| I5 | schedule_policy.py:1309 门内 | `evt=prefill_deny rid=%s reason=prefill_delayer` | delayer 门（OTHER） | 1 |
| I6 | unified_radix_cache.py:1932 后（`stats["issued"] += 1` 处） | `evt=prefetch_issued rid=%s prefetch_length=%d` | L3→H requested；req_id/prefetch_length 作用域内（下方 t38c 同用） | 1 |

格式统一：`logger.info("[P2A] ts_ms=%d evt=...", int(time.time() * 1000), ...)` —
`[P2A]` 前缀 + 显式 `int(time.time()*1000)` 毫秒字段（不依赖 SGLANG_LOG_MS），key=value
风格对齐仓库既有日志（如 "HiCache prefetch success req=..."）；每处单行单语句。

## evidence

1. 本机 `python3 -m py_compile`（scheduler.py / unified_radix_cache.py / schedule_policy.py）：
   `exit=0`。
2. git diff 审查：`git diff --stat` = `3 files changed, 18 insertions(+)`，**0 deletions，
   0 modifications**；全 diff 逐行过目，18 行 = 16 行 `[P2A]` logger + 1 行 reset 条件包装
   `if running_batch.batch_is_full:`（只包日志、纯读） + 1 行 `import time`。所有插桩引用
   变量（req.rid / total_tokens / rem_total_tokens / swa_needed / rem_swa_tokens /
   real_input_tokens / rem_input_tokens / req_id / prefetch_length / operation.request_id /
   ack.completed_tokens / running_bs / adder.can_run_list）均经行级 Read 确认作用域内。
3. 落地核对：`grep -c '\[P2A\]'` 本机 = scheduler 8 / unified_radix_cache 2 / schedule_policy 6；
   evt 分布 = bif_reset×1 + bif_set×5 + admission×1 + no_token×1 + prefetch_issued×1 +
   prefetch_io_done×1 + prefill_deny×6 = 16。
4. 部署前双侧基线 md5 一致（3 文件与远端部署逐字节相同，覆盖安全）；部署后：
   - scheduler.py md5 `4f202059639d8f81cf6381cb3a69a67b`（双侧一致）
   - unified_radix_cache.py md5 `7632cb7d48706ad657b866a0d0bcbee1`（双侧一致）
   - schedule_policy.py md5 `855a69fa79e9ae665fad41a1cdf0ef11`（双侧一致）
5. 远端 py_compile：`/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python
   3.10.21）三个文件 `exit=0`；远端 `grep -c '\[P2A\]'` = 8/2/6 与本机一致。
6. 3090 引擎进程：`ps -eo pid,args | grep -iE 'launch_server|engine.*server'`（滤自匹配）=
   0；`nvidia-smi` compute-apps 空、显存 15 MiB/24576 MiB（空闲）；`ss -tlnp` 无 30000-30009
   监听。K=32 引擎 SIGTERM 后确认无残留，部署后未启动引擎（实验启动归 tester）。

## summary

按勘察表 e3-09 的 I1-I6 清单实施 log-only 插桩，全部落地为单行 `logger.info`，统一
`[P2A] ts_ms=...` 格式（显式 ms 便于与 b15/t38c 探针 ts 配对）。batch_is_full 获得完整
false→true→false 时间线（reset 转换 + 4 类 set 原因，含 NO_TOKEN 的 hicache/else 两分支）；
admission 行给出 rid/队列位置/running_bs/can_run 快照；prefetch_issued 补 L3→H requested；
prefetch_io_done 补 io_done 端点（与 success 行/pc_l3_host 按 rid 配对得 completion→
finalization 延迟）；prefill_deny 6 门给出 NO_TOKEN/OTHER 的预算级原因（含锁前/锁后区分，
可观测 restore-quota 压缩导致的 budget 移动）。零逻辑改动：16 行日志 + 1 条件包装（纯读）
+ 1 行 import time。

## followups

- tester 启动实验（3090，冻结参数）后，解析侧按 evt 名 grep `[P2A]` 行；配对键 = rid，
  时间键 = ts_ms（与 b15 探针 `ts`（秒浮点）×1000 对齐）。
- I1 的 `bif_reset` 只在旧值 True 时发射——若整轮 0 命中，属"每 pass 均从 False 起"的
  正常静默，不是插桩失效；判定依据是 `bif_set` 行的存在性。
- I2 的 pos 用 `waiting_queue.index(req)`（O(n)，扫描期队列不突变，等价 enumerate）；
  默认 fcfs 下 pos 即到达序，abort/retract 会扰动——与客户端 ts_sched 代理交叉时注意。
- 本分支插桩为临测件：P2-0a 裁决后按结果保留或回退（git checkout 受限，回退需按
  `git diff` 逆操作或 `git show HEAD:<path>` 恢复——本任务未 commit，HEAD 即原始状态）。

## open_issues

- schedule_policy.py 缺 `import time`，为满足派发格式要求（显式 ms 字段）新增 1 行标准库
  import——这是 18 行 diff 中唯一非日志行；属"只插入新行"且零逻辑，已在 diff 审查中明示。
- 插桩行较长（evt=admission 行约 250 字符），未按仓库惯例折行——为满足"每处一行"字面要求
  保持单物理行；若后续合并入主干，可考虑折行 + 复核。
- SWA 门（1256/1292）日志在"门被进入"时发射，其中 swa_cap 子分支可能最终仍成功（chunk
  限额压缩）——`prefill_deny reason=swa_budget*` 表示预算门触发，不等于必然拒绝；最终
  结果以调度侧 `evt=no_token`（仅 NO_TOKEN 时发射）为准，两者配对解读。
- 远端部署环境为 conda sglang-patch（Python 3.10.21）与 sglang-dev（CUDA 路径）双 env；
  引擎实际运行 env 以 launch 脚本为准，py_compile 已按派发指定用 sglang-patch 验证。
