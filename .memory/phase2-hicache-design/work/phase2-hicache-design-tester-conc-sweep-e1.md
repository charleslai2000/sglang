# phase2-hicache-design — 实验① c>8 单卡 decode 并发上限 sweep（tester conc-sweep-e1）

- 任务：sglang-3090-24g-hicache（phase2-hicache-design）实验①
- 日期：2026-09-05
- 状态：**done**
- 引擎/模型：SGLang + HiCache × Qwen3.5-9B-w4a16（GPTQ 4-bit 混合 KV/SSM Mamba）
- 机器：远程 runner 175.155.64.171:24052（RTX 3090 24G，单卡唯一目标机）
- wrapper：新建 `/root/direct-launch-sweep-hi.sh`（POOL/MAX_RUNNING_REQUESTS/CUDA_GRAPH_MAX_BS 可配，含 ninja PATH 修复；不改 hicap/gate1 现有 wrapper、不改引擎源码、不改模型）
- runner 脚本：`/root/run-conc-cell.sh`（单 cell）、`/root/run-conc-cell-prof.sh`（带 dmon 的 cell）、`/root/run-p2-conc-sweep.sh`（整 sweep 框架）

---

## 0. 前置 profiler run（orchestrator 新增步骤）

### 配置与运行
- pool64 + Graph ON + c8（=阶段②推荐点），固定 generation trace，TURNS=40（~2.3 分钟稳态）。
- 证据：`/root/evidence-prof-p64-c8/run-20260905-180115`（320 req，elapsed 136.4s）
- 采集：`nvidia-smi dmon -s pucvmt` + `dmon --gpm-metrics 2,5,10,12,20,21` + pynvml + gpu-util.csv

### GPM 可用性判定（如实降级）
- **GPM 在消费级 RTX 3090 上不可用**：`nvidia-smi dmon --gpm-metrics` 各活动列（smutil/mmaact/dram/fp32/pcitx/pcirx）全为 `-`；pynvml 无 `nvmlDeviceGetGpmMetrics`；`nvmlGpmQueryDeviceSupport(h)` → `isSupportedDevice=0`；`nvmlGpmQueryIfStreamingEnabled` → NVMLError_NotSupported。已开启 persistence mode（`nvidia-smi -pm 1`）复测仍为 `-`。**已按 orchestrator 指示降级**：dmon -s pucvmt + pynvml。

### 结果（dmon pucvmt 稳态窗口 pwr≥300W，n=118/133 采样）
| 指标 | mean | p50 | p90 | max | 判读 |
|---|---|---|---|---|---|
| power (W) | 337.1 | 348 | 349 | **350** | **贴 350W 功耗墙** |
| SM util (%) | 91.7 | 100 | 100 | 100 | 满 |
| Mem util (%) | 91.0 | 100 | 100 | 100 | 满 |
| pclk (MHz) | 1779 | 1770 | 1860 | 1950 | 持续 boost |
| mclk (MHz) | 9501 | 9501 | 9501 | 9501 | 满速 |
| PCIe RX (MB/s) | 37.1 | 40 | 43 | 43 | 可忽略 |
| PCIe TX (MB/s) | 12.4 | 13 | 14 | 16 | 可忽略 |

gpu-util.csv：44 采样 mean 70.7% / p50 100% / max 100%。
性能：STEADY decode TPS = **601.0**（realtime_tokens_total decode delta / 126.2s 稳态窗）；FULL-window = 600.5；decode graph passes/s = 75.1；mamba used/avail mean = 24/11。80→320 req，rc=0，零 OOM，finish 全 length。

### profiler 判定
**c8≈601 tok/s 是 compute-bound（power-limited）**：
- 稳态 SM 100% + Mem 100% + pclk boost + **power 钉在 350W 墙** → GPU 算力已满，不是 scheduler/Mamba/launch 没喂饱。
- PCIe RX/TX 可忽略（<45 MB/s）→ 非 memory/IO-bound。
- 无法用 GPM 区分 SM-activity vs Tensor-activity（消费卡硬件限制），但功耗墙 + 双 100% 已足以判定 compute-bound。
- 下界参考（粗略，不作 KPI）：~600 tok/s × ~18 GFLOP/token ≈ 10.8 TFLOP/s（dense 近似，hybrid+Mamba+量化 kernel 会改变真实值）。
- **含义**：GPU 已满，c>8 吞吐提升空间有限；但 profiler 只测了 c8，sweep 实证显示 c8→c16 仍有大增益（见下），因为 c8 时 power 虽满但 batch 利用率不足——**compute-bound 的功耗墙 与 并发提升吞吐 可共存**（更大 batch 每步处理更多 token，功耗仍满但每瓦 token 更多）。

---

## 1. 档位与配置

固定 Graph ON + generation trace（gen_load.py，max_new=256，stream:false，16 固定 prompt，turns=10 或 20）。engine random_seed 每启动不同（已知 confound，记录于各 engine-alloc.txt 的 random_seed 字段）。每 cell fresh namespace、run 前 idle 15MiB、run 后 SIGTERM 回 idle。max_running 与 graph max_bs 均设到该档 conc。

| 档位 | pool | conc | 说明 |
|---|---|---|---|
| p96-c8 | 96 | 8 | 与阶段②交叉控制点 |
| p96-c12 | 96 | 12 | |
| p96-c16 | 96 | 16 | （T10 + T20 各一） |
| p96-c19 | 96 | 19 | pool96 硬边界（cap≈19，实际 cap 18） |
| p106-c19 | 106 | 19 | 与 pool96 交叉控制点（T10 + T20 + prof） |
| p106-c21 | 106 | 21 | 测 24G 能否跑满 Mamba 上限（T10 + T20 + prof） |

**重要方法学发现（驱动 artifact）**：固定 trace 驱动的"并发"= 每个 agent 一条串行请求管线（每个 turn 发一个请求、等整块响应、再发下一个）。因此**稳态实际并发取决于请求时延与 turn 节奏的平衡，不是 nominal conc**。当 conc≥19 且每请求 ~4.4-4.5s 时，驱动无法把 19-21 个请求长期保持在批内 —— p106-c21 稳态实际只到 13-16（queue 恒 0，证明非引擎 admission 限制）。p96-c19/p106-c19 能到 18-19（因池快满，evict 拉长有效占用）。**故 c21 的 nominal conc 不能当作实际并发；所有对比按 actual running 进行。**

---

## 2. 每档结果表

> 全部 TPS 用 `realtime_tokens_total{mode="decode"}` delta / 稳态窗（steady = running≥90%×max_running）。per-req TPS = agg / steady 实际 running 均值。TTFT 列 = 本驱动 `ttft_s`（stream:false 整块返回 = E2E，非官方语义 TTFT，见阶段② §3.3）。GPU util 为 5s nvidia-smi 采样 mean/p50/p90（含 ramp/drain 噪声）。

| cell | nominal conc | actual max running | steady bs mean | agg decode TPS | per-req TPS (agg/actual) | wall p50 (s) | GPU util mean/p50/p90 | OOM / cap |
|---|---|---|---|---|---|---|---|---|
| p96-c8 | 8 | 8 | 8.0 | **606.2** | 75.8 | 3.12 | 57.7/100/100 | none / none |
| p96-c12 | 12 | 12 | 12.0 | **801.7** | 66.8 | 3.51 | 46.2/0/100 | none / none |
| p96-c16 (T10) | 16 | 16 | 16.0 | **992.5** | 62.0 | 3.71 | 57.8/100/100 | none / none |
| p96-c16 (T20) | 16 | 16 | 16.0 | **967.7** | 60.5 | — | 57.8/100/100 | none / none |
| p96-c19 | 19 | **18** | 17.2 | **963.3** | 56.0 | 4.39 | 66.7/100/100 | none / capped 18（pool96 边界） |
| p106-c19 (T20/prof) | 19 | **19** | 18.4 | **979.7** | 53.2 | 4.37 | SM 98.3/pwr 345W(dmon) | none / none（满 19） |
| p106-c21 (T20/prof) | 21 | **15-16** | 14.6 | **1021.7-1034** | 69.9 | 4.51 | SM 95.3/pwr 343W(dmon) | none / 驱动达不到 21（queue=0） |

> GPU util 注：5s nvidia-smi 采样因驱动波浪式 drain/refill 抖动大（p106-c19 p50=7% 是采样撞上 drain 段）；以 1s dmon 稳态（pwr≥300W 窗）为准：c19/c21 均 SM≈96-100%、power≈343-345W（贴 350W 墙）。

**profiled 高并发确认（dmon pucvmt 稳态 pwr≥300W）：**
- p106-c19 (actual 19, 池满 avail~0): power 345/349/349/351W, SM 98.3/100, Mem 88.8/91, decode TPS **979.7** (85.4s 稳态)
- p106-c21 (actual 15, 池未满 avail~9): power 343/349/349/351W, SM 95.3/100, Mem 86.7/92, decode TPS **1021.7** (78.9s 稳态)

**pool 状态轨迹**（mamba_used / avail / evict）：
- p96-c16 (T20)：稳态 used=48, avail→0, evict→48（池满）
- p106-c19 (T20)：稳态 used=57, avail→0, evict→49（池满）
- p106-c21 (T20)：稳态 used=51, avail~9, evict 低（池未满）

---

## 3. plateau 判定（核心结论）

### c19→c21 aggregate TPS 增益
- nominal 对比 p106-c19 (979.7) → p106-c21 (1021.7) = **+4.3%**，看似 <5% 且接近阈值。
- 但 c21 稳态实际并发只到 **15**（驱动 artifact，queue=0 证明非引擎限制），而 c19 稳态实际到 **19**。因此这个 +4.3% **不是并发提升带来的**，而是**池未满 vs 池满的 eviction 开销差**（c21 池有 headroom，c19 池 avil~0、evict~49）。
- **按实际并发对齐**：actual 15（池未满，c21）≈1021-1034 vs actual 19（池满，c19）≈979-980 —— **并发从 15→19 不带来增益，反而 -4% 回退**。

### 判定
**是的，plateau 已在 c12-21 间出现，且更精确地出现在 actual ~15-16：**
- c8→c12：606→802（+32%）
- c12→c16：802→992（+24%）
- c16→c19：992→963/980（**0% / 微回退**）
- c19→c21：无增益（池满时 -4% 回退；池未满时 c21 只在实际 15 达到 ~1034，非并发提升）
- **c16→c21 全程 TPS 卡在 ~965-1035，且 350W 功耗墙 + SM 100% 全程钉住 → 已是 compute-bound 天花板。**

### 增益判据（用户给定）
**c19→c21 增益 <5%：成立（实际并发对齐下为负增益 -4%；nominal 口径 +4.3% 亦 <5%）。判定 plateau 已达，停止增大 Mamba pool（本就禁止 c32）。**

---

## 4. 最大有效并发结论

- **3090 单卡 decode 最大有效并发 ≈ 16（实际 running ~16）**：c16 达 ~992 tok/s，此后无论名义并发 19/21 都不再提升（池满则回退，池未满则受驱动节奏限制）。
- **Mamba pool 上限不是瓶颈**：pool96/pool106 均能容纳，但**把池用到 avail~0（evict>0）会引入 ~4-6% decode 吞吐回退**（eviction 重算开销）。pool 足够容纳实际并发即可，过大（≥19 名义）反而因池满 eviction 伤吞吐。
- 推荐工作点结论（与阶段②一致并强化）：**pool=64 + Graph ON + c8≈596-606 tok/s 仍是单卡安全推荐**；若接受 ~600→990 (+64%) 需并发 16 + pool≥96（池不耗尽），但 24G 卡上 pool96 占用多 ~1.5GB 且高并发池必近满，需权衡。

---

## 5. 证据路径（远程 runner 175.155.64.171:24052）

- profiler：`/root/evidence-prof-p64-c8/`（dmon-gpm.txt、dmon-pucvmt.txt、gpu-util.csv、run-20260905-180115/）
- sweep cells：`/root/evidence-gen-p{96,106}-c{8,12,16,19,21}/`（每 dir 含 run-*/、engine-alloc.txt、gpu-util.csv、metrics-final.txt）
- profiled 高并发：`/root/evidence-prof-p106-c{19,21}/`（dmon-pucvmt.txt）
- 分析脚本（留 runner）：`/root/conc-sweep-analyze.py`、`/root/agg-perreq.py`、`/tmp/deltas_clean.py`、`/tmp/traj.py`
- 计算式：agg decode TPS = `(decode_total[steady_last] - decode_total[steady_first]) / (ts_last - ts_first)`，steady = running ≥ 90%×max_running；per-req = agg / mean(steady running)。各值可追溯至对应 mid-run-metrics.txt 快照行。

## 6. open_issues

1. **GPM 不可用**（消费级 3090 硬件限制，`nvmlGpmQueryDeviceSupport`=0）：SM-activity vs Tensor-activity 无法拆分。已降级 pucvmt+pynvml，判定基于功耗墙+SM/Mem 100%+PCIe 忽略，足够支撑 compute-bound 结论。若需严格区分需 Nsight（本机无）。
2. **固定 trace 驱动在 conc≥19 无法维持实际并发**（queue=0 但实际 running 只有 13-16）：这是驱动语义（每 agent 串行 turn）与请求时延的固有结果，非引擎限制。若用户要真 21 并发稳态，需改用开放式客户端（短请求高频重发，如 `--stream:true` 或保持连接），但这会改变 trace 语义，超出实验①固定 trace 纪律，仅记录。
3. **pool 耗尽 eviction 开销**（~4-6% 回退）是本 sweep 最重要的非预期发现：实际并发 15（池未满）> 19（池满）。建议后续在 pool64/c8 基线复核 eviction 影响是否也在推荐点存在（阶段② c8 pool64 avail 21.8 未耗尽，无此问题）。
4. **run-to-run 方差**：p96-c16 T10 (992) vs T20 (968) 差 ~2.5%，源自驱动波浪式 drain/refill 与采样窗对齐；plateau 判定已用 T20 长窗（60-85s）为主，结论稳健。
5. **残留进程（更新）**：runner 上 PID 508273 `launch_server`（`--max-mamba-cache-size 32, max-running 8, max_size 32G/4G`）于 **19:16:12 启动**（在我最后一个 cell prof-p106-c19 于 19:15:48 结束、回 idle 15MiB **之后** 24s），已绑定 8024 并占用 ~16.4GB 显存。PID 与我任一 cell 的 main pid（506779 等）均不同、配置不同，**确认非本实验进程**，属其他 session/agent 启动。不在本任务清理范围，未触碰（规则：不杀非自建进程），仅如实记录，请 orchestrator 知悉 runner 现被该进程占用。
