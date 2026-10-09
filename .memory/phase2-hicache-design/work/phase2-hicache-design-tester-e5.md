# phase2-hicache-design-tester-e5 — P2-0 子任务 08（实验批次 2）+ 紧急停止现场

## status
done（实验批次 2 完成 4 runs 全部 completed；按紧急指令已停引擎、保存现场、清理进程，等待 P2-0a 新任务）

## 紧急指令执行情况（四项）
1. 优雅停止：SIGTERM 引擎 PID 59748 → 6 轮询（18s）退出；engine-p2b0-02.log 尾 = uvicorn lifespan
   CancelledError（SIGTERM 正常路径）+ kill_process_tree，无崩溃堆栈；driver 本已全部自然退出（无残留）
2. 现场保存：evidence-p2b0-02 原样保留；4 个 run 全部 status=done（completed，verdict 齐全）；
   MD5SUMS 已补齐（4,741 文件）；run 状态标注见下
3. 进程清理：ps 确认 sglang.launch_server 残留 0、agent_driver.py 残留 0、
   torch compile worker 0（引擎 SIGTERM 连带清理）；GPU 19027 → 15 MiB（0%）
4. L3 写放大：/data/l3/p2b0-02 = 17G / 300,698 文件（run 1 期间从 0 写满 19G cap，之后
   eviction 回落到 17G；写放大观察：20G cap 下 K=16 run 1 单 run 写满）；/data 盘 62%

## 实验批次 2 实际执行结果（4 runs 全部 completed，非 partial）
| run | K | requests | failed | downgraded | elapsed_s | budget | status |
|---|---|---|---|---|---|---|---|
| run-20260830-112352 | 16 | 192 | 0 | 64 | 1241.9 | 5400 | done |
| run-20260830-114610 | 16 | 192 | 0 | 64 | 1248.6 | 5400 | done |
| run-20260830-120724 | 32 | 384 | 0 | 113 | 2369.4 | 7200 | done |
| run-20260830-124754 | 32 | 384 | 0 | 113 | 2366.6 | 7200 | done |

判据每 run 全绿：engine-p2b0-02.log 四类签名（OOM/KeyError/RecursionError/SchedulerException）grep = 0；
join.log 行数 = 请求数（192/192/384/384）；driver 进程 0 残留。chain_check：K=16/32 未开
--final-chain-check（设计如此）；存储尾部只读 chain 验证未做（引擎已停，L3 文件为 page 级 .bin，
无链索引，记录原因：读侧链校验需引擎进程配合，留 P2-0a）。

## 12 指标表摘要（collect_metrics.py 修复版，K=1/8 取自 evidence-p2b0-01，K=16/32 为本批次）
| 指标 | K=1 | K=8 | K=16 r1 | K=16 r2 | K=32 r1 | K=32 r2 |
|---|---|---|---|---|---|---|
| agent_turns_per_s | 0.655 | 0.175 | 0.1547 | 0.1539 | 0.1621 | 0.1623 |
| p95_round_interval_s | 3.51 | 52.84 | 121.99 | 122.86 | 236.13 | 235.34 |
| active_width | 1 | 1 | 1 | 1 | 1 | 2 |
| slot_refill_gap_s | 0.0 | 10.05 | 10.06 | 15.34 | 10.25 | 15.24 |
| restore_served_tokens | 3461 | 0 | 0 | 0 | 5117 | 10234 |
| recompute_served_tokens | 7650 | 1866880 | 4235744 | 4235744 | 8001422 | 8001806 |
| l3_to_h_wait_s | 0.731 | missing | missing | missing | 204.49 | 203.86 |
| h_to_d_wait_s | 0.0425 | 0.0479 | missing | missing | 0.0667 | 0.0667 |
| device_free_tokens | 1525 | 811 | 970 | 811 | 808 | 793 |
| device_evictable_tokens | 21504 | 17140 | 16909 | 16995 | 16809 | 16699 |
| device_locked_tokens | 0 | 0 | 0 | 0 | 0 | 0 |
| quota_denied_tokens | missing | missing | missing | missing | missing | missing |
| quota_compressed_ratio | 0.793 | 0.966 | missing | missing | 0.836 | 0.908 |

（K=16 两 run 的 recompute 相同 4,235,744 = 同负载同全 miss 行为；counter 口径经引擎日志
Prefill batch #new-token 验证一致）

## 重点观察结论
1. **active_width/串行性（P2-1 admission 核心输入）**：K=1/8/16/32-r1 全程 active_width=1
   （num_running_reqs max=1，引擎严格串行，32 agents 也排队）；K=32 run 2 首次出现
   active_width=2（偶发双并发）。p95 轮间隔随 K 线性放大（3.5→52.8→122→235s）=
   排队深度的直接度量。引擎 max-running-requests=8 但实际 batch 深度 1-2。
2. **B 类判定口径对齐（07 followup 49f35a23）**：K=32 的 30 个事件中 18 个 B 类里 13 个是
   "假 B"（E_r=A_r 完整恢复但 D_r=prompt_len-device_hit 口径差 → d_ok 失败）。根因：并发
   churn 下 device_hit 崩塌使 D_r 失真。**已修 metrics_schema.classify_event**（TDD：
   D_r 与 E_r 分裂 >tol 时以 E_r 为准；self-test 更新为 r-2→A + 新增 r-4 真 B 场景，
   13/13 字段 18/18 检查 GREEN）。**修复未部署远端/未重跑历史表**（紧急指令打断，留 P2-0a
   批次：部署 + 重跑 6 个 run 表 + 新旧分类对比）。
3. **R12a quota denied**：引擎 counter 仍未发射（4 runs 全 missing，D3 实证延续）；
   预算门控相关日志证据：K=32 的 11 条 "HiCache prefetch success"（completed 4480-6144、
   matched 3-1031、loaded 3449-5117）——matched 远小于 completed = L3 部分命中；
   无 prefetch dropped 行（无显式预算拒绝日志）。
4. **L3 写放大**：p2b0-02 从 0 写到 19G/333K 文件（K=16 run 1 内）→ eviction 回落 17G/300K；
   K=16 两 run 无 prefetch（host 锚点全失），K=32 有 11 次 prefetch 成功（部分恢复）；
   restore_served_tokens K=32 = 5117/10234（run 2 因 L3 数据累积翻倍）。
5. **32762 超限拒绝**：engine log 全程 30 行 "exceeds maximum"（= K=32 两 run 各 15 个
   L2/L3 请求 ×2；K=16 轨迹无 L2/L3（levels 仅 0/1），拒绝计数随 K 增长到 K=32 出现）。
6. **R11 locked**：K=16 两 run 248 快照 + K=32 两 run 各 ~473 快照 locked 恒 0、无负值。
7. **R3 降级**：downgraded K=16=64/192(33%)、K=32=113/384(29%)（命中不足→L0-V1 降级，
   wall 46-52s 全量 prefill）。

## 事件分类计数（窗口过滤后）
- K=16 r1/r2：各 0 事件（无 pa_lb_init、无 prefetch、无 restore 恢复）
- K=32 r1：18 事件 = A 4 + B 14 + C 0 + D 0；K=32 r2：12 事件 = A 2 + B 9 + C 0 + D 1
- 同一 rid 出现 2 次 pa_lb_init（两段恢复，第二段普遍 partial：6144/8192 等 75%）
- b15 探针：K=32 窗口 pa_evict 风暴（run 1 ~977 次/run 级，K=16 更高，详情见各 run metric-table.json aux.probe）

## evidence（关键命令与输出）
- 判据：`grep -cE "OutOfMemory|KeyError|RecursionError|SchedulerException" /root/engine-p2b0-02.log` = 0
- SIGTERM：`kill -TERM 59748` → 6 轮询退出；`nvidia-smi` 19027→15 MiB；`ps aux | grep -c "[s]glang.launch_server"` = 0
- MD5SUMS：`cd /root/evidence-p2b0-02 && find . -type f | sort | while read f; do md5sum "$f"; done > MD5SUMS`（4,741 行）
- L3：`du -sh /data/l3/p2b0-02` = 17G；`ls | wc -l` = 300,698；`df -h /data` = 62%
- 12 指标表：`python3 /root/p2-0/collect_metrics.py --run-dir <run> --engine-log /root/engine-p2b0-02.log --probe /tmp/b15-probe.log --out ... --out-csv ... --out-events ...`（4 runs 全成功）
- 引擎参数冻结逐项确认：--kv-cache-dtype bf16、--hicache-write-policy write_back、
  --hicache-storage-backend file、--hicache-storage-prefetch-policy wait_complete、
  --hicache-ratio 1.5、--max-total-tokens 32768、--max-running-requests 8、cap 20G/min_free 10G、
  page_size=1、hicache_host_memory_mode=cache、STORAGE_DIR=/data/l3/p2b0-02（launch 脚本已改
  + .bak-p2b0-02 备份）

## followups
- **B 类口径修正（classify_event + self-test）已本地完成待部署**：metrics_schema.py / collect_metrics.py
  改动在 /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/，未同步远端、未重跑 6 个 run 表
  （紧急指令暂停）；P2-0a 批次第一步：scp 双文件 → 远端 self-test → 重跑全部 run 表 → 新旧分类对比
- 引擎已停（SIGTERM）→ P2-0a 需重启（launch-l3-3090.sh，STORAGE_DIR=/data/l3/p2b0-02 现指向）
- K=16 轨迹无 L2/L3（03 设计按 K 选 payload 变体）→ K=16 的 32762 拒绝为 0；K=32 每 run 15 个
- L3 尾部只读 chain 验证未做（需引擎进程配合），P2-0a 若需可先启动引擎再做
- t38c 探针仍未启用（D 类频次 K=32 r2 仅 1 例，低频维持不启用）

## open_issues
- K=32 的 B 类 14+9 个中真 partial 占比（A_r < E_r）约 1/3，假 B（E_r=A_r）约 2/3——修正后
  分类对比待 P2-0a 输出
- K=32 run 2 的 active_width=2 首次突破串行——是否稳定复现需更多样本（P2-1 输入）
- L3 eviction 在 run 进行中的 du 竞态（扫描时文件被删）——文件数统计应在 run 后静态做
