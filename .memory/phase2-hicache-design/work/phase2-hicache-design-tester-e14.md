# P2-1 正式终判（A）— tester e14 报告

## 1. status

**blocked** — K=8 无截断完整 run 两次尝试均被**外部 SIGTERM**（引擎启动后约 5–6.5 分钟，非协调人 25 分钟护栏）截断；
归因分析已完整交付（基于事件日志，不受截断影响）。待协调人裁决 SIGTERM 来源（疑似协调人侧执行机制）后重跑。

## 2. artifacts

- /root/evidence-p2b0-1f/：run-20260830-213930（50 http 200 + 46 failed，elapsed 392s）、run-20260830-214853（39 + 57，elapsed 293s）、k8-driver.log、k8-r2-driver.log、MD5SUMS
- /root/engine-p2b0-1f.log、/root/engine-p2b0-1f2.log（两次引擎日志）
- run-20260830-213930 内：join.log（96 行）、verdict.json、metric-table.json/csv、events-table.csv、mid-run-metrics.txt、turns/、END-BANNER.txt
- 12 指标表（run-20260830-213930 截断前）：recompute 380,291 / restore 362,858 / turns/s 0.130 / p95 121.3s（截断窗口值，非终判值）
- **recompute 六类归因表**（见 summary 3）+ **denied_rate_limit 归因**（见 summary 4）

## 3. summary

### 3.1 截断证据（两次，模式相同）

| run | 引擎启动 | 截断时刻 | 存活 | 成功/失败 | 截断形态 |
|---|---|---|---|---|---|
| 1f | 21:39:30 | **21:46:01** | 392s | 50 / 46 | 46 个 failed 行 ts_end 全部 = 1788097562（同秒）= 引擎死亡时 in-flight 被标记失败；引擎日志 destroy_process_group → kill_process_tree（parent_pid=122762），外部 SIGTERM |
| 1f2 | 21:48:51 | **21:53:46** | 293s | 39 / 57 | 同上（parent_pid=124024） |

已排除来源：crontab（仅 report_ban_ips.sh）、systemd timers、我的监控/驱动进程（0 残留）、OOM（dmesg 无输出）、25 分钟护栏（不符合时间特征）。
截断前引擎正常：21:45:59 仍在处理（frontier_wake、prefetch 事件、10 次 mamba fetch 失败、1 次 revoked:alloc_failed）。

### 3.2 判据（截断前全绿，但非终判值）

- 签名：join 全部成功行 output_sha16 存在且一致（downgraded=0）
- CHAIN_GAP：0c 链 earliest=0 已在 e13 验证；本次 run 未再写链（recompute 不产生链写入）
- 优雅退出：**无**（外部 SIGTERM）
- 0 残留：pgrep 无 launch_server/agent_driver；GPU 15MiB/0%（已释放）

### 3.3 recompute 六类归因（36 个 restore_recompute 事件，token = 该 rid 最后一次 restore_disposition 的 requested）

| 类别 | rid 数（事件数） | tokens | 占比(按 token) | 证据 |
|---|---|---|---|---|
| 1. true miss | 3（6 行） | 46,355 | 11.4% | restore_recompute cause=miss + disposition reason=revoked:miss ×6 |
| 2. frontier wait timeout | 14（16 行） | 338,474 | 83.4% | cause=timeout；frontier_wait 注册 1,042 / frontier_wake 仅 11 — 60s 时钟超时是主导结束路径 |
| 3. rate-limit deny | 10 终态 recompute（34 拒绝事件） | 152,082 被拒（granted=0） | — | disposition reason=denied_rate_limit ×34，见 3.4 |
| 4. too_short | 6（8 行） | 21,185 | 5.2% | cause=too_short + disposition reason=too_short ×28（79 tokens，granted=0） |
| 5. shutdown-truncation | 46 在途（+57 重试） | 0（未产出） | — | join http!=200 且 finished=False，new_tokens_est=0 |
| 6. other | — | — | — | hybrid_discard ×9（132,361 req / 128,036 granted）、revoked:alloc_failed ×1（20,864）、restore_loadback_fail ×1、mamba fetch 失败 ×10 |

recompute 总计（1+2+4）：406,014 tokens / 23 个终态 rid（36 日志事件含重试）。frontier wait timeout 占 83.4% — 与 e13 观察一致（wake 稀缺，等待端多由超时收尾）。

### 3.4 denied_rate_limit 归因（34 个 RID 全量事件链）

- **结论：rate-limit 不是永久放弃**。34 个被拒 RID 终态：**21 个 restore_ready（62%）**、10 个 restore_recompute、3 个在途截断（引擎死亡时未决）。
- 事件链示例（e43aa54f8818）：restore_retry → prefetch_issued → io_finished → io_done → finalize → **restore_disposition denied_rate_limit** → restore_state → **restore_ready**（拒绝后仍在链中，被后续 slot 释放唤醒并 restore 成功）。
- 反例（c2c2115cc797）：restore_state → ready → … → restore_disposition → restore_state → **restore_recompute**（被拒后重试耗尽，转 recompute）。
- 这正是 M2 wake 修复（5f07791c/2bb64a91）的功效：denied_rate_limit 的 RID 不再丢出状态机，62% 后续 restore 成功。

## 4. followups

1. **SIGTERM 来源**（阻断项）：两次均在启动后 5–6.5 分钟，非 cron/systemd/OOM/我的进程。时间特征与协调人"25 分钟护栏"不符，疑似协调人侧执行代理的周期性机制。建议协调人核查其执行层（是否对 ssh 长命令有 ~5 分钟超时/心跳机制）。
2. 截断前 12 指标表已生成（1f 内 mid-run-metrics.txt），可作为部分窗口参考，不可作为终判。
3. 重跑前置：确认外部 SIGTERM 来源消除后，第三次 K=8 完整 run（复用 0c 链），时间盒 25 分钟护栏保持。

## 5. open_issues

- 未知外部 SIGTERM（两次，时间戳 21:46:01 / 21:53:46，kill_process_tree parent_pid=122762/124024）——阻塞终判唯一问题。
- 六类归因中"frontier wait timeout 83.4%"占比偏高：wake 仅 11 次 vs wait 注册 1,042 次（多轮重试放大），若终判后需优化，方向是 wake 谓词覆盖（frontier_anchor_ready 之外的 wait 场景），此点仅记录不判定。
