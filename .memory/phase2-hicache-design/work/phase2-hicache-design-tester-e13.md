# phase2-hicache-design-tester-e13 — P2-1 最终复测（60s 时钟修复）

## status
done（K=1 回归 + K=8 同链对照 + CHAIN_GAP 补测全部完成；判据全绿；四代对照 recompute 持续
下降至 130K（↓93% vs P2-0a）；**遗留：K=1 t5 仍 60s（时钟修复部分生效）+ K=8 窗口含 74
失败请求（协调人侧截断）**——见 followups）

## 部署确认
hicache_restore.py **2bc86bbd** / scheduler.py **f58517a3**（双侧 md5 匹配 ✓）；L3 **复用
/data/l3/p2b0-0c（15G/260K 文件预热链）**——与 1c 同链条件；证据归 /root/evidence-p2b0-1e/

## 1. K=1 基线
- 12/12 完成，**elapsed 148s**（vs 上轮 220s——改善但未达 20-55s 预期）
- wall 分布：t8/t12 restore 2.0/2.2s（**时钟修复生效 ✓**），t5 restore 仍 60.97s（残留偶发），
  t1/t2/t6/t7/t10 15-18s（正常 prefill）
- HEALTH_CHECK 不阻塞维持 ✓、restore_retry cause=capacity=0 维持 ✓（全程 retry 仅 1 次）

## 2. K=8 主判据（同链 0c；引擎 18:10:48 协调人侧 SIGTERM 截断——我的 timebox kill 因 ssh
连接延迟与截断竞态未达；96 请求中 22 成功 + 74 failed 为截断后请求）
**四代对照表（P2-0a / 1c / 1d / 1e）**：
| 判据 | P2-0a | 1c（同链）| 1d（fresh）| 1e（同链+时钟修复）|
|---|---|---|---|---|
| recompute_served_tokens | 1,866,880 | 365,040 | 653,873 | **130,204**（↓93% vs P2-0a，↓64% vs 1c）|
| restore_served_tokens | 0 | 224,276 | 4,096 | **194,607**（↑ 47× vs 1d，同链条件 ≈1c）|
| turns/s | 0.175 | 0.166 | 0.170 | 0.111（窗口含 74 失败段拉低）|
| p95_round_interval | 52.8s | 106.4s | 67.6s | 121.6s（含失败段，参考值）|
| l3_to_h_wait | missing | 13.8s | 7.9s | **8.5s** |

**recompute 构成（timeout/too_short/miss）**：restore_recompute 18 = **miss 2（真 miss 大幅
下降，同链）** + **timeout 12** + **too_short 4（首次出现 ✓ 放行观测）**
- timeout 12 未趋 0：K=1 t5 的 60s 残留同源（时钟复位残余路径）——1e 全程 wait 6 次仅 5 次
  wake（1 次 wait 未 wake → 60s 超时即 t5）
- **frontier_wake 5 次**（wait 6→wake 5 配对；K=1 小节点 ms 级、K=8 5-7s）
- restore_ready 27 次（同链恢复量大）
- disposition：PARTIAL 23（shortfall）+ RECOMPUTE 44（too_short 21、denied_rate_limit 16、
  hybrid_discard 4、revoked:alloc_failed 1、revoked:miss 2）——**denied_rate_limit 16 稳定
  出现**（配额门）
- prefetch：issued 31 → io_finished 28 → finalize 27 → revoke 3（同链命中率高，revoke 极少）

## 3. CHAIN_GAP 补测（chain_check.py 直读 0c，引擎外）
- **verdict=CHAIN_GAP 达标形态**：earliest_stored_index=**0**、无内部 hole、
  **missing_count=46（尾缺口 [20864..20909] = 46 页，恰好 ≤46 允许）**、链 [0,20863] 连续
  （20864 页）
- 对比 e8 的 558 页尾缺：多轮 write_back 推进 frontier 至 20864，尾缺收敛到 46 页验收线

## 4. 判据
签名 0 ✓（OOM/KeyError/RecursionError/SchedulerException 全 0）；SIGTERM 优雅退场 ✓
（18:10:48 destroy_process_group → 18:10:52 kill_process_tree）；进程 0 残留 ✓；
GPU 18975→15 MiB ✓；CHAIN_GAP ✓（见上）

## 交付物（/root/evidence-p2b0-1e/，461 文件，MD5SUMS 校验 OK）
- p2a-lines.txt（399 行）、state-machine.txt（84 行）、restore-disposition.txt（67 行）、
  chain-check-1e.json
- k1/run-20260830-180427（join 12 行）、run-20260830-180715（join 96 行 + metric-table
  json/csv + events-table + mid-run 快照）
- k1-driver.log / k8-driver.log、MD5SUMS、engine log /root/engine-p2b0-1e.log

## followups
1. **t5 的 60s 残留**：K=1 第一个 restore 的 wait 未 wake（1/6 wait 未配对）→ 60s 时钟兜底；
   timeout 12 与此同源——需确认该 wait 为何未 wake（frontier_anchor_ready 谓词对该节点
   未满足？）
2. K=8 的 74 failed（协调人侧截断后请求）污染 turns/s 与 p95——下轮完整 run（K=16/32 批次
   或 P2-1 收尾）用完整窗口对照
3. denied_rate_limit 16 次稳定出现（配额门）——M1a/M1b 增量计费与配额交互的归因输入
   （p2-0-10）
4. revoked:alloc_failed 1 次（L3 命中但 H→D alloc 失败）——新形态，量小
5. 四代对照结论：recompute 1.87M→130K（↓93%）+ restore 0→195K 为 P2-1 核心成果；
   p95/turns 的最终判读需无截断完整 run

## open_issues
- CHAIN_GAP 尾缺 46 页 = 验收线边缘（≤46 允许）——frontier 推进到 20864 后稳定；
  若后续 run 再写应继续推进或保持 46 页平衡态
- K=1 的 148s vs 20-55s 预期差距 = t5 单点 60s——修复范围外残余，优先级低于 wake 配对
