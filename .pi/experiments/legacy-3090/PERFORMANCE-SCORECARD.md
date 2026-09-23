# SGLang / Agent Workload 性能 Scorecard 指标体系

本文是 RTX 3090 24G HiCache 性能评估的**指标口径规范**（正式文档）。
它规定一次请求应从 `queue → cache restore / prefill → decode → completion` 拆分观测，
而不是只看 TPS。本文只定义指标与口径，**不新增任何指标**；出处见文末第 9 节。

- 适用对象：M1/M2/M3/M4 角色评估、以及后续任何同源性能对比。
- 权威规范：`.memory/phase2-hicache-design/evidence/p0-telemetry-20260914/authority/PERFORMANCE-BASELINE-SPEC-v2.md`
  （状态 `SPECIFICATION_ONLY`，自述未跑过 workload/GPU/server）。
- 可复用采集 harness：`3090-dev/tools/perf/efficiency_sweep.py`。

## 0. 目的与口径

核心不是只看 TPS，而是把一次请求拆成：`queue → cache restore / prefill → decode → completion`。

只有把每个阶段的指标分开报告，才能区分「用户感觉慢」与「GPU 真的算得慢」，
也才能避免把 cache 命中误读成计算能力。

## 1. 端到端与延迟指标

| 指标 | 定义 | 主要回答 |
|---|---|---|
| TTFT | request 到第一个输出 token 的时间 | 用户开始看到响应要多久 |
| E2E latency | request 到最后一个输出 token / 请求完成 | 一轮总耗时 |
| ITL | 相邻输出 token 之间的时间间隔 | decode 是否稳定、有无卡顿 |
| TPOT | `(E2E - TTFT) / output_tokens`（近似每输出 token 时间） | 单请求 decode 速度 |
| Per-request decode TPS | `output_tokens / decode_time` | 单请求生成速度 |
| Aggregate output TPS | 同时运行请求的总 generated tokens / s | GPU 真正的 decode 吞吐能力 |
| Request throughput | completed requests / s | 服务整体吞吐 |

规范对照：UX 延迟为 `ttft, e2e, tpot, itl`，分位 `p50/p95/p99`
（`PERFORMANCE-BASELINE-SPEC-v2.json:9-12`）；吞吐定义见
`PERFORMANCE-BASELINE-SPEC-v2.md:58-61`。

## 2. 输入侧指标（必须区分「上下文长度」与「真正计算量」）

| 指标 | 定义 |
|---|---|
| prompt tokens | 本次请求完整输入 token 数 |
| cached / recovered tokens | 被 Radix/HiCache 直接复用、不重新 prefill 的 token |
| newly-prefilled tokens | `prompt_tokens - recovered_tokens`，真正重新计算的部分 |
| cache hit rate | 通常 `recovered_tokens / prompt_tokens`；严格实验必须说明 denominator |
| prefill time | 真正执行新 prompt prefill 的时间 |
| prefill TPS | `newly_prefilled_tokens / prefill_time`，**不能**拿完整 prompt tokens 算 |
| effective input TPS | 完整 prompt tokens / 输入处理时间；含 cache 加速，只是用户视角指标 |

> 记录教训：M1 的 4.5K prompt 大量 cached，M2 是 cold ⇒ 直接比较 TTFT 或 concurrency 没意义，
> 必须同时报告 `cached / newly-prefilled`。

规范对照：cache 守恒四分（勘误后）为 `C = L1_tokens + L2_tokens + L3_tokens`，
`newly_prefilled_tokens = prompt_tokens - C`（`PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.md:11-25`）。
`avoidable_recompute_tokens` 是独立派生子集，仅在 durable 前缀权威被证明时输出，否则 `null`
（同文件 `:27-41`）。

## 3. Cache / HiCache 分层

- L1/device Radix hit：GPU 上直接命中的 prefix
- L2/host hit/restore：从 CPU host cache 恢复
- L3/storage hit/restore：从 storage 恢复
- restore tokens：从 L2/L3 恢复的 token/state
- avoidable recompute：本来已有 cache/state 却又重新 prefill 的 token
- eviction：被逐出的 cache entry/token/state 数量
- write/backup：L1→L2/L3 写出的量

规范对照：`prompt_tokens = L1_tokens + L2_tokens + L3_tokens + newly_prefilled_tokens`
（`PERFORMANCE-BASELINE-SPEC-v2.md:71`）；`restore_tokens`、`full/partial/miss`、
`mamba_slots/restore/rebuild/eviction`、`rh_*` 等明细见 `.json:19-20`。
三层分解的运行时来源为 `split_cached_prefix_by_tier`
（`python/sglang/srt/managers/schedule_batch.py:220-232`），请求级累计见同文件
`:2599`（`req.cached_tokens += new_cached`）与 `:2608` 起的 device/host/storage 分解。

## 4. 并发侧指标

| 指标 | 定义 |
|---|---|
| nominal concurrency | 压测发出的 `c=1/2/4/8...` |
| actual/running concurrency | 后端真正同时 running 的请求数 |
| queue_time | 请求已到达但尚未 admission/running 的时间 |
| running / queued requests | 每时刻执行与等待数量 |
| decode batch size | 实际合批 decode 的请求/token 数 |
| retraction / preemption | 因资源不足把 running request 撤回/抢占的次数 |

规范对照：`queue` 指标为 `wait, admission, active, queued`
（`PERFORMANCE-BASELINE-SPEC-v2.json:17`）；阶段指标 `batch_histogram` 见 `.json:16`。

## 5. 资源侧

- KV occupancy / free KV tokens
- Mamba slots used/free
- Mamba eviction / restore
- HiCache host/storage usage
- VRAM：weights / KV / Mamba recurrent state / CUDA Graph / free
- CUDA Graph hit / fallback
- GPU utilization / SM utilization / power（需旁路硬件 telemetry）

规范对照：telemetry 字段 `gpu_util, vram, gpu_bw, power, clocks, cpu, ram, pcie_h2d, pcie_d2h,
nvme_*`（`.json:21`）；缺失权威计数器一律记 `UNAVAILABLE`，**绝不从占用或总 token 吞吐推断**
（`.json:24`；`.md:81-87`）。

## 6. 固定输出：精简版基础表

```text
Workload:
  prompt tokens p50/p95
  output tokens p50/p95
  concurrency

Latency:
  TTFT p50/p95
  E2E p50/p95
  queue_time p50/p95
  ITL/TPOT

Compute:
  prefill TPS
  per-request decode TPS
  aggregate decode TPS

Cache:
  cached tokens
  newly-prefilled tokens
  prefix hit rate
  L1/L2/L3 restore（若可得）
  eviction / avoidable recompute

Runtime:
  actual running concurrency
  decode batch size
  KV free/used
  Mamba slots free/used
  retractions
  CUDA Graph hit/fallback
```

## 7. 三条最重要的口径纪律（必写）

1. TTFT 必须和 cache state 一起看。
2. Prefill TPS 必须用 newly-prefilled tokens，不是完整 prompt tokens。
3. 并发性能必须同时看 aggregate TPS + queue_time + actual concurrency，不能只看单请求 TPS。

## 8. Agent 层 KPI（不属于「模型基础性能」，另列）

`successful tasks/hour`、`cost/successful task`、`P95 task completion time`
—— 用于最终工作负载评价。

规范对照：`agent/` 为独立 workload 命名空间，使用固定多轮/tool corpus 且上下文递增
（`PERFORMANCE-BASELINE-SPEC-v2.json:31`；`.md:102`）。Agent 层 KPI 与模型基础性能**分开报告**，
不得混入第 1–6 节的指标。

## 9. 与既有资产/规范的出处（逐条 file:line）

以下路径均相对于仓库根 `/home/ubuntu/workspaces/3rdparty/sglang/`，且均已存在并只读核对。

### 9.1 权威规范

- `.memory/phase2-hicache-design/evidence/p0-telemetry-20260914/authority/PERFORMANCE-BASELINE-SPEC-v2.md`
  - 全文 150 行；状态 `SPECIFICATION_ONLY` 见 `:3-8`；UX/吞吐/cache 定义见 `:51-79`；telemetry 见 `:81-87`。
- `.memory/phase2-hicache-design/evidence/p0-telemetry-20260914/authority/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.md`
  - 全文 54 行；cache 守恒勘误见 `:11-25`；avoidable recompute 见 `:27-41`。
- 同名 `.json`（机器可读契约）与 `.sha256`（哈希）同目录。

### 9.2 实际 harness（同源）

- `3090-dev/tools/perf/efficiency_sweep.py`（本仓；M1/M2 同源，含 `--flush` 控制；
  §127 C1–C4 加法式修订后行数增加）
  - TTFC = 首个 content delta（旧 `ttft_*`），`:133-136`；
    基础性能 TTFT = 首个任意输出 delta（`ttft_output_*`），C1 新增；
    decode TPS = `completion_tokens/(dur_s-ttft_s)`，`:212-213`；
    aggregate TPS = `total_out_tokens/max(per-request dur_s)`，`:227`；
    cache 命中 = `usage.prompt_tokens_details.cached_tokens`，`:147`；`--flush`，`:163-173` 与 `:340`。
  - `--flush` 对应 M2-RCA 的 `RCA_FLUSH=1`，但**不代表冷**（C4，须显式 `--cache-state`）；
    harness 说明见 `3090-dev/tools/perf/README.md`。
- `3090-dev/metrics/metric_compare.py`（既有 P2A restore episode 的 A/B 配对工具）
  - 用于 restore 服务窗口的逐 episode 对比，非 UI 端到端性能；文件头说明见 `:1-42`。

### 9.3 指标规范出处

- `.memory/phase2-hicache-design/agents/PERF-METRIC-SUITE-RECON-20260918.md`
  - 指标定义（原样抽出）见 `D. 指标定义` `:91-99`：TTFT `:93`、decode TPS `:94`、
    aggregate TPS `:95`、cache 命中 `:96`、Prometheus `:97`、e2e `:98`、per-request 导出 `:99`。
  - 可比性条件见 `E. 可比性条件` `:101-111`；权威规范/勘误/契约出处见 `A.` `:25-43`。

### 9.4 服务端字段

- `usage.prompt_tokens_details.cached_tokens`
  - 门控开关 `enable_cache_report`（默认 `True`）：
    `python/sglang/srt/server_args.py:1380-1384`。
  - 填充逻辑：`python/sglang/srt/entrypoints/openai/usage_processor.py:43-49`
    （`if enable_cache_report: ... cached_total`），`_details_if_cached` 见 `:16-19`。
    > 说明：recon 报告曾引 `usage_processor.py:41-45`；实际当前内容为 `:43-49`，**以实际为准**。
- per-request JSONL 导出
  - `python/sglang/srt/observability/request_metrics_exporter.py`
    （`FileRequestMetricsExporter` `:72-156`；输出文件名 `sglang-request-metrics-{hour}.log` `:105-106`）。
  - 服务端开关：`--export-metrics-to-file` / `--export-metrics-to-file-dir`
    （`python/sglang/srt/server_args.py:1649-1658`）。

### 9.5 采集通道与覆盖（重要）

当前**仓库内唯一固化的端到端 harness** 是 `efficiency_sweep.py`。它稳定输出：
`ttft_p50/p90/p95`、`dur_p50/p90/p95`（对应 E2E）、`decode_tps_p50/p90`、`aggregate_tps`、
`total_out_tokens`、`cached_tokens_nonzero/max/mean`（字段清单见 `:267-272`）。

按 ledger §127 的 owner 口径修正，harness 做**加法式**扩展（C1–C4，不改名/不删除既有字段）：

- **C1 TTFT 拆分**：`ttft_output_*` = 基础性能 TTFT（首个**任意**输出 delta，含
  `reasoning_content`）；`ttfc_*` = 首个**最终 content** delta（TTFC）；`n_ttfc` 为参与
  TTFC 统计的请求数（仅 reasoning 无 content 者不计入）。旧 `ttft_*` **= TTFC**，仅向后兼容，
  语义在 `manifest.ttft_field_semantics` 显式标注。第 1 节的「TTFT」在使用时应明确采用哪一口径；
  **不得再用 first-content 作为 M3/M4 的唯一 TTFT**。
- **C2 reasoning/thinking policy 冻结**：`--reasoning-effort` / `--thinking` 逐请求发送并写入
  `manifest`（连同 model/server_argv/max_tokens/ignore_eos），跨角色比较前必须核对一致。
- **C3 microbenchmark 标记 + agent-like 档**：`--workload-kind micro`（默认，64-token/ignore_eos）
  仅为 microbenchmark，manifest 带 `workload_kind_note` 声明其不具 agent 代表性；
  `--workload-kind agent-like` 用真实长前缀、正常 EOS、典型 256/512 输出。
- **C4 cache 状态成为结果字段**：每 level 记 `prompt_tokens_p50` / `cached_tokens_p50` /
  `cached_tokens_mean` / `newly_prefilled_tokens_p50` / `hit_rate_mean`；`--cache-state`
  {cold-distinct,warm-shared,warm-distinct} 为显式声明，**`--flush` 不等于冷**。
  这落实第 2 节「必须同时报告 cached / newly-prefilled」的纪律。

以上扩展是**采集字段/口径标注**，不改变本文第 1–6 节 owner 固定指标集；完整字段与用法见
`3090-dev/tools/perf/README.md`。

以下指标**该 harness 不直接产出**，需从别的既有权威通道获取，或按规范记 `UNAVAILABLE`：

- ITL / TPOT：无逐 token 时序，规范要求，harness 不产出（对照 `PERF-METRIC-SUITE-RECON-20260918.md:99`）。
- queue_time / prefill/newly-prefilled / eviction / restore 分层 / KV/Mamba/CUDA Graph：
  见 per-request JSONL（`request_metrics_exporter.py`）或 Prometheus；缺失即 `UNAVAILABLE`。
- GPU util / power / VRAM：需旁路硬件 telemetry（`.md:81-87`）。

**如何采集（一条命令示例）**：

```bash
python3 3090-dev/tools/perf/efficiency_sweep.py \
  --tag m2 \
  --url http://127.0.0.1:30000/v1/chat/completions \
  --model omnicoder-9b-gptq-int4 \
  --flush
```

对比时须保持相同 `--levels` / `--count-per-level` / `--out-tokens` 与相同 case/flush 设定；
跨角色比较前必须记录 `--server-argv` 与模型身份（`3090-dev/tools/perf/README.md:69-84`）。

### 9.6 未找到（已核）

- 未找到独立命名为「M1/M2 基础性能评估 suite」的固化产物；实跑口径 = F39 `efficiency_sweep.py`
  + M2-RCA `sweep.py`，现以 `3090-dev/tools/perf/efficiency_sweep.py` 固化
  （`PERF-METRIC-SUITE-RECON-20260918.md:48-71`，`Defects or blockers` `:144`）。

## 口径边界（非新指标，仅为使用纪律）

- `aggregate_tps` 的 harness 口径为 `total_out_tokens / max(per-request dur_s)`，
  **不同于**规范的 `aggregate_output_tps = output_tokens / wall_time`（`.json:14`）；
  前者只可作同一 harness 内的相对量（`3090-dev/tools/perf/README.md:23-27`）。
- 规范只允许在身份/argv/corpus/warmup 边界一致时比较（`.md:10-18`）；否则只能做相对观察。
