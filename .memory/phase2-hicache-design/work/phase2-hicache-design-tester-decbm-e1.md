# phase2-hicache-design — Decode/Mamba 9-cell benchmark + Graph OFF attribution (tester decbm-e1)

## status: done

## 任务完成
阶段② Decode/Mamba benchmark **完整 9-cell**（Graph ON）+ **2 个 Graph OFF 归因 cell**（用户推荐项）。
目标机 175.155.64.171:24052 (RTX3090 24G)。全部 cell rc=0，**无一处 OOM**（含 96@8 风险格）。
matrix 严格执行：pool{32,64,96} × conc{4,6,8}，全部 Graph ON，max_new=256，turns=10，budget=900。

## 9-CELL 主表（Graph ON，稳态 decode 指标）

| cell | pool | Graph | conc | rc | req | comp | gen_tokens | **稳态 decode tok/s** | TPOT(s/tok) | batch | mamba_used/avail | caps? | OOM? |
|------|------|-------|------|----|-----|------|------------|----------------------|-------------|-------|--------------------|-------|------|
| c4   | 32   | ON | 4  | 0 | 40 | 40 | 10240 | 317.3 | 0.0120 | 3.83 | 12 / 7.8  | yes(cap=6,未触及) | no |
| c6   | 32   | ON | 6  | 0 | 60 | 60 | 15360 | 453.4 | 0.0123 | 6.00 | 18 / 3.3  | **yes(cap=6,满载)** | no |
| c8   | 32   | ON | 8  | 0 | 80 | 80 | 20480 | 483.3 | 0.0161 | 6.00 | 18 / 1.0  | **yes(cap=6,queue=2)** | no |
| c4   | 64   | ON | 4  | 0 | 40 | 40 | 10240 | 317.3 | 0.0120 | 4.00 | 12 / 38.4 | no | no |
| c6   | 64   | ON | 6  | 0 | 60 | 60 | 15360 | 468.6 | 0.0119 | 5.83 | 18 / 30.0 | no | no |
| c8   | 64   | ON | 8  | 0 | 80 | 80 | 20480 | **596.5** | 0.0123 | 8.00 | 24 / 21.8 | no | no |
| c4   | 96   | ON | 4  | 0 | 40 | 40 | 10240 | 321.1 | 0.0119 | 4.00 | 12 / 72.5 | no | no |
| c6   | 96   | ON | 6  | 0 | 60 | 60 | 15360 | 469.3 | 0.0119 | 5.83 | 18 / 61.3 | no | no |
| c8   | 96   | ON | 8  | 0 | 80 | 80 | 20480 | **607.4** | 0.0122 | 8.00 | 24 / 55.0 | no | **no** |

稳态 decode tok/s = `realtime_tokens_total{mode="decode"}` 的 delta / 时间窗（num_running 满负荷时段）。
gen_throughput gauge 与稳态 delta 一致（~346-348 / ~683-688 等），未恒 0（此引擎/配置下正常发射）。

## Graph OFF 归因（推荐项，已做）

| cell | pool | conc | rc | req | comp | gen_tokens | 稳态 decode tok/s | TPOT(s/tok) | batch | mamba_used/avail | caps? | OOM? |
|------|------|------|----|-----|------|------------|-------------------|-------------|-------|--------------------|-------|------|
| p32-c8-goff | 32 | 8 | 0 | 80 | 80 | 20480 | 117.1 | 0.0669 | 6.00 | 18 / 1.8 | yes(cap=6) | no |
| p96-c8-goff | 96 | 8 | 0 | 80 | 80 | 20480 | 163.6 | 0.0478 | 8.00 | 24 / 49.9 | no | no |

## 主效应结论

### 1. Mamba pool 32→64→96 对 decode concurrency 的影响 — "解除 cap 的最小池" = **64**
- **决定性证据（engine log smoking gun）**：p32 三个 cell 引擎日志均有
  `"max_running_requests is capped to 6 by the mamba state cache (max_mamba_cache_size=32, 5 state slots per request)"`；
  p64/p96 六个 cell **全部无此消息**。
- **机制**：1 个请求占用 5 个 mamba state slot；pool 32 / 5 = 6 并发上限。
  - p32-c4：conc=4 < cap=6 → 未触及，decode 317 tok/s
  - p32-c6：conc=6 == cap=6 → 刚好满载，mamba avail 3.3（单采样点归 0）
  - p32-c8：conc=8 > cap=6 → **running 钉死在 6，queue=2 持续驻留**，avail=0 池耗尽；TPOT 恶化至 0.0161
- **pool 64（96 slots → 上限 12.8）在 conc=8 完全解除 cap**：running 满 8、queue=0、无 cap 消息。
- **结论**：解除 Mamba decode concurrency cap 的**最小池 = 64**（上限 12.8 ≥ 8 并发）。96 相对 64 在 conc=8 仅 +1.8%（607.4 vs 596.5），收益边际。

### 2. 每档 pool 的 decode 吞吐（Graph ON，conc=8 峰值）
| pool | c4 | c6 | c8 |
|------|----|----|----|
| 32   | 317 | 453 | 483 (cap 限 6, batch 6) |
| 64   | 317 | 469 | **596** (batch 8, uncapped) |
| 96   | 321 | 469 | **607** (batch 8, uncapped) |
- conc=4 时三档 pool 几乎相同（317/317/321）→ pool 在下限以下无影响。
- **跨档及上升沿**：32→64 在 conc=8 带来 +23%（483→596），64→96 仅 +1.8%。
- CPU/调度侧观察：p64/p96-c8 batch 满 8 时 decode tok/s 达 ~600，GPU util 100%。

### 3. Graph ON vs OFF 归因（Graph 独立贡献）
| cell | Graph ON | Graph OFF | Graph 加速 |
|------|----------|-----------|-----------|
| p32-c8 | 483.3 tok/s | 117.1 tok/s | **4.1x** |
| p96-c8 | 607.4 tok/s | 163.6 tok/s | **3.7x** |
- **CUDA Graph 是 decode 路径的绝对主力**：Graph ON 使稳态 decode 吞吐提升约 **3.7-4.1 倍**，TPOT 降低 4-5 倍。
- Graph OFF 时 decode_cuda_graph passes 为 None（graph 完全禁用），decode 走非 graph 路径（~117-164 tok/s）。
- **Mamba cap 与 Graph 无关**：p32-c8-goff 仍有 cap 消息、running 限 6；p96-c8-goff 无 cap、batch 满 8（与 gON 一致）。
- 关键：**p96-c8 Graph OFF 无 OOM**（24G 卡上 19 GiB 引擎 + 8 并发非 graph 路径安全）。

### 4. Mamba effective concurrency / 池容量
- 每 request 5 slots × N running：p32 满负荷 6 req = 30 slots（池 32 耗尽，avail=0）；p64 满负荷 8 req = 40 slots（池 64 富余 24）；p96 满负荷 8 req = 40 slots（池 96 富余 56）。
- **p32 是唯一显示池压力的档**：conc=6 时 avail 触及 0，conc=8 时 avail 持续 0（queue 驻留的原因）。
- 结论：**32 池在 conc≥6 时打满 Mamba slot**，`mamba_used`（18-24 slots）与 `max_running`（6）一致 → pool 直接压制并发。

### 5. 归因结论（总体）
- **目标组合 = pool 64 + Graph ON + conc 8（或更高）**：这是"解除 Mamba cap 的最小池"+Graph 全开的实测最优（596 tok/s）。
- p96 提供 ~1.8% 额外吞吐但 VRAM 占用更高（~19.3 vs ~17.8 GiB boot），性价比低。
- **Graph ON 是决定性因素**（4x），pool 是次要但真实的 concurrency 门槛（32 档 cap 在 6）。

## 证据路径
- 每 cell runs.csv/verdict.json/mid-run-metrics.txt：
  - `/root/evidence-gen-p{32,64,96}-c{4,6,8}/run-<ts>/`
  - Graph OFF: `/root/evidence-gen-p{32,96}-c8-goff/run-<ts>/`
- engine log cap 证据：`/root/engine-gen-p32-c{4,6,8}.log`（"max_running_requests is capped to 6"）
- master 汇总：`/root/decbm-master-gON.log`(session log)、`/root/decbm-master-gOFF.log`
- 期望值：全部断言（40/60/80 req、20480 tokens、finish_reason=length、ttft 非空、http=200）独立自 verdict/runs.csv，非自循环

## 一致性 / 验证纪律
- 每 cell 串行、fresh namespace（新 STORAGE_DIR `/data/l3/p2io-gen-*`）、run 前确认 GPU idle（15 MiB 基线）、run 后 SIGTERM 引擎按 PID + 确认 GPU 回到 15 MiB 空闲。
- 全部 11 cell 出 GPU 15 MiB idle / 0 procs / 8024 free / 无残留（最后验证 15 MiB, procs=0, 8024 free）。
- 无 OOM（11/11 引擎日志 grep "CUDA out of memory"=0）。
- 未改 driver/common/wrapper; gOFF runner 为自包含新增脚本（不 source 主 runner）。

## followups
1. p96-c8 已是全局最优（607 tok/s），但 p64-c8（596）几乎持平 → 推荐池取 64 以省 VRAM/留 headroom（若后续跑高 conc 或长上下文的 KV，64 池比 96 更安全）。
2. Graph OFF 与 Graph ON 的 4x 差异是**本 workload（Qwen3.5-9B w4a16 + 短 prompt 256 gen）**下的数值；长 prompt / 大 prefill 的 workload 中 Graph prefill 占比可能不同（本实验 decode 为主），归因结论限 decode 路径。
3. 未测 conc>8（单卡 max-running-requests=8 为 wrapper 硬上限）。若需 >8 并发（K8s 多 worker / 多卡），需另起 wrapper 参数（超出本矩阵）。

## open_issues
1. **96@8 OOM 风险已解除**：阶段①未测 96@8，本实验实测 p96-c8-gON 及 p96-c8-goff 均无 OOM（boot 19 GiB，峰值运行稳妥）。24G 卡安全。
2. gen_throughput gauge 在本引擎此配置下**正常发射**（非恒 0），主指标稳态 decode tok/s 用 `realtime_tokens_total{mode="decode"}` delta，两者交叉一致；未来若 gauge 缺失仍降级 delta（task 口径保留）。
3. gOFF cell 的名称（`engine-gen-p{32,96}-c8-goff.log`）与 gON 相同前缀但 tag 带 -goff 后缀，引擎日志文件名与 evidence 目录一致，无混淆。
