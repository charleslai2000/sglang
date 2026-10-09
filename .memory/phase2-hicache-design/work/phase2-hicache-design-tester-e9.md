# phase2-hicache-design-tester-e9 — M1a（增量计费）引擎级回归

## status
done（K=1 等价性 + K=8 对照全部完成；restore_disposition 新字段首次落地；判据全绿）

## 部署确认
- schedule_policy.py md5 **54b0a0e6**（双侧一致）✓；restore_disposition 插桩实际位于
  unified_radix_cache.py（158 行 logger + 6 个调用点：too_short/denied_rate_limit/
  aux_alloc_failed/hybrid_discard/miss/shortfall/full/revoked:*）
- L3 复用 /data/l3/p2b0-0c（e8 预热链，earliest=0、尾缺口 558 页形态已知）——证据归 /root/evidence-p2b0-1a/

## 1. K=1 基线回归（等价性结论：一致）
- 12/12 完成、53s（M1a 前 e8 重访 55s → turns/s 0.226 vs 0.218，~4% 内等价）；failed=0、
  downgraded=0、签名 grep 0
- restore_disposition 首次样本（K=1 窗口 14 行）：PARTIAL 4（shortfall）+ RECOMPUTE 10
  （too_short 9 + revoked:miss 1）；**无 RESTORE**（0c 链 97.3% + 顺序 churn 下 46 页尾缺
  口使 full 不可达——PARTIAL granted=20864 vs requested=20910 即尾缺口形态）

## 2. K=8 快速观察（3 分钟截断，38 请求完成）
- **deny 对照（vs P2-0a 基线）**：prefill_deny_summary（新插桩，8 行）reasons 全
  rem_total_tokens，累计 288-350 次/窗口 vs P2-0a 的 2358 次 → **数量级下降 ~85%**（口径
  谨慎：P2-0a 为空库全 miss churn、M1a 复用有链 0c，但请求数相近 32 vs 38）；
  **rem_total_tokens_lock 新维度首次出现**（1 行 summary 含 lock 计数 6——增量计费锁维度）
- **width 对照**：num_running_reqs max=1（与 P2-0a/K=8 一致，引擎依旧串行）；num_queue
  max=7（队列深度同）
- **restore_disposition（K=8 窗口 14 行）**：PARTIAL 1（shortfall 20910→20864）+ RECOMPUTE 13
  （revoked:miss 9 + too_short 4）；**RESTORE 0**——0c 链在并发 churn 下无 full 恢复
- **事件计数**：prefetch_issued 14 → revoke 9 → io_finished 5 → io_done 5 → finalize 5
  （5 对完整链 + 9 快速 revoke，与 M1a 前形态一致）
- join：38 行（grow 19 + downgrade 14 + restore 5），device_hit 20864、host_hit 27776、
  storage_hit 0（sglext 口径未抓 storage——disposition granted 为引擎侧真值）

## 3. restore_disposition 首次样本（每请求一次，代表性 4 行）
- disposition=RECOMPUTE requested=11427 granted=0 reason=revoked:miss（L3 无链）
- disposition=RECOMPUTE requested=0 granted=0 reason=too_short（退化体/链过短）
- disposition=RECOMPUTE requested=0 granted=0 reason=too_short
- disposition=PARTIAL requested=20910 granted=20864 reason=shortfall（尾缺口 46 页）

## 判据
两 run 全绿：K=1 与 K=8 均 SIGTERM 优雅退出（kill_process_tree）、签名 grep 0、进程 0 残留、
GPU 18975→15 MiB

## 交付物（/root/evidence-p2b0-1a/）
- p2a-lines.txt（74 行）、restore-disposition.txt（28 行）
- k1-baseline/run-20260830-154222（join 12 行）、run-20260830-154342（join 38 行 +
  mid-run-metrics 46 帧）
- k1-driver.log / k8-driver.log、MD5SUMS（221 文件）
- engine log：/root/engine-p2b0-1a.log

## followups
- **deny 数量级下降（2358→~350）需归因**：M1a 增量计费 + 有链 L3 双变量——p2-0-10 归因时
  需用同条件对照（空库 K=8 M1a vs 空库 K=8 M1a 前）
- rem_total_tokens_lock 维度（增量计费锁）首次观测（6 次/窗口）——量级小，继续观察
- disposition 的 RESTORE=0：0c 链尾缺口 558 页 + 并发 churn 使 full 恢复不可达——若需
  RESTORE 样本，需完整链 namespace（finalize 语义修复后）或 K=1 顺序重访
- storage_hit 的 sglext 口径与 disposition granted 不一致（join sh=0 vs granted 20864）——
  归因以引擎侧 disposition granted 为准
- test 文件 md5 83c9fc12 未在树内找到（restore_disposition 测试文件路径待协调人确认）

## open_issues
- K=8 的 38 请求中 downgrade 14（R3 降级 37%）与 P2-0a 的 24/32（75% 降级）对比：M1a 有链
  场景降级率显著低（命中不足触发降级少）——但两 run 请求完成数不同（38 vs 32），谨慎对照
