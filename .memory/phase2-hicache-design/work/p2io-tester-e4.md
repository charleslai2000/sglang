# p2io-tester-e4 — M4T-e4：事件驱动 restore wake（coder e8 T15）3090 验证

## 1. status

**done** — 代码同步核验 9/9 一致；M4T 同配置实验完整跑完（96 请求 0 失败，rc=0）；判据裁决：
**P2-IO 未 CLOSED**。T15 park 机制本身生效且无 lost-wake 孤儿（BACKUP_PENDING residence
p50=0.70s / max=3.74s，无 ~60s 样本，per-pass predicate 兜底成立），但核心指标全部 FAIL 且
**整链 restore p90 较基线恶化**（3.9s→47.9s）：park 等待的写在途 span 常不含缺失尾（drop-
without-backup / 链增长），wake 后 re-lookup 仍 partial；且 wake 后 re-issue 与 prefetch
rate limit（预算 ≈ 单条整链 20,910 tokens）碰撞，57 次 denied_rate_limit → PREFETCH_BUDGET
等待 p90=18.4s 成为新尾延迟。判据逐条证据见 §4；根因与修复方向见 §5。

## 2. artifacts

**同步核验（3090 部署树 vs 本机，9 文件 md5 逐字节一致）**：
| 文件 | md5 | 一致 |
|---|---|---|
| python/sglang/srt/managers/scheduler_components/hicache_restore.py | 5c8df78f… | ✓ |
| python/sglang/srt/mem_cache/unified_radix_cache.py | 495d10d5… | ✓ |
| python/sglang/srt/managers/scheduler.py | 7290c368… | ✓ |
| python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py | 35b2e82f… | ✓ |
| python/sglang/srt/mem_cache/unified_cache/unified_tree_core_interface.py | c12e1982… | ✓ |
| 3090-dev/test_hicache_restore.py | 6fc6f4c1… | ✓ |
| 3090-dev/test_drain_reentry.py | 2d8f66a7… | ✓ |
| 3090-dev/test_hicache_restore_scheduler_feed.py | 8588a8b6… | ✓ |
| 3090-dev/test_storage_regression.py | 835256e9… | ✓ |

引擎核心一致性复核（与 e3 状态相同）：cache_controller **0d63a8e8** / hicache_storage
**22348ed0** / extent_file_backend **534683c6** / hybrid_cache_controller **3bb6ae94**；
部署树 8 文件聚合 md5 双侧 98c1f9dd（实验前后复核，0 改动）。T15 在位确认：
`RestoreEvent.BACKUP_PENDING` 存在、`sglang.srt` 各模块 resolve 到部署树
（`/root/sglang-b1-continuity/python/...`）。

**运行（M4T 同配置：host 5G，K=8，96 请求，extent v1，SGLANG_PORT=8024）**：
- run-20260901-015701，engine 01:57:00 healthy，driver 01:57:00→02:07:19 **rc=0**，
  elapsed **617.4s**（基线 M4T 646.8s）；96 请求 **0 失败**，downgraded=3（基线 4）。
- 证据：/root/evidence-p2io-extent-m4t-e4/run-20260901-015701/（8 agent json +
  mid-run-metrics + runs.csv + verdict.json）；/root/engine-p2io-m4t-e4.log（[P2A] 4586 行）；
  /root/p2io-m4t-e4-{io,fd}-{before,after}.txt；采样器 p2io-m4t-e4-samples.jsonl（62MB 留存 3090）。
- 脚本：/root/p2io-m4t-e4-run.sh（M4T 脚本改名副本，输出命名 e4，基线文件未覆盖）。
- 本机分析：/tmp/p2io-e4/{analyze_p2a.py,trace_rid.py,rid_summary.py,compare_sha16.py}；
  基线对照用 e3 M4T 引擎日志（engine-p2io-m4t.log）与证据目录。

**清理（脚本内建 SIGTERM 步 + 复核）**：进程树 0（sglang::/launch_server/agent_driver/
sampler 全无），GPU 15 MiB / 24576 MiB，dmesg OOM=0，/data 余 51.3GB（循环文件不增长）。
无代码修改（部署树 md5 复核 0 差异）；无删除操作；不碰 .bak-e8-20260901/。

## 3. evidence（真实命令与输出）

**同步核验**（3090，实验前）：
```
$ md5sum …/{hicache_restore,unified_radix_cache,scheduler,unified_tree_core,
           unified_tree_core_interface}.py 3090-dev/test_*.py
5c8df78f… 495d10d5… 7290c368… 35b2e82f… c12e1982… 6fc6f4c1… 2d8f66a7… 8588a8b6… 835256e9…
（与本机逐字节一致）
$ python3 -c "import sglang.srt.managers.scheduler_components.hicache_restore as m;
               print(m.__file__, hasattr(m.RestoreEvent,'BACKUP_PENDING'))"
/root/sglang-b1-continuity/python/sglang/…/hicache_restore.py True
```

**运行状态**（3090）：
```
$ cat /root/p2io-m4t-e4-status.log
[01:57:00] M4T-e4 engine healthy
[02:07:19] M4T-e4 driver finished rc=0 evidence=/root/evidence-p2io-extent-m4t-e4
[02:07:41] M4T-e4 stage: engine SIGTERMed, remaining python procs=1, gpu_mib=15 MiB
$ cat …/verdict.json | head -c 200   # status done, 96 requests, failed 0, downgraded 3, elapsed 617.4
```

**[P2A] 事件总览（e4 vs 基线）**：
```
                baseline M4T        e4 (T15)
prefetch_issued 544                 529
prefetch_revoke 453                 461
io_finished     91                  68
restore_ready   91                  68
restore_recompute 455 (miss 453, timeout 2)   392 (miss 389, timeout 3)
restore_retry   554 (capacity 511, frontier 43) 547 (capacity 509, frontier 38)
disposition     RECOMPUTE 502 / PARTIAL 64 / WAIT 33   RECOMPUTE 412 / PARTIAL 60 / WAIT 129
frontier_wait/wake 54/43            45/38
守恒           544=453+91 ✓        529=461+68 ✓
```

**判据 1 — lookup/rid（同 rid prefetch_issued 次数）**：
```
baseline: n_rids=93 min=1 p50=3 p95=34 max=37
e4:       n_rids=94 min=1 p50=4 p95=9  max=38   dist={1:11,2:12,3:15,4:16,5:19,6:6,7:6,8:3,9:1,33:1,35:1,36:1,37:1,38:1}
```

**判据 2 — 重试等待（revoke→next issued）**：
```
baseline: n=384 p50=0.015s p75=9.370 p90=15.698 p95=17.341 p99=29.206 max=33.506 mean=4.642
e4:       n=384 p50=0.573s p75=9.556 p90=16.238 p95=17.728 p99=19.779 max=45.838 mean=4.919
```

**判据 3 — 整链 restore（issued→io_finished，finish n_tokens≥20k）**：
```
baseline: n=55 p50=2.806 p75=3.129 p90=3.901 p95=7.983 max=17.208 mean=3.105
          <2s:16  2-5s:34  5-15s:4  ≥15s:1
e4:       n=44 p50=3.199 p75=17.909 p90=47.927 p95=63.194 max=69.843 mean=13.197
          <2s:18  2-5s:9   5-15s:4  ≥15s:13
（all spans n=188 p50=1.975 p90=17.909 p95=30.439 max=69.843）
```

**判据 4 — recompute cause=miss 与 partial**：
```
e4 recompute causes: {miss:389, timeout:3}   （基线 miss=453 → -14%，未消失）
e4 partial IO: rids_with_finish=54, rids_with_partial=44, ratio=81.5%（基线 94.5%）
e4 disposition: revoked:miss→RECOMPUTE 352 / revoked:backup_pending→WAIT 72 /
   revoked:insufficient→RECOMPUTE 37 / denied_rate_limit→WAIT 57 / shortfall→PARTIAL 60
```

**判据 5 — 守恒 / 崩溃 / OOM**：529=461+68 ✓；96/96 完成；引擎日志 Traceback 62 处全部为
启动期 torchcodec 加载警告（line 32–622）与 SIGTERM 关闭路径（line 6802+，SystemExit: 0），
运行时 0 异常；dmesg oom/killed 0 匹配；backup 写侧 0 "pwrite failed"/0 "pages failed"。

**判据 6 — 五门**：
```
a. 整链 p50≤1.0s：FAIL（3.199s；fast 组 18 样本 <2s 证明路径可达，min=0.53s）
b. 读放大≈1.0×：本轮不可测（页缓存温：read_bytes Δ=11.28GiB < requested≈23.4GiB@31KB/页，
   差值即缓存命中；M4F 探针口径 physical/requested=1.0000 保持为权威值）
c. 无 backup failure：PASS（0 写失败；backuped_tokens_total 1,555,721 在健康平台值 1.5–1.9M）
d. syscall 稳定可解释：syscr Δ=+6,218（基线 +3,666）；read_bytes 11.28GiB/6,218≈1.9MB/次；
   单持久 fd（flags 02100002 无 O_DIRECT 位，前后一致）；~91 次读/整链 ≈ 21 批 × ~4，批结构可解释
e. correctness：PASS（sha16 确定性会话 S1/S2/S3/S8 50 tag：37 逐字节一致；13 DIFF 全部落入
   已知非确定性家族——a8-t5-restore=e4=adefe7c5=基线 a8-t1 值（同前缀重放）、a1-t5-restore
   第三值（M4F=c71201d3/基线=b140e9da/e4=f6b66de0，M3 已证前置非确定性）；无乱码/截断/损坏签名；
   0 崩溃 0 OOM）
```

**协调者追加指标**：
```
BACKUP_PENDING residence（n=72）：min=0.000 p50=0.703 p75=1.421 p90=1.682 p95=1.898 p99=2.996
                                 max=3.738 mean=0.908   ← 无 ~60s 样本（lost-wake 检查 PASS）
DEVICE_QUOTA residence（n=376）：p50=0.522 p95=8.105 max=32.737（与基线 p50=0.502/max=36.8 同量级）
PREFETCH_BUDGET residence（n=57）：p50=4.393 p90=18.390 max=44.415（基线 p50=1.176/max=43.1 → 变差）
FRONTIER residence（n=45）：p50=0.527 max=0.637
park 后主路径：43 rid 72 次 park → 8 full-hit restore（18.6%）/ 32 partial（74.4%）/ 3 miss
park 唤醒机制：72 次 park 中 67 次由 per-pass predicate（restore_retry cause=capacity）唤醒、
               5 次显式 frontier_wake（ACK/T12）
recompute cause=timeout 的 3 rid：2 个（261c1e4f/2508a849）含 4–5 次 BP park，timeout 为总
   WAIT 时钟（首入 DEVICE_QUOTA 时上弦，DQ+PB+BP 累计 >60s）——非 park 孤儿；0 rid 以
   BACKUP_PENDING 状态收尾
```

**观测项**：
- 落盘碎片：本轮无探针（e3 探针已还原），per-batch pread 分布不可测；syscall 级 1.9MB/次与
  批结构吻合，M4F 探针值（preads/批 p50=2、p90=3）保持。
- Host copy/scatter 线性：无 kv_batch 探针，不可测；整链 fast 组 min=0.53s 与 M4F min=0.563s
  一致（设备路径未退化）。
- 写入侧：syscw Δ=+21,891（基线 +28,152），write_bytes Δ=+103.1GB（基线 93.2GB）；
  backuped 1,555,721（基线 1,812,950）；storage_hit prefill tokens 348,342（基线 297,790）；
  dropped kv 158,095（基线 160,885）。

**根因代码核查（lost-wake race，协调者点 1）**：
- 注册侧 `register_frontier_waiter`（unified_radix_cache.py:2707）：去旧注册 → 入
  `_storage_frontier_waiters[anchor]` → **discard ready 标记** → 自触发
  `write_backup_storage(anchor)`。
- 唤醒双通道：T12 ACK（`_wake_frontier_waiters` → scheduler step3 `pop_frontier_ready`）；
  **T11 per-pass predicate（scheduler.py step4）**：BACKUP_PENDING 分支
  `_restore_wait_capacity_fits` = `not chain_backup_in_flight(anchor)`，每个调度 pass 对
  waiting_queue 全部 WAIT_CAPACITY 请求重读；`capacity_wake_applies` 含 BACKUP_PENDING
  （hicache_restore.py:326-332）。
- **double-check 成立**：即使注册晚于 drain（register→discard ready→该 ACK 已过、无新 ACK），
  per-pass predicate 在备份排空后下一 pass 翻转 → wake。孤儿 60s 条件（anchor=None /
  capacity_wake_applies=False / 不在 waiting_queue）逐一排除：park 注册仅当
  `last_host_node is not None`（scheduler.py:3109-3116），WAIT 期间该字段只读不写（grep 仅
  2877/2889 局部变量读取）；数据侧 0 个 ~60s residence、0 个 BP 收尾 rid。
- 结论：**lost-wake race 不存在（代码语义 + 数据双侧 PASS）**；3 个 T13 timeout 是总时钟
  （含 DQ/PB）触顶，属设计内兜底。

## 4. summary

- **判据逐条**：① lookup/rid ≤2–3：**FAIL**（p50=4 / p95=9 / max=38，基线 3/34/37——p95 改善
  但 p50 与 max 未动）；② 重试等待 p90 → 秒级：**FAIL**（16.2s vs 15.7s，尾未消）；③ 整链
  p50<1.0s：**FAIL**（3.199s，p90=47.9s 较基线 3.9s 恶化 12×）；④ cause=miss 备份在途样本消失：
  **FAIL**（453→389，-14%；partial-IO rid 占比 81.5%）；⑤ 0 崩溃/0 OOM/守恒：**PASS**；
  ⑥ 五门：a FAIL / b 不可测（M4F 1.0000 保持）/ c PASS / d PASS（口径内）/ e PASS；
  ⑦ 观察项：记录（syscall 级稳定；探针级不可测）。
- **CLOSED 判定**：**未达成**（p50 0.8–0.9s / p90-p95 1–2s / lookup ≤2–3 / partial 消失 /
  五门 5/5 均不满足）。**T15 机制本身正确**（park 快醒、无孤儿、守恒、双通道唤醒在位），
  但两个结构性缺口使其净效果为负：
  1. **park 判据过粗**（R1）：`backup_wait_applies` 只看"链上有在途写"，而缺失尾常不在该写
     span 内（写提交后链增长 / dropped-without-backup 25 次 / 尾页未入写源）→ wake 后
     re-lookup 仍 partial（实证：72 次 park 后仅 18.6% full-hit，60 次 PARTIAL shortfall）。
  2. **wake 后 re-issue 撞 prefetch rate limit**（R2）：预算 = 0.5×host pool ≈ 21,392 tokens
     ≈ 单条整链 prefetch（20,910）——多请求 park 同醒突发 re-issue → 57 次 denied_rate_limit
     → PREFETCH_BUDGET 等待 p90=18.4s/max=44.4s，成为新尾延迟主项。
  净效果：基线 2–5s 的部分恢复路径（34/55）在 e4 中退化为 15–70s 的
  park→rate-limit→re-park 循环（13/44 ≥15s，基线 1/55）。
- 工作量等价性已核：两轮同为 96 请求 / 24 restore turns / 8 agents，ttft 分布同量级
  （restore p50 46.9s vs 37.8s），storage 需求指标同平台（prefetched 678,695 vs 671,310）。

## 5. followups

1. **R1 修复（coder，P0）**：`backup_wait_applies` / `chain_backup_in_flight` 应判定"缺失
   span 是否被在途写覆盖"，而非"链上任意在途写"——需在途写 span 与
   [hit_count..requested) 求交；无覆盖则不 park（现行部分恢复/重算）。预期 park 命中率
   18.6% → 主路径，且消除无效 park 引入的 latency。
2. **R2 修复（coder，P0）**：wake 后 re-lookup 应绕过/豁免 prefetch rate limit（wake 是
   事件驱动的一次性 re-lookup，不是投机 prefetch；或按 rid 记账预算独占）；否则
   PREFETCH_BUDGET 等待（p90=18.4s）吃掉 T15 全部收益。
3. **验证再测（tester，修复后）**：M4T 同配置重跑，判据不变；附加检查 park→full-hit 占比
   应 >70%。
4. **a1-t5-restore 第三 sha16 值（f6b66de0）**：落入已知多模态家族（M4F/基线/e4 三值），
   无损坏签名；如用户要定论，定向单链对照（restore-served vs fresh-serve ×3，A' 构造）——
   e3 followup 2 仍挂账。
5. 读放大本轮不可测（页缓存温）：如需本判据实测值，下轮 restore 前 fadvise(DONTNEED) 冷盘
   或探针（M4F 口径 1.0000 保持）。
6. 证据路径：e4 run-20260901-015701；分析脚本 /tmp/p2io-e4/。

## 6. open_issues

- 单轮实验（每轮 ~12 min driver）；判据 FAIL 幅度大（p90 12× 恶化）且机制完全解释，结论
  稳健；如需统计置信可复跑一轮确认。
- 3090 部署树保持 e8 态（9 文件 md5 双侧一致），未做任何修改；实验脚本 /root/p2io-m4t-e4-run.sh
  留存（与基线同名文件不冲突）。
- lost-wake race 的"注册即 discard ready 标记"语义依赖 per-pass predicate 兜底——predicate
  每 pass 重读 ongoing_backup，性能成本（锁内遍历）未量化；若后续 pass 频率下降需重审。
- extent 文件仍为 64GiB 循环（du 64G 实块）；/data 51.3GB 余量，无 ENOSPC 风险。

## 7. 基线一致性核查（追加，协调者质疑 M4F 1.32s vs M4T 2.81s 漂移 >2×）

### 7.1 结论先行

**漂移主因 = 指标口径不一致，非 workload 漂移**：e3 §12.2 的 M4F 1.32s 是 finish-matched
口径（每次 io_finished 匹配其**末次** prefetch_issued = 完成尝试窗口）；本报告 §3/§4 引用的
M4T "2.806s" 是 issued-matched 口径（每次 issued 匹配其后**首次** finish = 整段重试周期，
含所有等待）。同一分析器统一口径后，三轮整链 p50 全部落在 1.0–1.3s，**不存在 >2× 漂移**。

### 7.2 逐项对比（真实数据）

**① workload 完全相同**：`diff /root/p2io-m4f-run.sh /root/p2io-m4t-run.sh` 仅输出命名差异
（M4F/M4T 字样），配置逐字节同（host 5G / K=8 / 96 请求 / extent v1 / wait_complete）；
同一 /root/p2-0/agent_driver.py（两轮间无同步）；三轮 verdict 均 96 请求 0 失败、
24 restore turns / 8 agents；**prefetch_length 分布三轮完全一致**
（p50=11858 / p90=34812 / p95=max=43513，M4F 188/487 大span 38.6%、M4T 163/544 30.0%、
e4 191/529 36.1%）；payload 家族相同（b1c-S1-L0..L3 V1-V3），单 agent 回合组合微差
（M4F agent-1 用 9 个 payload 文件 vs M4T/e4 8 个）= driver 自适应 downgrade 注入时机差
（downgraded 5/4/3），非配置差异。

**② restore state size / 授予分布**：finish n_tokens —— M4F n=100 p50=7752（≥20k: 20）、
M4T n=91 p50=6144（≥20k: 11）、e4 n=68 p50=12237（≥20k: 17）。span 相同、授予构成
有轮间方差（M4T 大授予偏少），同负载内正常散布。

**③ backup overlap**：单写者饱和 —— 三轮 30s 桶写速率曲线近同形：
M4F 110–252MB/s（全程 ~190）、M4T 116–253（~192）、e4 136–237（~183），均全程持续
饱和（设备限速），备份队列三轮都恒深；读突发均集中前 150s。**overlap 无差异**。

**④ 冷/热度**：M4F **读侧最冷**（物理 read_bytes Δ=+18.9GB vs M4T +8.8GB vs e4 +12.1GB，
M4T 在 M4F 后 18min 起跑吃到页缓存余温）；/data 三轮稳定 51–48GB 余量；L3 命中行为：
revoke 中 storage_hit>0 占比 M4F 2.6% / M4T 2.4% / e4 23.6%（e4 因 T15 部分命中分类天然
抬高）。**冷热度差异方向与"漂移"相反**（M4F 最冷反而报告最快）——不构成 1.32 vs 2.81 的解释。

**⑤ 漂移来源 = 口径 + 残余方差**：
- 统一口径复算（/tmp/p2io-e4/metric_compare.py，同一定义跑三轮日志）：
  - **定义 B（finish-matched，完成尝试窗口）**：整链 ≥20k p50 —— **M4F=1.320s（n=20，
    与 e3 §12.2 报告 1.320/1.482/1.844 完全复现）、M4T=1.051s（n=11）、e4=1.236s（n=17）**。
  - **定义 A（issued-matched，整段重试周期）**：p50 —— M4F=4.900s（n=56）、M4T=2.855s
    （n=46）、e4=3.199s（n=43）。
- 即：1.32 vs 2.81 是**跨口径比较**（B vs A）；同口径下轮间差 B 仅 1.05–1.32s（~1.26×），
  A 为 2.86–4.90s（~1.7×，M4F 反而更慢——冷读 + 队列时序残余，非配置差异）。
- 插桩成本：M4F 3,223 行 V1_READ/WRITE_PROBE（后端 per-pread）；M4T 2,037 行
  kv_batch/sidecar/restore_io_start（prefetch 路径 per-batch 2 行）——两侧都有探针且
  M4T 的探针位于关键路径，但 B 口径下 M4T 反而快（1.05 vs 1.32），探针成本不构成解释。

**⑥ 结论与对齐动作**：
- **基线采用定义 B（finish-matched）作为判据口径**：与 e3 §12.2（1.32s）及 coder e8 的
  "1.32→0.9s" 目标推导一致；报告同时给出 A（周期开销）。M4F 与 M4T 在 B 下均为有效基线
  （1.05–1.32s，取 M4T 作同脚本基线、M4F 作终裁参照）。
- 本报告 §3/§4 修正：M4T baseline 整链应记 **B: 1.051s（n=11）/ A: 2.855s（n=46）**，
  原 "2.806s n=55" 为 A 口径下的近似值（含一 rid-末次 finish 计数的实现差异）。
- **T15 结论不变且更锐利**：B 口径 e4=1.236s（vs M4T 1.051，未改善 +0.19s）；A 口径
  e4 p90=47.9s（vs M4T 3.3s，周期恶化 14×）+ partial-IO 81.5% + lookup p50=4 —— FAIL 判据
  全部成立，与口径无关。
