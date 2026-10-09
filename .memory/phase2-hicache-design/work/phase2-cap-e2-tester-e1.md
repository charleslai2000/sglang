# phase2-cap-e2-tester-e1 — ② 容量 sizing 第 1 步：FP8 KV on 3090 可启性 + 观测基线

- Agent: tester
- Epoch: 1
- Date: 2026-09-07
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX 3090 24G, Qwen3.5-9B-w4a16)
- Repo deploy: `/root/sglang-b1-continuity`（editable）@ commit 9c9e7b7c7c（scheduler md5 495b8851，与本地 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt HEAD 相同）
- 任务域：**只做** FP8 KV 可启性 + 容量基线观测；不做 ratio sweep / 50-80K 并发 / parked；不改产品代码

> 运行中收到 orchestrator 判据修正（用户 2026-09-07 权威裁决）：402-480K 目标口径变更 —— **禁止 kv_used+mamba_used 聚合**；业务目标 = **attention KV working set**（c8 下 8 个 ~50-60K active Agent 的 attention KV resident capacity，避免互相 eviction/recompute）。Mamba state 是 per-active-sequence slot，不折算进 400-480K 指标。基线观测**分列输出**（8 项，见 §4），attention KV 为主判据列，mamba 为独立约束列。本报告已按修正后口径撰写。

---

## status: done

## artifacts
- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`
- 启动 wrapper（新增，仅配置层）：runner `/root/direct-launch-cap-fp8.sh`（md5 b97728cd…）；本地副本 `/tmp/direct-launch-cap-fp8.sh`
- 运行驱动（新增，仅配置层）：runner `/root/cap-fp8-run.sh`（md5 02d66e22…）；本地副本 `/tmp/cap-fp8-run.sh`
- 运行证据（runner 保留）：
  - `/root/evidence-cap-fp8-e2t/`（boot-metrics.txt、metrics-final.txt、gpu-util.csv、engine-alloc.txt、engine-events.txt、run-20260907-171921/{runs.csv,mid-run-metrics.txt,verdict.json,join.log}）
  - `/root/engine-cap-fp8-e2t.log`（引擎日志，8.5K 行）
  - `/root/cap-fp8-e2t-status.log`、`/root/cap-fp8-e2t-outer.log`

## evidence（每结论原始数据）

### 部署状态核对（步骤 1）
- 引擎 = 9c9e7b7c7c：editable 路径 `/root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py` md5 = **495b88515cc2e932c57448359443604d**（本地 git 9c9e7b7c7c 同文件 md5 一致）；test_hicache_restore_scheduler_feed.py md5 = **465b6c68ce813b0522200ac96fea0828**；关键方法 `_miss_rearm_decision` present=2 / `_miss_rearm_durable_coverage` present=4。
- 备份 `.bak-round2-pre` 保留：scheduler e1b749956459…; test c94a55db…（与 round2 一致）。
- 其余生产文件未动；**无产品代码修改**（本次仅新增配置脚本）。
- FP8 支持面确认（代码层）：`server_args.py` `fp8_e4m3` choices 在列；kv_cache_dtype.py fp8_e4m3 → torch.float8_e4m3fn；torch 2.13.0+cu130 `float8_e4m3fn` 存在；CUDA 13.0 / driver 580.173（≥ CUDA 11.8 门槛）。FC8 KV 解析独立于 cuda-graph/batch 选择（scout Q1 复核实）。
- FP8 生效确认（运行层，engine log）：`'kv_cache_dtype': 'fp8_e4m3'`；`Using FP8 KV cache but no scaling factors provided. Defaulting to scaling factors of 1.0. This may lead to less accurate results!`（17:13:25）；`KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 448000, K size: 3.42 GB, V size: 3.42 GB`（17:13:44）。

### FP8 可启性 run（步骤 2）— PASS（272 requests 服务证据）
- 配置：FP8 KV(`fp8_e4m3`) + pool64(`--max-mamba-cache-size 64`) + CUDA Graph bs8(`--cuda-graph-max-bs 8`) + c8(`--max-running-requests 8`) + RH OFF + L3 extent（`hicache_storage_backend_extra_config {"max_size":"200G","min_free_space":"10G"}`, waite_complete prefetch, write_back, hicache_ratio 1.5）+ `--max-total-tokens 448000`. MODEL Qwen3.5-9B-w4a16。
- 启动：17:11:55 launched → 17:19:16 **engine healthy HTTP 200**（boot ~7.3min，含 prefill CUDA graph capture 312.5s）。ExtentFileBackend OK（slots=447, max_size 200G, min_free 10G）。**无启动 config error**。
- 推理：**272/272 HTTP 200**，**272/272 finished=True**，**output_sha16 非空 272/272**。rc=0。
- 正确性四项：**0 CUDA OOM / 0 BackendError / 0 EngineError / 0 Scheduler exception**。引擎日志 62 处 Traceback 全部为良性 torchcodec/libavutil FFmpeg 探测（启动段 lines 30-620）+ 1 处 SIGTERM 正常关停（uvicorn SystemExit:0，17:25:45）。
- 数值：候选对照 —— device_hit 总 2,961,908 tokens（139 req，max 34,796）、host_hit 总 2,854,696（128 req，max 32,951）、storage_hit 2,496（3 req）；Phase B（restore/read）ttft p50=0.5s / p90=6.2s —— 表明 FP8 KV 在 flashinfer+triton linear attention 路径下 cache 命中与恢复数值未崩坏（恢复出的前缀可正常解码，host_hit 2.85M tokens 走 FP8 恢复展示数值路径正常）。默认 scale factor 1.0 警告如实记录（fp8 无 scaling factors 时 =1.0 近似，属已知近似，非 error）。
- GPU：util mean 89% / active-mean 96% / p90 100%；mem mean 22.8GB/24G（95%）。

### 容量基线观测（步骤 3）— 分列输出（用户修正后口径）

**8 项分列**（同一 run：8 agents × 4 write + 30 read-turns，drives 272 req，6.25 min 实际 run 窗）：

| # | 项 | 值 | 证据 |
|---|---|---|---|
| 1 | resolved attention KV capacity tokens | **max_total_num_tokens=448000**（= 请求值，memory-computed 容量 ≥448K）；运行时 kv_used **max=341,818 / p90=216,244 / p50=102,347**；kv_available min=163（池未耗尽，最低时仅剩 163 空闲）；kv_evictable p50=268,821 / max=440,141 | boot/final metrics + mid-run |
| 2 | KV bytes | **K 3.42GB + V 3.42GB = 6.84GB**（dtype torch.float8_e4m3fn, 448000 tokens）；kv_cache_memory_usage_gb=6.84 | engine log 17:13:44 |
| 3 | Mamba pool slots | **max_mamba_cache_size=64**（显式）；mamba_available 终态 12；mamba_evictable p50=40 / max=53；终态 avail 12+evict 52=64；mid-run mamba_used_tokens gauge 无值（0 时不发射，瞬时锁定 slot 量，见 note） | metrics-final + mid-run |
| 4 | Mamba bytes | **ssm_state 3.05GB + conv_state 0.07GB = 3.12GB**（float32） | engine log 17:13:43 |
| 5 | max effective active requests | **8/8 达到**（num_running_reqs max=8；p50=3）；24G 上 c8 实际跑满；单 req prompt max 43,514 tokens | mid-run running + runs.csv |
| 6 | CUDA Graph 占用 | **prefill 0.64GB / decode 0.08GB**（graph bs8）；prefill graph capture 312.5s（boot 大头） | boot-metrics graph_memory_usage_gb + engine log |
| 7 | free VRAM | **startup_available_gpu_memory_gb=1.74GB**（post-capture）；运行期 mem mean 22.8GB/24G；无 OOM | boot-metrics |
| 8 | c8 真实可运行 | **是**：running max 8，272/272 HTTP 200，GPU active-mean 96%，decode graph bs8 已捕获 | mid-run + runs.csv + gpu-util |

**对照 non-FP8（soak bf16 2h，同脚本口径）**：

| 指标 | non-FP8 soak (bf16, pool~106) | FP8 本 run (pool64) | 说明 |
|---|---|---|---|
| max_total_num_tokens | 65536（cap=请求值） | **448000** | FP8 池大 ~6.8x（部分也因 pool64+higher request） |
| KV bytes @448K | 不可行（bf16 448K≈13.7GB） | 6.84GB | FP8 精确减半 |
| kv_used max | 64851（65536 池内） | 341,818（448K 池内） | 本 run 负载 active working set 345K；池未耗尽（avail min 163） |
| mamba pool | ~106（ratio 默认） | 64（显式） | pool64 为生产 base |
| mamba bytes | ~5GB（106 slots float32） | 3.12GB（64 slots） | |
| GPU mem | 20.3GB mean | 22.8GB mean | 448K FP8 KV 吃掉更多显存 |

> note: mid-run 快照 `sglang:mamba_used_tokens` / `mamba_available_tokens` 无展开值（该 build 对瞬时锁定 slot gauge 在 0 时只发 HELP/TYPE），终态 metrics-final 有 avail/evict。mamba used 可由 avail+evict=64 隐含（used=0 终态）。

### DQ / restore timeout / 长尾（本 run 短窗口对照）

- **DQ（DEVICE_QUOTA WAIT_CAPACITY）≥55s：0 次**；全部 11 次 WAIT_CAPACITY 均 reason=FRONTIER（非 DEVICE_QUOTA）。原因：448K 池相对负载充足（avail min 163 但未到 0），无容量排队 → 无 DQ。
- **restore_recompute cause=timeout：1 次**（17:24:48，final_storage_survivability=host）；restore_recompute 总 78。对照 soak 2h=66 次 timeout —— 本 run 6.25min=1 次，量级显著更低（池大头下 restore 竞争少）。
- **restore_success=3**（n_tokens 1280/832/384）；extent_write=714；forced_drop=0；prefetch_issued=81。
- **TTFT 长尾**：≥55s = **1/272**（run-minute 4，冷写阶段）；>60s = 1/272；TTFT p50=0.6 / p90=13.2 / p99=45.5 / max=61.7s。对照 soak p99=83s。
- Phase A（write, 冷长上下文）ttft p50=22.8 / max=47.2s；Phase B（restore/read, cache hit）ttft p50=0.5 / max=61.7s。

### 环境复原（步骤 4）
- /data 实验命名空间 `/data/l3/p2io-cap-fp8-e2t`（14G）已清 → /data 回 15%（160G free）。
- GPU idle 0%/15MiB；无残留引擎/lock（/tmp/p2io-cap-fp8-* 空）；无 sglang/launch_server/gate2/cap-fp8 进程（jupyter-lab 为系统常驻）。
- 部署 md5 复核不变（scheduler 495b8851 / test 465b6c68 / .bak-round2-pre 保留）；22151 未动。

## summary

**FP8 KV on 3090：PASS（可启动、健康、推理正确、数值未崩坏）。**
- 代码层支持面（scout Q1）实测兑现为运行层：`dtype torch.float8_e4m3fn`，**448K tokens KV = 6.84GB（FP8 减半直接实证）**；c8 实跑满 8 running；272/272 HTTP 200 无任何 error；device_hit 2.96M / host_hit 2.85M tokens 表明 FP8 KV 在 flashinfer+triton 路径下 cache/restore 数值正常（恢复前缀可正常继续解码）。
- **容量基线（修正后口径，分列）**：attention KV working set 在 448K 池下实测峰 **341,818 tokens**（p90 216,244），池可用 min 163（未耗尽 → 无 DQ≥55s / 仅 1 次 restore timeout）；mamba 64 slots = 3.12GB 独立列。
- 对 ② ratio sweep 起点（**事实，不推方案**）：本 run 已在 pool64 + FP8 下实测 attention KV working set 达到 **~342K**（8 × 平均 ~43K 长上下文 write 后的残留 resident）；→ "c8 下 8 个 ~50-60K active Agent" 的 400-480K working set 目标 = 需每 agent 更长历史（~50-60K）或更多 resident，当前负载形状（gate2 采 L0-L3 21-44K）落在 342K，**处于 400-480K 目标之下 ~17-29%**。sweep 时若收 max_total_tokens=448K 为 memory-computed 可容纳上限（未观察到 clamp warning），每档 ratio 只需扫 mamba 预算对 working set 的影响，不改变 attention KV 池上限；观察游标 = kv_used（attention KV working set），mamba 列（used/avail/evict + max 64）作约束。

## followups
- ② sweep 下一步：在 pool64+FP8+bs8+c8 上扫 `--mamba-full-memory-ratio`（默认 0.9 为起点），attention KV working set 为主判据（kv_used max/p90），mamba 独立列；负载需调长历史形状至每 agent ~50-60K 以对齐 400-480K 目标区（当前 gate2 L0-L3 只推 ~342K working set）。
- FP8 scale factor=1.0（default，无 scaling factors）为已知近似项，若 ② 需更高数值精度可评估（非阻塞，需真实正确性基准才确认影响）。
- prefill CUDA graph capture 312.5s 是 boot 大头；sweep 多次重启会重复支付（认知成本，非缺陷）。

## open_issues
- 无产品缺陷。FP8 在 3090 + flashinfer/triton 路径数值**无崩坏**（host_hit 2.85M tokens 恢复路径正常解码）；但"数值精确性 vs bf16"未做逐 token 比对基准（超出本任务范围；仅确认无 decode 崩坏/assert/OOM/BackendError）。
- mid-run 快照 mamba_used_tokens gauge 在 0 时不展开值（终态 avail/evict 隐含 used=0）；若 sweep 需 mamba used 全程轨迹，可用 metrics-final + engine log（mamba usage per batch）交叉，或确认该 gauge 在 used>0 时是否发射（本 run 未捕获到 used>0 窗）。
- 单次 6.25min run；DQ≥55s=0 / timeout=1 的量级对照 soak（2h, 66）成立（池大头少竞争），但长期 DQ 稳定性需 sweep 阶段更长 run 复核。

## claim 判定
```text
claim: FP8 KV (fp8_e4m3) 在 3090 真卡可启动、可推理、无 error，并给出现有配置（FP8+pool64+graph bs8+c8+RH OFF+L3 extent, max_total_tokens=448000）的分列容量基线
verdict: confirmed
basis:
  - 部署 9c9e7b7c7c（md5 495b8851/465b6c68）核实；无产品代码改动
  - FP8 生效：server_args fp8_e4m3 + KV Cache dtype torch.float8_e4m3fn 448000 tokens 6.84GB；engine healthy 200
  - 推理正确：272/272 HTTP 200, finished=True, output_sha16 非空；0 OOM/BackendError/EngineError/assert；62 处 Traceback 全为 torchcodec 启动噪声 + SIGTERM 正常关停
  - 数值：device_hit 2.96M + host_hit 2.85M tokens 恢复路径正常（FP8 未崩坏）；Phase B ttft p50 0.5s
  - 容量分列（修正口径）：attention KV max_total=448000, kv_used max=341818/p90=216244, 池 avail min=163（未耗尽）; KV=6.84GB; mamba 64 slots=3.12GB; running max=8; CUDA graph 0.64+0.08GB; free VRAM 1.74GB; c8 可运行=是
  - 长尾: DQ≥55s=0; restore timeout=1; TTFT>=55s=1/272; GPU active-mean 96%
limitations:
  - 单次 6.25min 短 run; DS≥55s=0 的绝对次数少, 与 soak(26/2h) 的长期对照需 sweep 阶段更长窗口
  - "数值正确"限定为"无 decode 崩坏/缓存恢复路径正常", 未做 vs bf16 逐 token 精度基准（FP8 scale-factor=1.0 默认近似已记录）
  - mamba_used 瞬时轨迹受 gauge 发射条件限制, 使用 avail/evict 隐含
  - attention KV working set 峰 341.8K < 400-480K 目标区: 因负载每 agent 历史 L0-L3 仅 ~21-44K, 非池容量不足（池可用 min 163）
```