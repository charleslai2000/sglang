# p2io-tester-e7 — P3 Ready Horizon v0 整链终裁验证（M4T 同配置）

## status
done

## artifacts
- 实验 run-20260901-094745（3090，driver rc=0）：
  - 引擎日志 `/tmp/p2io-e7/engine-p2io-m4t-e7.log`（5.4MB / 37876 行，含 [P3] 事件）
  - 证据 `/tmp/p2io-e7/evidence/`（agent-1..8.json / runs.csv / mid-run-metrics.txt）
  - fd/io 前后对照 `p2io-m4t-e7-fd-before/after.txt`、`-io-before/after.txt`
- 对比基线 e5：`/tmp/p2io-e5/engine-p2io-m4t-e5.log`（+ evidence）
- 分析工具：`3090-dev/metrics/metric_compare.py`（双口径）、`/tmp/p2io-e4/analyze_p2a.py`、`/tmp/p2io-e4/p3_analyze.py`、本会话内联解析脚本（事件流直析）

## evidence

### 0. 实验事实
- 96/96 turns 完成，0 failed，9 downgraded，全部 http 200；elapsed 668.3s（e5 642.1s——墙钟相当）
- 配置：HICACHE_SIZE=5，READY_HORIZON=1（frontier_n=8 / watermark_low=2 / high=4 / spec_fraction=0.6），`--hicache-restore-backup-park` 未传（T15 关）
- 清理：GPU 15 MiB、0 python 进程、dmesg OOM=0（3090 实测）

### 1. 双口径指标（metric_compare.py，e5 vs e7 同表）
```
===== e7 =====
conservation: issued=2852 == revoke=2654 + io_finished=198 -> True
lookup/rid: n_rids=92 p50=9 p95=70 max=1289
[B_fin per-finish] full>=20k: n=22 p50=1.176s p90=1.777s p95=1.796s max=3.294s
[main full>=20k] A_ep: n=5 p50=14.553s p90=22.611s p95=22.611s max=22.611s
[main full>=20k] B_ep: n=5 p50=1.382s p90=1.796s p95=1.796s max=1.796s
[main full>=20k] A-B:  n=5 p50=13.371s p90=21.910s p95=21.910s max=21.910s
[appendix all ep] A_ep: n=58 p50=6.079s p90=53.795s p95=68.405s max=146.969s
[appendix all ep] A-B:  n=58 p50=5.416s p90=53.700s p95=67.156s max=146.816s
[no_finish episodes] 55: 0ad03b2c(iss=1289), a8649371(iss=51), ...
[self-check] A-B<0 or B>A violations: 0

===== multi-run comparison (full-chain >=20k) =====
run      n_full   B_fin p50/p90    B_ep p50/p90     A_ep p50/p90          A-B p50/p90/p95/max   lookup p50/max cons
e5           15     1.158/1.720     1.146/1.402    34.415/41.632   32.495/40.279/41.867/41.867             3/35 True
e7           22     1.176/1.777     1.382/1.796    14.553/22.611   13.371/21.910/21.910/21.910           9/1289 True
```

### 2. ready_pool 统计（[P3]）
- ready_pool 事件 136 个：size 分布 `{0:68, 1:67, 2:1}`；`frac>=2 = 1/136 = 0.7%`；时间占比 `time>=2 = 0.0%`（watermark=[2,4] 稳态从未形成）
- ready_stage 事件 6703 个，73 个 rid；spin 表（issued>=30 共 21 rid）：
  - `0ad03b2c17ad` issued=1289 ready_stage=1288 finishes=0 —— 全部发生在 **9.04s** 内（≈143 次 issue/s）
  - `e4f681ed257d` ready_stage=1145（8.1s，≈141/s）但实际 issued=1 —— 1144 次被 scheduler 层静默 decline
  - `f6fc6793b93a` ready_stage=1005 / issued=1；`f7b063a645b7` ready_stage=860 / issued=3
  - 其余 17 个 issued 30–100 的轻量 spin
- 事件总流：restore_state=11016 / restore_disposition=7595 / restore_recompute=2660 / frontier_wait=50 / frontier_wake=26

### 3. WAIT 驻留（criterion 6）
```
e7  PREFETCH_BUDGET: n=4732 p50=0.007s p90=0.561s p95=0.997s max=18.181s
e5  PREFETCH_BUDGET: n=36   p50=1.300s p90=29.264s p95=39.006s max=52.395s
e7  DEVICE_QUOTA: n=509 p90=1.925s; FRONTIER: n=50 p90=0.549s
```

### 4. 正确性 / 系统
- 0 crash（日志仅启动期 libtorchcodec import 警告）；0 OOM（dmesg）；0 backup failure（0 "pwrite failed"/"pages failed"）
- sha16：确定性会话（S1/S2/S3/S8）42 个共同 tag，e5→e7 分歧 10 个；其中 **6 个 e7 值为全新家族**（从未出现在 m4f/m4t/e4/e5 任一 run）：a1-t1-grow(S1)、a1-t12-restore(S1)、a1-t5-restore(S1)、a3-t6-grow(S3)、a8-t11-grow(S8)、a8-t2-grow(S8)
  - a1-t1-grow 与 a1-t12-restore 在既往 4 run 全稳定（b140e9da / c71201d3），e7 被打破且**两者在 e7 输出相同**（f6b66de0 = 既往 a1-t5-restore 家族值）
  - prompt_len 双侧逐 tag 一致（20911/27812/43514），无截断；全部 200/finished
- 驱逐事件（系统级，非 horizon 直接）：e7 hollow_evict=12 / forced_drop_to_miss=6（e5: 4/2，e4: 4/0，m4t: 0/5）

### 5. 机制归因（spin 循环，日志证据）
逐 pass 循环（0ad03b2c 实测 1289 次，同一秒内多次）：
```
[P3] ready_stage rid=0ad03b2c... ready=0 headroom=42784      <- refill 每 pass 运行
[P2A] prefetch_issued rid=0ad03b2c... prefetch_length=20910   <- 真实 issue
[P2A] prefetch_revoke rid=0ad03b2c... storage_hit=0 requested=20910
[P2A] restore_disposition disposition=RECOMPUTE reason=revoked:miss
[P2A] restore_state state=NONE
[P2A] restore_recompute cause=miss                             <- 回到 NONE，重新 eligible
```
根因三连：
1. **NONE 候选无 decline-park**：`staging_candidates()` 对 `state==NONE && staging_eligible` 的 view 无条件列候选；miss→recompute→NONE 后同一请求立即重新 eligible。M3 文档声称 "declined requests park until a resource-epoch event"，候选层未实现。
2. **M3 epoch 签名被击穿**：`_ready_horizon_epoch_sig` = (frontier rid 元组, ready_count, inflight_speculative_tokens, prefetch_tokens_occupied, mem_pool_host.available_size, len(running_batch))。8-agent 24-restore workload 下 frontier/队列/可用页每 pass 变化 → event=True 每 pass → refill 以调度器 pass 速率运行（实测 ~141/s）；0ad03b2c 的 issue→revoke 又自持翻转 inflight/prefetch_occupied，双保险失效，5s 安全 reconcile 从未成为限速器。
3. **miss 是确定性而非瞬时的**：L3 extent 尚未收到该链（storage_hit=0 连续 1289 次），每次 revoke 立即释放 prefetch 预算（capacity≈21392 tokens）→ 下一 pass 再 issue → 自持。真正该做的是 park 到数据到达事件。
4. 附带：e4f681ed 类 "attempt-only" spinner（ready_stage 1145 次 / 真实 issue 1 次）——refill 每 pass 重评估同一候选，scheduler 层 `_prefetch_kvcache` 静默 decline，日志与评估开销照烧。

### 6. 损伤量化
- issued 2852 vs e5 463（6.2×）；revoke 2654 vs 377；restore_recompute 2660 vs 378
- full-chain 完成 episode 5 vs 15；no_finish episode 55（0ad03b2c 单 rid 1289 issue / 26.9M tokens 投机预取空转）
- ready_pool 从未 ≥2 稳态（M4 READY-first 分区无池可重排）；lookup/rid p50 3→9、max 35→1289
- 墙钟 668.3s vs 642.1s 相当——质量崩坏而非时延崩坏；96/96 仍全部完成

## summary
**判据逐条（9 条）**：

| # | 判据 | e7 实测 | 对照 e5 | verdict |
|---|---|---|---|---|
| 1 | B_ep ≤1.2s 无回归（B_fin 亦报） | B_ep full n=5 p50=1.382s；B_fin full n=22 p50=1.176s p90=1.777s max=3.294s | B_fin 1.158/1.720 (n=15)；B_ep 1.146 | **FAIL（边际）**：B_fin 口径无回归（+0.018s，读路径正常）；B_ep +0.236s 超 1.2s 门，n=5 样本过小 |
| 2 | 守恒/0 crash/0 OOM/0 backup fail/sha16 无新分歧 | 守恒 True；crash 0；OOM 0；backup fail 0；**sha16 6 个全新家族值** | e5：分歧全在已知家族 | **FAIL（sha16 子项）**：6 新值含 2 个 4-run 稳定 tag 被打破，a1-t12-restore 输出与 a1-t1-grow 相同（异常身份）；其余子项 PASS |
| 3 | A−B 逐样本 p90 ≤2s | full n=5 p50=13.371s p90=21.910s；all-ep p90=53.700s | 32.495/40.279 | **FAIL**（数值优于 e5 但 >2s 门 10×；且 full-chain 样本崩塌 15→5） |
| 4 | A p90 ≤3s | full p90=22.611s；all-ep p90=53.795s max=146.969s | A(issued) p90=10.66s | **FAIL** |
| 5 | ready_pool ≥2 稳态 | frac>=2 = 1/136 = 0.7%；time>=2 = 0.0%；size dist {0:68,1:67,2:1} | — | **FAIL**（watermark=[2,4] 稳态从未形成） |
| 6 | PREFETCH_BUDGET WAIT 驻留 p90 秒级 | **0.561s**（n=4732，max=18.181s） | 29.264s | **PASS**（唯一显著胜利：29.3s→0.56s） |
| 7 | READY→准入间隔≈0；READY 先于非 READY 样本>0 | 36 次 READY→准入（22 有后续 finish，样本存在）；但 162/198 READY 转入 WAIT_CAPACITY（82% 被拒，间隔 p50=0.01s/p90=6.77s）；准入间隔不可直接测（prefill 批日志无 rid） | — | **FAIL**：READY 未转化为准入，M4 分区无真实池可重排；子项 2 数值满足但机制未生效 |
| 8 | 投机 eviction = 0 | horizon 路径 0 evict（`ready_horizon.py` 无 evict 调用，M2 静默 decline）；系统级 hollow_evict 12 / forced_drop 6 | 4/2 | **PASS（直接）+ 注意**：间接驱逐升高（spin 流量推高设备压力），非 horizon 直接调用 |
| 9 | lookup/rid 主体 ≤2–3 | p50=9 p95=70 max=1289（92 rid，51% ≤9） | p50=3 p95=7 max=35 | **FAIL** |

**总体裁决：FAIL。** Ready Horizon v0（e11+e12+e13）整链验证未通过：状态机 5/7 判据 FAIL（唯一 PASS 是 PREFETCH_BUDGET 驻留 29.3s→0.56s，与 ready_pool 相关的地平线收益未兑现），数据面 B_fin 无回归但 B_ep 边际超门，A−B/A 远逊目标（虽优于 e5 绝对数——因 full-chain 样本崩塌 15→5、55 个 no_finish episode 退出了统计）。核心机制缺陷：M3 event-driven refill 门在 8-agent 高队列抖动 workload 下每 pass 重武装（实测 ~141 refill/s），NONE 候选无 decline-park，miss 确定性空转 1289 次——"T6 循环换个名字回归"（设计文档明令禁止的 per-pass poll 实际发生）。

**回注与复现性**：B_fin e7=1.176/22 与 e5=1.158/15 同口径可比（metric_compare.py 双轨）；A−B 采用逐样本配对口径（e6 定案），非 percentile 相减。

## followups
1. **M3 门修复（coder，最高优先）**：`_ready_horizon_epoch_sig` 排除 refill 自身 issue 流量所翻转的项，或对候选按 rid 加 decline-cooldown（miss 后 park 至 L3 数据到达事件/IO 完成）；`staging_candidates` 需区分 "attempted-but-declined" 与 "fresh"。位置：`scheduler.py:3257`（epoch sig）、`ready_horizon.py:116-151`（staging_candidates）、`:181-193`（should_refill）。
2. **ready_stage 日志语义**（scheduler.py:3271-3279）：当前记 plan.to_issue（含被 scheduler 层静默 decline 的 1144 次假尝试），应仅记真实 issue 或双列 attempted/issued，否则不可观测。
3. **sha16 新家族追查（coder）**：a1-t1-grow 4-run 稳定被打破 + a1-t12-restore 输出与 a1-t1-grow 相同（f6b66de0）——需判定是调度抖动所致解码非确定性（批形状→logit 舍入→长输出翻转）还是 restore 路径上下文退化（e7 该 turn ttft 10.0s vs e5 50.3s，命中路径不同）。prompt_len 无截断、http 全 200。
4. **间接驱逐升高**：hollow_evict 12/forced_drop 6（e5 4/2）与 spin 流量相关性——修复 M3 后复查应回落。

## open_issues
- A−B 主表 n=5（full-chain 完成样本崩塌）——即便修复后复测，需关注 full-chain 完成率是否回到 e5 的 15 水平，否则指标不可比。
- READY→准入间隔无直接可测证据（prefill 批日志无 rid）：建议未来在准入点加 rid 级日志（同 [P2A] 格式），criterion 7 才能严格验证。
- 恢复路径正确性疑云（sha16 a1-t12-restore==a1-t1-grow）未决，详见 followups 3。
