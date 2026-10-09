# p2io-tester-e5 — M4T-e5：e9（frontier park + DEMAND_RESTORE ticket）终裁重测

## 1. status

**done** — 同步核验 9/9 一致；M4T 同配置终裁重测完整跑完（96 请求 0 失败，rc=0）。判据裁决：
**FAIL（双层门均不过）**。数据面 B（整链完成窗口）p50=1.158s 差于 1.0s 门 16%；机制面
**T15 全程 0 次触发**（0 park / 0 wake / 0 demand ticket）——e9 的 frontier 严格条件在本负载
下从不满足（在途备份目标从不覆盖请求终点），e4 的 72 次 park 全部被正确消除，但 T15 对
本负载贡献为零，行为回到 M4T 基线（partial restore + T6 DEVICE_QUOTA/PREFETCH_BUDGET 循环），
A（request-level cycle）p90=10.7s 仍 > 几秒级（T6 主导，Ready Horizon 域，范围外）。与 e4
相比的唯一改善：park→rate-limit 灾难消失（A p90 47.9→10.7s）。判据逐条见 §4。

## 2. artifacts

**同步核验（9 文件 md5 双侧逐字节一致，3090 部署树 /root/sglang-b1-continuity）**：
| 文件 | md5 | 一致 |
|---|---|---|
| scheduler_components/hicache_restore.py | afe9f27a… | ✓ |
| mem_cache/unified_radix_cache.py | 6405ac21… | ✓ |
| managers/scheduler.py | ad91a701… | ✓ |
| mem_cache/unified_cache/unified_tree_core.py | d12613c8… | ✓ |
| mem_cache/unified_cache/unified_tree_core_interface.py | a630d5a1… | ✓ |
| 3090-dev/test_hicache_restore.py | 414448be… | ✓ |
| 3090-dev/test_drain_reentry.py | 8cde0632… | ✓ |
| 3090-dev/test_hicache_restore_scheduler_feed.py | de1143ed… | ✓ |
| 3090-dev/test_storage_regression.py | eb3a8485… | ✓ |

引擎核心未动（e3 状态复核）：cache_controller 0d63a8e8 / hicache_storage 22348ed0 /
extent_file_backend 534683c6。e9 符号在位：backup_wake_applies / DEMAND_RESTORE_MAX_INFLIGHT /
chain_backup_frontiers / _backup_wait_spans / _restore_backup_wake_ready。旧版备份
.bak-e9-20260901/ 在位（8 文件，新文件 test_hicache_restore_scheduler_feed.py 无旧版）。

**运行（M4T 同配置：host 5G，K=8，96 请求，extent v1）**：
- run-20260901-024649，engine 02:46:48 healthy，driver 02:46:48→02:57:24 **rc=0**，
  elapsed **635.2s**；96 请求 **0 失败**，downgraded=**7**（M4T 4 / e4 3 / M4F 5——本轮偏高，
  观察项）。
- 证据：/root/evidence-p2io-extent-m4t-e5/run-20260901-024649/；/root/engine-p2io-m4t-e5.log
  （[P2A] 4148 行）；io/fd before-after；采样器 62MB 留存 3090。
- 脚本：/root/p2io-m4t-e5-run.sh（e4 脚本改名副本，输出命名 e5，基线文件未覆盖）。
- 本机分析：/tmp/p2io-e5/（metric_compare 规范口径 + analyze_p2a + trace_rid）。

**清理**：进程树 0、GPU 15 MiB / 24576 MiB、dmesg OOM=0、/data 51.3GB；无代码修改
（部署树聚合 md5 复核 0 差异）；无删除。

## 3. evidence（真实命令与输出）

**同步**：
```
$ md5sum … 9 文件（双侧同列 §2 值，逐字节一致）
$ python3 -c "import sglang.srt.managers.scheduler_components.hicache_restore as m;
   print(m.__file__, hasattr(m,'backup_wake_applies'), m.DEMAND_RESTORE_MAX_INFLIGHT)"
/root/sglang-b1-continuity/python/…/hicache_restore.py True 4
```

**运行状态**：
```
$ tail -4 /root/p2io-m4t-e5-status.log
[02:57:24] M4T-e5 driver finished rc=0 evidence=/root/evidence-p2io-extent-m4t-e5
[02:57:46] M4T-e5 stage: engine SIGTERMed, remaining python procs=1, gpu_mib=15 MiB
$ verdict.json: status done, 96 requests, failed 0, downgraded 7, elapsed 635.2
$ dmesg oom/killed: 0；运行时 Traceback（line 700–6400）: 0
```

**[P2A] 总览（e5 vs 基线 vs e4）**：
```
                M4T base    e4 (e8)     e5 (e9)
prefetch_issued 544         529         463
revoke          453         461         377
io_finished     91          68          86
守恒            ✓           ✓           ✓ (463=377+86)
recompute       455(453miss) 392(389)   378(377miss, 1 timeout)
retry           554         547         468 (capacity 429 + frontier 39)
disposition     RECOMPUTE 502 / PARTIAL 64 / WAIT 33
                                    RECOMPUTE 412 / PARTIAL 60 / WAIT 129
                                              RECOMPUTE 418 / PARTIAL 58 / WAIT 36
revoked:backup_pending: 0 / 72 / 0     ← e5 零 park
denied_rate_limit→WAIT: 33 / 57 / 36
```

**B / A 双列（metric_compare 规范口径，全部 >20k 整链子集）**：
```
[B finish-matched 末次 issue→finish]   n    p50    p90    p95    max
  M4T baseline                         11   1.051  1.871  2.135  2.135
  e4 (e8)                              17   1.236  1.495  1.498  1.744
  e5 (e9)                              15   1.158  1.720  1.720  1.960   ← 门 <1.0s FAIL
  （e5 全部 86 次成功 restore：B p50=0.786 p90=1.285）

[A issued-matched 每次issue→首次finish] n    p50    p90    p95    max
  M4T baseline                         46   2.855  3.302  —      9.784
  e4 (e8)                              43   3.199  47.927 63.194 69.843
  e5 (e9)                              40   9.895  10.663 14.353 41.632   ← 尾巴仍 10s+

[A episode 首次issue→最终finish]       n    p50    p90    max
  M4T baseline                          7   21.314 47.546 49.670
  e4 (e8)                              11   24.755 69.843 75.924
  e5 (e9)                               8   34.415 41.632 42.971

[A−B 浪费量（episode − 最终 B 窗口，Ready Horizon KPI）]  p50   p90   max
  M4T baseline                                            20.0  46.3  47.8
  e4 (e8)                                                 23.4  68.5  74.4
  e5 (e9)                                                 32.5  40.3  41.9   ← 未改善（T6 主导）
```

**状态机指标（e5）**：
```
lookup/rid: n_rids=95 p50=3 p95=7 max=35  dist={1:12,2:14,3:25,4:20,5:11,6:6,7:2,24:1,34:1,35:3}
BACKUP_PENDING: parks=0 wake=0 demand_tickets=0（restore_state 无 BACKUP_PENDING 条目；
   disposition 无 revoked:backup_pending）
WAIT residence: DEVICE_QUOTA n=378 p50=0.530 p95=11.510 max=40.585
                PREFETCH_BUDGET n=36 p50=1.300 p90=29.264 max=52.395
                FRONTIER n=55 p50=0.524 max=0.640
retry wait (revoke→issued): n=302 p50=0.519 p90=16.721 max=26.240
partial IO: rids_with_finish=54 rids_with_partial=48 ratio=88.9%
```

**五门/数据面**：
```
amplification: read_bytes Δ=+6.9GB（io-before 7.09GB→after 13.95GB）；requested≈24.0GB
  （812,789 tokens × 31KB）→ 物理读/请求 = 0.27（页缓存温，仅计落盘 miss）——本轮不可实测，
  M4F 探针口径 physical/requested=1.0000 保持，无放大证据
backup failure: 0 "pwrite failed" / 0 "pages failed"；backuped_tokens_total=1,630,835
  （健康平台值 1.5–1.9M）；dropped kv=150,729（M4T 160,885 / e4 158,095——略优）
syscall: syscr Δ=+6,192（~1.1MB/次读）；单持久 fd（flags 02100002 无 O_DIRECT）
correctness: sha16 确定性会话 51 tag，13 分歧——3 个（a1-t5-restore=f6b66de0、a8-t5-restore
  =adefe7c5、a8-t10-grow=47ee90a4）与 e4 逐字节同值（跨 run 稳定模式），其余为已知非确定性
  家族（downgrade 注入时机差：a1-t9/a8-t3/a8-t4/a8-t11 在 e5 轮 MISSING）；无乱码/截断/损坏
  签名
ttft：restore turns n=24 p50=46.1s p90=58.9s max=70.1s（M4T 46.9s——请求级同量级）
```

## 4. summary

**判据逐条（用户终裁定案）**：
| # | 判据 | e5 实测 | verdict |
|---|---|---|---|
| 1 | B p50 < 1.0s（整链 ≥20k 完成窗口） | **1.158s**（n=15，p90=1.720，max=1.960；全部成功 restore B p50=0.786s） | **FAIL**（差 16%；读路径未动，B 在所有轮次 1.05–1.32s，非 e9 可及） |
| 2 | amplification ≈ 1.0× | 物理读 6.9GB < 请求 24.0GB（缓存温，不可测）；0 写失败 | PASS（探针口径 M4F 1.0000 保持，无放大证据） |
| 3 | correctness / backup failure / OOM | sha16 分歧全在已知家族（3 个与 e4 同值）；0 pwrite 失败；0 OOM；0 运行时异常 | **PASS** |
| 4 | park→full-hit > 90% | **0 次 park** | **FAIL/N-A**（机制从未触发） |
| 5 | park 后 partial IO ≈ 0 | 0 次 park | N-A（无样本） |
| 6 | lookup 主体 ≤2–3 次/rid | p50=**3**（51/95 rid ≤3）、p95=7、max=35 | **PASS（边际）**：p50 与 M4T 基线同值；5 个 rid 24–35 次尾巴仍在 |
| 7 | wake 后不进 PREFETCH_BUDGET | 0 wake / 0 demand ticket | N-A（ticket 未被执行） |
| 8 | A 十几秒尾巴消失、p90 回几秒级 | A(issued-matched) p90=**10.66s**；episode p50=34.4s | **FAIL**（10.7s 仍 >几秒级；优于 e4 47.9s，差于 M4T 3.3s——T6 主导） |
| 9 | BACKUP_PENDING residence p95 秒级 | 0 park | N-A |

**A−B 浪费量（Ready Horizon KPI）**：e5 p50=**32.5s** / e4 23.4s / M4T 20.0s——**未改善**
（本轮 T6 DEVICE_QUOTA 压力偏高：residence p90=7.8s / max=40.6s，downgraded 7）。

**机制归因（0 parks 的根因）**：e9 R1 要求 park 仅在"在途备份目标覆盖请求终点"
（backup_target_frontier ≥ requested）时发生。本负载 restore 的缺失尾 = host 驻留未驱逐段
（或 dropped-without-backup，25–36 次/轮），**从不在在途写 span 内**——备份前沿恒落后于
请求终点 → 条件永不满足 → 永不 park。e4 的 72 次 park 全部为 R1 counter-example 型
（在途写不覆盖尾，wake 后仍 partial），e9 正确地将其归零，但 T15 对本负载的净贡献 = 0，
e5 行为 ≡ M4T 基线（无 park 语义）：partial restore（58）+ T6/T11 循环。残余 A 尾巴
（p90=10.7s）由 DEVICE_QUOTA（T6，Ready Horizon 域）与 PREFETCH_BUDGET（p90=29.3s）主导，
均不在 e9 改动面。B=1.158s 需读路径优化（批大小/连续化，M4F 归因 10.4/12.3 挂账），
与 e9 无关。

**结论**：T15 事件驱动 restore wake 在 5G host 压力负载下**两代实现均无收益**——e8 版本
（宽松 park）产生 72 次虚假 park 拖出 47.9s 尾巴；e9 版本（严格 frontier）正确消除虚假
park 但条件在本负载下从不成立，机制归零。剩余瓶颈回到 M4T 基线形态：B=1.16s（读路径）
+ T6 device-full 等待（Ready Horizon 域）。

## 5. followups

1. **T15 判死或重定向（orchestrator/architect 决策）**：本负载（5G host 压力，备份恒落后于
   请求终点）不存在"备份在途覆盖尾"的竞态窗口——T15 前提不成立。若目标负载含"链稳定+
   备份在途"场景（如长链重访、无 host 压力），T15 才可能生效；当前 5G 配置下应移除或降级
   为纯观察。数据支持：e4 72 parks→18.6% full-hit；e9 0 parks（条件恒假）。
2. **B < 1.0s 唯一路径 = 读路径优化（coder，M4F followup 挂账）**：restore 批大小
   128→512–1024 或 allocator 连续化（单区间/批）——B 四轮稳定 1.05–1.32s，读路径未动，
   任何状态机改动都无法越过该门。
3. **A 尾巴 = Ready Horizon（T6 device-full）**：e8/e9 均明示范围外；A−B KPI（32.5s）量化了
   等待浪费——host tier/准入优化是其归属。
4. **观察项**：downgraded 7（前几轮 3–5）——本轮 T6/PREFETCH_BUDGET 压力偏高（run 级方差，
   write 速率曲线仍 ~190MB/s 饱和同形）；如需统计置信可复跑。
5. 证据路径：e5 run-20260901-024649；分析脚本 /tmp/p2io-e5/、/tmp/p2io-e4/metric_compare.py。

## 6. open_issues

- 单轮实验；FAIL 判定由"0 parks + B 超门 + A p90 10.7s"三独立证据支持，机制归因完整
  （trace f161f76c：FRONTIER 2s + DQ 22s + alloc_failed + DQ 13s + IO 1s = 41.6s，无 park）。
- 3090 部署树保持 e9 态（9 文件 md5 双侧一致），未修改；.bak-e9-20260901/ 未触碰；
  实验脚本 /root/p2io-m4t-e5-run.sh 留存。
- 基线一致性（§7 前置分析）结论沿用：B 口径为唯一判据口径（M4T 1.051 / M4F 1.320 /
  e5 1.158），A 需标注 issued-matched 或 episode 子口径。
