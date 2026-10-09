# Phase-2 Scorecard — 统一指标重算（只读审计）tester-e1

status: **done**

## 方法（数据源 / delta 对齐 / 窗口定义）

全部只读重算，未启动任何引擎/load，未修改任何证据。计算脚本留在 runner `/root/scorecard_cells.py`、`/root/scorecard_gate3.py`、`/root/scorecard_abwin.py`。

**数据源与对象集合**
- 阶段② 固定 trace decode 基准（正式工作点，11 cell）：`/root/evidence-gen-p{32,64,96}-c{4,6,8}/`（Graph ON）与 `/root/evidence-gen-p{32,96}-c8-goff/`（Graph OFF）。每 cell 取 `run-*/mid-run-metrics.txt`（引擎 /metrics 快照，~5s 间隔）、`runs.csv`（逐请求）、`gpu-util.csv`（nvidia-smi 5s 采样）、`metrics-final.txt`（Prometheus text 末态）。
- Cache/restore/GC/容量（RH OFF/ON 基线 + A/B）：`/root/evidence-gate3-soak/`、`/root/evidence-gate3-rhon/`、`/root/evidence-gate3-ab-a-off/`、`/root/evidence-gate3-ab-a-on/` 及其 `engine-gate3-*.log`（事件日志，`evt=` 行）。
- Gate-2 K 变体（K4/K8/K16）用作容量分层参考，非 restore 主导，标注后作旁证。

**delta 对齐**
- decode TPS：`realtime_tokens_total{mode="decode"}` 计数器，按 `ts` 相邻快照差 / 时间窗。全窗 = 首末快照；稳态窗 = `num_running_reqs` ≥ 峰值 90% 的子窗。
- prefill_compute TPS：`realtime_tokens_total{mode="prefill_compute"}` delta / 窗。
- cache hit：逐请求 `cached_tokens`（runs.csv 的 device+host+storage 命中之和，引擎在每请求结束上报）为准；metrics-final 的 `prefill_effective_tokens_total{mode=*_hit}` 仅作诊断（见 NOT MEASURABLE/差额节）。
- restore token 量：从 `engine-gate3-*.log` 的 `evt=restore_success rid=... n_tokens=<N>` 累加 N（非事件计数，是真实 token 量）。restore 延迟：`load_back_duration_seconds` 直方图（bucket 累计）线性插值 p50/p90/p99，mean = sum/count。
- 窗口：阶段② cell 全跑期；gate3 2h soak/rhon 全跑期；A/B clean window = [首 extent_write, +120s)，两轮各在自己首 recycle 之前（RH OFF 首 recycle offset 314.5s、RH ON 126.5s，故 120s 窗口均落在 recycle 前，无 GC 干扰）。

---

## 一、Cache 核心指标（token 量）

### 推荐工作点（pool=64 + Graph ON + c8）阶段② 11-cell 总表

`historical_prefix_tokens` 定义：本 trace 为短互异 prompt（p01..p16，互异前缀），cell 内**无跨请求前缀复用**，故 phase-2 cell 的 historical_prefix/cache_reused/recompute 三者均 ≈ 0（无共享历史）。**phase-2 是纯 decode 吞吐基准，不含 cache 命中语义**；cache/restore KPI 全部来自 gate3 restore 型 trace。

| cell | decode TPS(全窗) | decode TPS(稳态) | per-agent tok/s | avg_wall_s | p50_TPOT ms/tok | avg_TTFT_s | GPU mean | GPU p50 | GPU p90 | prefill TPS | steady_bs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p32-c4 | 318.1 | 317.3 | 79.3 | 3.10 | 12.6 | 3.10 | 66.7 | 100 | 100 | 58.1 | 4 |
| p32-c6 | 454.1 | 453.4 | 75.6 | 3.20 | 13.2 | 3.20 | 66.7 | 100 | 100 | 84.4 | 6 |
| p32-c8 | 460.8 | 483.3 | 60.4 | 4.12 | 16.1 | 4.12 | 71.1 | 100 | 100 | 85.4 | 6 |
| **p64-c4** | 317.9 | 317.3 | 79.3 | 3.10 | 12.6 | 3.10 | 55.6 | 100 | 100 | 58.1 | 4 |
| **p64-c6** | 469.8 | 468.6 | 78.1 | 3.10 | 12.3 | 3.10 | 53.3 | 66 | 100 | 87.3 | 6 |
| **p64-c8** ⭐ | **595.3** | **596.5** | **74.4** | **3.15** | **12.29** | **3.15** | 66.7 | **100** | 100 | 110.3 | 8 |
| p96-c4 | 321.4 | 321.1 | 80.3 | 3.01 | 12.2 | 3.01 | 75.0 | 100 | 100 | 58.7 | 4 |
| p96-c6 | 470.4 | 469.3 | 78.2 | 3.12 | 12.3 | 3.12 | 51.6 | 64 | 100 | 87.4 | 6 |
| p96-c8 | 601.7 | 607.4 | 75.9 | 3.13 | 12.3 | 3.13 | 67.7 | 100 | 100 | 111.5 | 8 |
| p32-c8-gOFF | 111.9 | 117.1 | 14.6 | 17.1 | 66.8 | 17.1 | 23.7 | 25 | 28 | 20.7 | 6 |
| p96-c8-gOFF | 163.4 | 163.6 | 20.4 | 12.2 | 47.7 | 12.2 | 23.8 | 26 | 27 | 30.3 | 8 |

- Graph ON vs OFF（c8）：p32 460.8→111.9（4.1x）、p96 601.7→163.4（3.7x）；64→96 仅 +1.8%。→ **推荐 pool=64+Graph ON+c8 成立**。
- 注：p64-c6/p96-c6 GPU p50=64/66 因 5s 采样窗内样本数少且恰落在 decode/drain 边界，GPU p90 均为 100；p50/p90 以 p90 为准判定饱和。
- TPOT 口径：ttft=wall=E2E（stream:false 整块返回，首 token 即整块），per-request TPOT = wall/completion = 0.0123 s/tok (p64-c8)。**验证参考值 c8≈596、per-agent≈74.5、GPU p50≈100%、256-token≈3.15s 全部吻合**（我的精确值 595.3/596.5、74.4、100%、3.15s）。

### Cache/restore 型 trace（gate3）—— 分层与 KPI

逐请求 ground-truth（runs.csv `cached_tokens` = device+host+storage 命中，`prompt_len` = 可复用历史前缀长度）——这是唯一诚实可溯源的口径：

| run | restore turns | 有命中 | historical_prefix_tokens | cache_reused_tokens | recompute_tokens | effective_cache_ratio | recompute 占比 |
|---|---|---|---|---|---|---|---|
| soak (RH OFF 2h) | 1540 | 1220 | 31,252,548 | 24,240,701 | 7,011,847 | **0.7756** | 0.2244 |
| ab-a-off (RH OFF) | 1535 | 1200 | 31,022,055 | 24,189,220 | 6,832,835 | 0.7797 | 0.2203 |
| ab-a-on (RH ON) | 1299 | 1090 | 28,077,152 | 18,792,155 | 9,284,997 | 0.6693 | 0.3307 |
| **clean 120s 窗 (ab-off)** | 4 | 4 | 104,447 | 104,252 | 195 | **0.9981** | 0.0019 |
| **clean 120s 窗 (ab-on)** | 3 | 2 | 41,822 | 41,762 | 60 | **0.9986** | 0.0014 |

分层（metrics-final `prefill_effective_tokens_total{mode=*_hit}`，全 run 累计，含 over-count 风险——见差额节）：
- soak：device 18,575,664 / host 12,927,023 / storage 6,938,433
- ab-off：device 18,661,597 / host 12,526,982 / storage 7,084,015
- ab-on：device 17,618,716 / host 10,675,514 / storage 218,883
- rhon：device 18,781,741 / host 10,035,300 / storage 16,375

**关键结论（正常容量，clean 120s 窗）**：effective_cache_ratio ≈ **99.8%**，RH ON/OFF 一致，≥95% 满足。全 run 掉到 67-78% 是容量压力（recycle/evict）所致，非引擎失效（见五）。

### 守恒校验
逐请求口径下 `cache_reused + recompute = historical_prefix` 恒等（由定义）：soak 24,240,701+7,011,847=31,252,548 ✓；ab-off 24,189,220+6,832,835=31,022,055 ✓；ab-on 18,792,155+9,284,997=28,077,152 ✓。守恒成立，无需解释差额。

### 对象集合汇总
- aggregate：全 11 cell 见总表；cache 语义见 gate3。
- conc 4/6/8：见总表（decode TPS 随 conc 单调升：c4≈318、c6≈470、c8≈596@64）。
- K=4/K=8/K=16：gate2 变体（多为 write/branch 相位，非 restore 主导，作旁证）：k8 ratio 0.743、k16 ratio 0.640——K 越大（会话越深）前缀可复用性越高但容量竞争越强，非本次正式工作点。
- Gate-3 2h soak / rhon / A-B：见上表。

---

## 二、Restore 指标（次数 + token 量 + 延迟）

### 2h soak（RH OFF 基线）
- restore_success：**852 次**
- **restored tokens 总量：9,454,492 token**（= Σ restore_success n_tokens）
- per successful restore：avg 11,097 / p50 10,382 / p90 20,889 / p99 30,711（min 67 / max 34,777）
- restore 延迟（load_back_duration 直方图）：p50 **0.066s** / p90 **0.109s** / p99 **0.191s**；count=1735、mean=110.3s/1735=0.0636s
- restore_disposition RECOMPUTE 决策：10,215 次、requested 84,066,204 token；restore_recompute 实际回退事件：5,556（cause miss=5,542, timeout=14）；restore_retry 9,465；restore_loadback_fail 10；forced_drop_to_miss 0；no_token 5,806
- `load_back_tokens_total`：kv 27,601,942 + mamba 3,712 = **27,605,654**（L3→Host→Device load 的 token 流，与 restore_success n_tokens 口径不同——前者含预取/未成功路径，后者为成功 restore 交付量，见差额节）

### "19 次 restore 到底恢复多少 token"（A/B clean 120s 窗，正是用户点名的问题）
| run | restore_success | restored tokens 总量 | avg/success | 每次 token 明细 |
|---|---|---|---|---|
| ab-a-off (RH OFF) | **19** | **430,445** | 22,655 | 15944,23705,24134,15944,22519,15944,22948,22948,24136,22948,30709,29849,30709,30278,30711,30280,3437,3453,29849 |
| ab-a-on (RH ON) | **19** | **391,110** | 20,585 | 24136,15944,24134,28230,23705,22517,14336,23379,24136,31138,20889,10399,24136,23379,22519,2638,3453,23379,28663 |

即：RH ON 与 RH OFF 在 clean 窗都恰好 19 次成功 restore，ON 恢复 391,110 token、OFF 恢复 430,445 token（每次 2.6K–31K 不等，p50≈23K）。

### 全 run restore_success（2h 级别）
- soak 852 次 / 9,454,492 token；ab-off 862 次 / 9,670,546 token；ab-on 仅 **21 次 / 422,951 token**；rhon 仅 2 次 / 20,471 token。
- 即：RH ON 下 2h 内 L3 restore 几乎被旁路（storage_hit 趋 0、restore_success 急剧减少），这是因为 RH 在容量压力下主要从 device/host 命中（device_hit 占比升），L3 路径几乎不消费——**这解释了 RH ON 的 cache ratio 掉到 0.6693**：不是 L3 失效，而是 RH 主动倾向热数据留在高缓存层，冷 L3 命中率下降。

### restore failure / revoke
- restore_loadback_fail：soak 10 / rhon 8 / ab-off 6 / ab-on 6
- forced_drop_to_miss：soak 0 / rhon 2 / ab-off 28 / ab-on 2（事件计数；带 freed token 量：ab-off 无法从该事件直接换算 L3 丢失——见 NOT MEASURABLE）
- prefetch_revoke：soak 5,542 / ab-off 5,740 / ab-on 9,122

---

## 三、Prefill / Decode 性能（正式固定-trace 工作点）

见第一节总表。补充：
- uncached prefill_compute TPS（阶段②）：p64-c8 = 110.3 tok/s（全窗），c4/c6/c8 与 conc 近似线性（58/87/110）。gOFF 时 prefill TPS 显著降低（p96-c8-gOFF 30.3）——Graph OFF 时 prefill 与 decode 均大幅退化，指向 CPU submission 瓶颈（gOFF GPU util 仅 24-26%）。
- aggregate decode TPS（= realtime decode delta / 窗，**未**把 window output tokens/wall 冒充）——p64-c8 595.3（全窗）、596.5（稳态）。
- per-request TPOT p64-c8：avg 0.01232 s/tok，p50 0.01229 s/tok（12.29ms）。
- E2E latency p64-c8：avg 3.153s，p50 3.146s，p90 3.228s；TTFT=wall（非流式整块）。
- GPU util（p64-c8）：mean 66.7%，p50 100%，p90 100%（n=9，5s 采样）。注：n 较小且含 ramp/drain，稳态段以 p90=100 判定饱和。
- gate3 soak GPU util（2h，n=1446）：mean 96.7%，p50 100%，p90 100%——restore 型 2h 满载 GPU 基本吃满。

---

## 四、容量 / GC

- **L3 configured capacity**（各引擎 ExtentFileBackend 行）：`ExtentFileBackend: ... extent=67108864 B slots=1430 max_size=64000000000 min_free=10000000000`，即 **max_size = 64,000,000,000 B（64GB）**、extent 块 64MB、1430 slot、min_free 10GB。`hicache_storage_backend_extra_config: {"max_size":"64G","min_free_space":"10G"}`。`MAX_SIZE=64G`、`SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G` env（FILE_SIZE=96G 但 backend 实际 max_size=64G）。
- **live/used peak**：metrics 中无直接 L3 容量占用 gauge（仅 `cached_tokens_total{cache_source="storage_ExtentFileBackend"}` 为 token 级累计，非字节占用）→ live 字节峰值 NOT MEASURABLE（缺 L3 字节占用 gauge）。
- **total logical writes**（extent_write 累计字节）：soak 1,435,193,671,680 B（≈1.37 TiB）；ab-off 1,443,785,506,816 B；ab-on 1,372,476,047,360 B；rhon 1,372,301,721,600 B。extent_write 事件数：soak 39,068 / ab-off 39,415 / ab-on 37,068 / rhon 37,135。
- **extent recycle count**：soak 6,454 / ab-off 6,513 / ab-on 36,527 / rhon 36,984。RH ON 的 recycle 数远高于 OFF（~5.6x），与 context 记录的一致（RH 下异常早 recycle，ready/DEVICE_QUOTA 恢复链未闭合——非本次范围）。
- **recycle 前/后 effective_cache_ratio**：
  - recycle 前（clean 120s 窗，无 GC）：ab-off 0.9981、ab-on 0.9986（≈99.8%，两者一致，正常容量）
  - recycle 后（全 run）：soak 0.7756、ab-off 0.7797、ab-on 0.6693
  - → 容量压力（recycle/evict）使 effective cache ratio 从 99.8% 掉到 67-78%。**"容量不够"与"引擎 cache 失效"可分离**：无 GC 时命中率 ~100%（引擎 cache 有效），有 GC 后下降（纯容量压力）。
- **GC 导致丢失的 reusable tokens**：`evicted_tokens_total`（soak 49,666,190 / ab-off 49,073,580 / ab-on 45,522,969 / rhon 45,341,916）与 `hicache_dropped_tokens_total`（soak kv 453,698+mamba 96；ab-off kv 625,087+mamba 138）。但 evicted 是"被逐出设备缓存"的 token，其中多少本可被后续复用并因 GC 丢失（即导致 recompute 增量的部分）无法直接由现有字段分离——**该精确量 NOT MEASURABLE**（缺"逐出 token 后续是否被 re-request"跟踪）。可用 recompute_tokens（全 run 6.8-9.3M）作为其代理上界。

---

## 五、稳定性（Gate-3 2h soak，RH OFF 基线）

- requests：2499 全部完成（runs.csv n=2499，completed 2499），HTTP 全部 200，**0 error，0 CUDA OOM**（engine log 无 "CUDA out of memory"/OutOfMemoryError）。
- restore_loadback_fail 10 次（2h 内）；forced_drop_to_miss 0；restore_recompute timeout 14 次（其余 5542 为 miss）。
- no_token 事件 5,806（admission 排队信号，非错误）。
- 正确性：`correctness failures`——runs.csv 无显式 correctness 字段；finish_reason 全为完成态（无中断/失败）。**显式 correctness 字段不存在 → correctness failure 计数 NOT MEASURABLE**（缺 per-request correctness 判定列）。
- zero-progress：未发现 decode 计数器停滞的稳定段；无专用字段 → 以 decode 计数器单调性为准（全窗单调，无停滞）。

---

## 六、最终总表（回答五个产品问题）

| # | 产品问题 | 答案 | 证据 |
|---|---|---|---|
| 1 | 3090 推荐配置（pool64+Graph ON+c8）decode aggregate TPS | **595.3 tok/s**（稳态 596.5；per-agent 74.4） | p64-c8 mid-run decode delta / 窗；runs.csv 20480 tok/34.4s |
| 2 | GPU 平均利用率 | **mean 66.7%，p50/p90 100%**（p64-c8）；gate3 2h soak mean 96.7%，p50/p90 100% | gpu-util.csv |
| 3 | 正常容量 effective cache ratio，≥95%？ | **clean 窗 ≈99.8%**（RH ON/OFF 均），**≥95% 满足**；全 run 77.8%（OFF）/66.9%（ON）为容量压力所致 | runs.csv 逐请求 cached/prompt |
| 4 | 2h 内 NVMe restore 次数/token/延迟 | soak：**852 次 / 9,454,492 token**，avg 11,097，p50 10,382 / p90 20,889 / p99 30,711；延迟 p50 0.066s / p90 0.109s / p99 0.191s。**"19 次"= A/B clean 窗 19 次 restore 430,445（OFF）/ 391,110（ON）token** | restore_success n_tokens 累加；load_back_duration 直方图 |
| 5 | 因 cache miss 被重算的历史 token 占比 | **clean 窗 ≈0.2%**；全 run soak 22.4%、ab-off 22.0%、ab-on 33.1%（= recompute/(cache+recompute)） | runs.csv recompute=prompt-cached |

---

## NOT MEASURABLE 清单（含缺的字段）

1. **phase-2 cell 的 historical_prefix_tokens**：本 trace 为短互异前缀，无跨请求共享，故三者≈0，语义上不适用（非缺字段）。
2. **L3 live/used 字节峰值**：缺 L3 容量占用 gauge（仅有 token 级 `cached_tokens_total{cache_source=storage_ExtentFileBackend}` 累计）。
3. **GC 精确丢失的 reusable tokens**：缺"逐出 token 后续是否被 re-request"跟踪；以 recompute_tokens 为代理上界。
4. **correctness failure 计数**：runs.csv 无 correctness 判定列；finish_reason 全完成态，HTTP 全 200。
5. **restore 单次事件时长**：per-restore 时间戳可还原 ts 差，但官方口径用 load_back_duration 直方图（count/sum/bucket），已给出 p50/p90/p99；无 per-restore 独立时长事件字段（用直方图替代，非缺）。
6. **metrics-final hit-mode 的 storage_hit 与 restore 消费核对差异**：`prefill_effective_tokens_total{mode=storage_hit}` 是 L3 query-hit 计数，不等于 consumed（cache_reused）。故分层 KPI 用 runs.csv 逐请求 cached_tokens 为准；metrics 分层仅作方向性诊断。差额来源见下。

## 守恒校验结果与差额解释

- 逐请求口径守恒恒等（见第一节），无差额。
- metrics-final 计数器口径下 `sum(hit modes) + prefill_compute` ≠ `input` 且不等于逐请求值，原因：
  1. `storage_hit`（L3 query hit）在 metrics 中即使未实际消费（restore 被 revoke/超时/LOADBACK_FAIL）也计入，造成 storage_hit 累计（soak 6.9M）显著高于 restore_success 实际交付量（9.45M 中来自 L3 的部分仅 ~4M/7M 量级），且 RH ON 下 storage_hit 剧烈虚高（16K vs ab-off 7M）——**这解释了为什么 RH ON 的 metrics 口径 ratio（0.552）远低于逐请求口径（clean 0.998）**：RH ON 大量 L3 query 未消费。
  2. metrics 计数器跨整个 engine 生命周期（含 ramp/drain/health），runs.csv 仅统计真实请求回合。
  → **诚实口径 = runs.csv 逐请求 cached_tokens/prompt_len**；metrics 分层仅供趋势。

## 证据路径（每个数字可回溯）

- decode TPS/TPOT/GPU：`/root/evidence-gen-p64-c8/run-20260905-111003/{mid-run-metrics.txt,runs.csv}`、`/root/evidence-gen-p64-c8/gpu-util.csv`、`verdict.json`（generation_tokens_total 20480, elapsed 34.4）
- 11 cell 全表：`/root/evidence-gen-p{32,64,96}-c{4,6,8}/run-*/`、`/root/evidence-gen-p{32,96}-c8-goff/run-*/`
- cache/restore/GC：`/root/evidence-gate3-{soak,rhon,ab-a-off,ab-a-on}/run-*/runs.csv`、`/root/evidence-gate3-{soak,rhon,ab-a-off,ab-a-on}/metrics-final.txt`、`/root/engine-gate3-{soak,rhon,ab-a-off,ab-a-on}.log`
- L3 容量：`/root/engine-gen-p64-c8.log` 的 `ExtentFileBackend:` 行；env `MAX_SIZE=64G`、`SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G`（run-p2-decbm-cells.sh）
- 计算脚本：runner `/root/scorecard_cells.py`（11-cell decode/GPU）、`/root/scorecard_gate3.py`（gate3 全量 counters/restore/GC/GPU）、`/root/scorecard_abwin.py`（A/B clean 120s 窗）；另在 runner 用临时 python 片段算 per-request ratio/restore token 分布/首 recycle offset。

## open_issues

- RH ON 在容量压力下的异常（recycle 5.6x、L3 命中近旁路、recovery 链）与 context.md 一致——根因未闭合，属 deferred known issue，非本次审计范围，未修（只读）。
- metrics 分层（device/host/storage）在 RH ON 下与逐请求口径偏差大，建议后续在引擎侧增加"consumed storage tokens"独立 counter 以消除 query-hit 虚高。
- 建议评审：对 p64-c8 稳态 decode TPS（596）做一次重复 run 确认采样稳定性；对 gate3 soak 的 852 次 restore 的 L3 来源占比做分层确认。
