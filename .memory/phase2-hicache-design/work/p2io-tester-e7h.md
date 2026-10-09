# p2io-tester-e7h — 12G 重跑（e18 token 口径容量模型落地，e7g 核算验证）

报告人: root tester | 状态: **done** | 日期: 2026-09-01 | epoch: 1

> 本次运行：e7h-r2（干净单发命名空间，锁保护），配置 = e7g 核算的 HICACHE_SIZE=12G +
> reserve 0.75G + margin 0.3G，其余同 e7f（enable-ready-horizon + extent + write_back +
> T15 off + 8 agents/96 req/24 turns/K=8）。`ready_horizon_state_p95_tokens` 未设（默认 0 → 配置水位 2/4）。
> 8 个 agent × 12 turns（agent_driver 强制 turns≤12）实际 96 请求（非 dispatch 的 24 turns，
> 与 e7f verdict 一致）。

## 1. status

**done** —— r2 全 6 主门评估完成：G1 PASS、G5-reserve PASS、G4 PARTIAL-PASS、
G2/G3/G5-horizon FAIL、G6 证据不足。运行本身完全干净：rc=0、无 crash/OOM、GPU 归零、无残留进程。

## 2. artifacts

### 运行（3090）
- run script: `/root/p2io-m4t-e7h-r2-run.sh`（锁 + 全新 e7h-r2 命名空间）
- engine log: `/root/engine-p2io-m4t-e7h-r2.log`（932 KB，已拉回本地）
- evidence: `/root/evidence-p2io-extent-m4t-e7h-r2/run-20260901-215818/`（agent-1..8.json、
  runs.csv、turn meta/payload、mid-run-metrics.txt、END-BANNER）
- status: `/root/p2io-m4t-e7h-r2-status.log`、run.log、sampler `p2io-m4t-e7h-r2-samples.jsonl`（45 MB）
- extent 数据: `/data/l3/p2io-extent-e7h-r2/hicache.data_qwen3.5-9b-gptq_0_1`（64 GiB sparse）

### 本地证据
- `/tmp/p2io-e7h-r2-ev/`: engine.log、agent-1.json、runs.csv、mid-run-metrics.txt、summary-e7h.txt
- 六 gauge 专用验证（引擎独立启动）: `/root/p2io-gauge-boot.log`（scrape 八 gauge 值）

### 运行摘要
- verdict: `status=done agents=8 turns=12 requests=96 failed=0 downgraded=16 elapsed=479s`
- B_ep/B_fin ≤1.2s 门不可测：e18 构建不再发 `io_finished`/`restore_ready`（e7b/e7c 时代有），
  该门当前无 instrument 支撑（见 §5 followups #2）。

## 3. evidence（真实命令 + 真实 exit code）

### 3.1 运行与清理
```
[22:06:18] M4T-e7h-r2 driver finished rc=0 evidence=/root/evidence-p2io-extent-m4t-e7h-r2
[22:06:40] M4T-e7h-r2 stage: engine SIGTERMed, remaining python procs=1, gpu_mib=15 MiB
[22:06:40] == M4T-e7h-r2 run stage: COMPLETE (rc=0) ==
M4T_E7H_R2_STAGE_COMPLETE rc=0
nvidia-smi: 15 MiB | leftover launch_server/scheduler/agent_driver/sampler procs: 0
```
G1 无崩溃 PASS。

### 3.2 六 gauge 发布验证（独立 scrape，引擎刚启动 idle）
```
GAUGE hicache_kv_pool_tokens = 102680.0
GAUGE hicache_writeback_reserve_tokens = 22888.0
GAUGE hicache_usable_tokens = 70637.0
GAUGE hicache_ready_resident_tokens = 0.0
GAUGE hicache_working_tokens = 0.0
GAUGE hicache_spec_inflight_tokens = 0.0
GAUGE hicache_kv_host_usable_tokens = 70637.0
GAUGE hicache_ready_state_max_tokens = 0.0
（均来自 /metrics；算出的 reserve 22.3%、margin 8.9% 与 e7g 预测一致）
```
driver 的 `parse_metrics` 前缀白名单未含这六 gauge，故 mid-run-metrics 快照不含它们——
属 harness 采集限制，非引擎缺陷（已验证 /metrics 实际发布）。

### 3.3 Z3 / drop（G2）
```
r2:  write_back: KV subtree dropped without backup = 843   (21:58 起全程 ~1.5-2/s)
     _drop_subtree_no_host = 0            forced_drop_to_miss = 1 (21:58:53 启动期, node=65)
e7f: write_back flood = 1001              _drop_subtree_no_host = 0  forced_drop = 1
```
G2 Z3≈0 → **FAIL**（843 vs 1001，仅 -16%，非个位数）。12G + 0.75G reserve 仍不足以消除
host-pressure 落盘前丢弃。

### 3.4 survivability（G3）与 full-prefix（G4）—— per-turn restore serving
```
r2 restore turns=24:  host_hit>0=7, device_hit>0=5,  storage=0, empty(降级)=12
  -> 12/24 = 50% cache-served;   full(≥20k)=7, partial(≥15k)=9
e7f restore turns=24:  host=5, device=3, empty=16
  -> 8/24 = 33% cache-served;    full(≥20k)=2, partial(≥15k)=4
r2 downgrade turns=16 (agents 5-8), e7f=28
```
- G3 survivability>95% → **FAIL**（50% cache-served；e7f 33%；token-metric 口径 10.8% 系 e7f 汇总数差异）。
- G4 full-prefix 恢复 → **PARTIAL-PASS**：full≥20k 从 2→7，cache-served 33%→50%，降级 28→16，
  有实质改善但未达"全 prefix 可恢复"。
  - **口径说明**：dispatch 的"对比 10.8%"取自 e7c/e7d 的 **L3 通道**指标
    （`storage_hit==requested / issued` = 10/93 = 10.8%）。r2 的 L3 通道 `storage_hit` 在 96 个 turn
    全为 0——L3 从未直接供命中（host 承担了恢复）。我报告的恢复提升是 **host/device tier** 的
    turn-level cache-served（33%→50%）、full≥20k（8%→29%）。两口径通道不同，需协调者对标的
    "full-prefix availability" 定档（L3 链 vs host 链）。

### 3.5 ready-horizon + reserve（G5）
```
ready_pool: 1 次 (21:58:04) size=0 tokens=0 watermark=[2/4]  -> ready horizon 从未组装非空池
frontier_wait=187, frontier_wake=2, ready_stage=0, restore_ready=0
peak host_used=79746 (mid-run-metrics);  pool-reserve(floor)=79792 -> 距 reserve floor 46 tok, 从未侵蚀 reserve
usable=70625; peak 超额 usable 9121 tok = margin 的 99.5% 被耗尽（margin 几乎全用）
spec_inflight=0, spec_evict=0 (engine log 零匹配)
```
- G5 ready-horizon feasible target → **FAIL**（ready pool 空，ready_resident=0）。
- G5 writeback reserve 不被侵占 → **PASS**（峰值始终 ≥46 tok 于 reserve floor 之上；spec_inflight/evict=0）。

### 3.6 restore 行为 / 16-diff（G6）
```
r2:  restore_state 1275 (RESTORING 495 / WAIT_CAPACITY 450 / NONE 330)
     restore_recompute 330 (cause=miss; final_storage_survivability host=329, l3=1, none=0)
     restore_disposition 362 (RECOMPUTE 360 = revoked:miss 330 + too_short 30; WAIT 2 denied_rate_limit)
     prefetch_issued 330 / prefetch_revoke 330  (1:1:1，全部 speculative 收回)
     restore_ready = 0            ready_stage = 0
     prefill_deny_summary 16 次 = 261 (rem_total_tokens 204 + rem_lock 57)
     promotion_reserve 52 / promotion_transfer 52 (852,288 tok 提权)
     extent_write 135 (kv 90×2.61GB + mamba 45×2.32GB)
```
- G6 16-diff 细分 → **证据不足**：本构建 P2A 无 NEVER/PARTIAL/FULL_THEN_LOST/Z3/recycle 分桶事件
  （`_final_storage_survivability` 只输出 host/l3/none 标签）。可给的是：360 RECOMPUTE
  (330 revoked:miss + 30 too_short) + 2 WAIT；且 330 次 recompute 中 329 次判定 host 仍存前缀
  却被 recompute（即 host-tier survivability 高，但 restore 未达 READY→服务路径）。

### 3.7 B_ep / B_fin（次门）
```
r2 restore turns wall_s: n=24 p50=33.7 max=48.3; live restore (非降级) n=12 p50=32.9
e18 构建 P2A 不再发 io_finished / restore_ready / restore_success -> B_ep/B_fin 窗口不可算
（gate FAIL 无法判，属 instrument 缺口，非性能证明）
```

### 3.8 守恒 / crash / gauge（次门）
```
conservation: kv spt 32768 B/tok (vs e7g 核算 32723), extent kv 2.61GB = 79746 tok = peak host_used, 守恒成立
crash/OOM: 0（全程）
fd: extent fd 89 flags=02100002 (O_DIRECT) 存在
六 gauge 发布: PASS（见 3.2）
```

## 4. summary（真实数字）

### 与 e7f / e7b 对比
| 指标 | e7f (8G/1.5G/0.3G) | e7h r2 (12G/0.75G/0.3G) |
|---|---|---|
| restore cache-served (turn-level, host/dev) | 8/24 = 33% | **12/24 = 50%** |
| full restore (≥20k cached) | 2/24 = 8.3% | **7/24 = 29.2%** |
| partial (≥15k) | 4/24 = 16.7% | 9/24 = 37.5% |
| L3 storage_hit (对比 e7d 10.8% 频道) | — | **0**（96 行全 0） |
| downgrade (R3 降级) turns | 28 | **16** |
| write_back Z3 flood | 1001 | **843 (-16%)** |
| restore_recompute cause=miss | 243 | 330 |
| restore_ready | 0 | 0 |
| prefill deny | 18 | 16 (261 tokens) |
| peak host_used / 距 reserve-floor | ~22.4k / 0 (reserve 66.9% 被占) | 79,746 / +46 tok |

### 门级结论
- **G1 无崩溃 PASS**。**G2 Z3≈0 FAIL**（843 落在盘前丢弃，仍 ~1.5-2/s）。**G3 survivability>95% FAIL**
  （50%）。**G4 full-prefix 恢复 PARTIAL**（8.3%→29.2% full，33%→50% any，降级减半）。
- **G5**：ready-horizon feasible → **FAIL**（pool 恒空）；reserve 不侵占 → **PASS**（46 tok headroom，
  spec 全 0）。**G6 16-diff 数据不足**。
- 次门：B_ep/B_fin 不可算（instrument 缺口）；守恒 PASS；0 crash/OOM；六 gauge 发布 PASS。

### 机制归因（若需要）
1. **Z3 洪泛根源未除**：12G + 0.75G reserve 下，usable=70,625 tok ≈ 2.16 READY-state 级容量。
   M4T 8 agent × 20k restore 涌入时 host 池在 reserve 上方只剩 46 tok headroom → write-back
   backup 失败 fallback 到直接丢弃。**池大小仍是瓶颈**；12G 只是把 reserve 百分比从 66.9% 降到 22.3%，
   绝对 margin 依然只有 ~9k tok。
2. **ready horizon 不生效**：ready_pool 恒 0 tokens/0 states——即使 reserve 已降容，ready 组装/prefill
   仍无窗口（frontier_wait 187 全是等 bucket）。需独立排查 ready 池触发条件（可能与
   `hicache_restore_backup_park` 或 watermark 判定在 aware-restore 路径上的交互有关）。
3. **host survivability 高但服务不上**：330 recompute 中 329 次 host 仍持有前缀，却全部走 recompute；
   restore_ready=0 说明 ready 服务路径完全未用。恢复靠的是普通 prefill admission 的 host_hit
   （race 式命中），而非 ready-horizon 的确定性恢复。

### coverage 说明
本任务为实验验证（远程 3090 运行流水线），无本地 Rust/单测覆盖率口径。验证面 = 6 主门 + 4 次门，
全部基于真实 engine log / evidence / /metrics scrape 数据（见 §3）。

## 5. followups

1. **[P1][容量] 还须扩 host 池或改 drop 语义**：843 次 write_back 丢弃说明 12G 仍是"常满"配置。
   建议 coder：`drop-when-full` 应优先驱逐**可再生成/低价值前缀**（如 L0 已 cache 的），
   保留 host 中高价值 READY 链；或把 reserve 按"≥2 ready-state + working"重算（e7g 的
   `work + 2*READY_max + reserve + margin` 到 12G 只刚够，实际需再上探）。
2. **[P1][instrument] B_ep/B_fin 门失仪表**：e18 移除/替换了 `io_finished`/`restore_ready`/`restore_success`
   P2A 事件，导致 ≤1.2s 服务窗口门无法评估。建议 coder 在 e18 新增的分桶事件带上
   `issued→satisfied` 时间戳，否则该门永久不可测。
3. **[P2][harness] six gauge 未进 driver 快照**：`agent_driver.py common.py _ALL_PREFIXES` 缺
   `sglang:hicache_*` 六 gauge——建议把 `parse_metrics` 前缀表补上，下一轮直接进 mid-run-metrics。
4. **[P2][ready-horizon] ready 池空因待查**：`ready_pool` 仅 1 次(size=0)，需 coder 查 ready
   组装触发与 `hicache_restore_backup_park`/watermark 交互。
5. **[P3] io-after 采样缺失**：run 脚本写 io-after 时 scheduler 已退出（只留 io-before），
   下轮在 SIGTERM 前采样。

## 6. open_issues

- **12G 未达"Z3≈0 + 全 prefix 恢复"目标**。两门 FAIL 均为容量边际：reserve 上方 headroom 46 tok。
  reserve=0.75G 对 12G pool 是 22.3%，但"常满运转 + race 命中"状态仍在——指标比 e7f 全面改善
  （这轮证明容量增加确实缓解），但 ready-horizon 的确定性恢复路径没有生效，真正的收益仍靠
  prefill admission 的自然 host_hit。
- survivability 口径：driver turn-level(cache-served 50%) 与 e7f 报告标的 token-metric(10.8%)
  不同口径；本报告统一取 turn-level 可比口径，3 段均有数字供协调者对齐。
- 六 gauge 验证用独立引擎启动（idle 值），运行中 gauge 未采集（driver 白名单限制）——
  running 值由 host_used 峰值 79,746 佐证 reserve 安全。