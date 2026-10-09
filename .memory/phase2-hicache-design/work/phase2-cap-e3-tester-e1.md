# phase2-cap-e3-tester-e1 — ② ratio sweep 实测（BLOCKED: 主机 RAM 墙 + T 重标定冲突）

- Agent: tester
- Epoch: 1
- Date: 2026-09-07
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX 3090 24G, 31GB host RAM, Qwen3.5-9B-w4a16)
- Repo deploy: `/root/sglang-b1-continuity` @ 9c9e7b7c7c（scheduler md5 495b8851 == 本地 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt HEAD；kv_cache_configurator 62b040e4 同）
- 任务域：**只做** ② ratio sweep（C0-C4+可选 C5）。**未跑 ③④**；未改产品代码（新增 3 个配置/驱动脚本）。

---

## status: blocked
reason: NEEDS_REASONING — ② sweep 的启动配置（memory-computed host pools × hicache_ratio 1.5）在本机（31GB host RAM）**所有 ratio 档均物理不可 boot**（可复现、非 transient、ratio 无关 17.2GB 恒超预算 ~16.7GB）；且 T 实测 10.78 GiB 与 architect 假设 9.45 GiB 偏差 +14% > 10% 重标定阈值。
completed: 部署核验 / 驱动与 wrapper 构造部署 / C0、C3 两档 boot 实测（calibration 数据完整）
evidence: 见 evidence 节（/root/evidence-cap-sweep/calib/ + 本地 work/evidence-cap-sweep-calib/）
remaining_work: 需裁决 host 池降 ratio 或其它 boot 通路 → 重推档 → 全 5-6 档 sweep
recommended_owner: orchestrator（裁决）+ architect（按 T=10.78 重推档表）

---

## summary

### 部署核验（步骤 1）— PASS
- 引擎 9c9e7b7c7c：远程 `/root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py` md5 **495b8851**（与本地 git HEAD 相同）；`mem_cache/kv_cache_configurator.py` md5 **62b040e4**（本地同）。无产品代码改动（本 epoch 仅新增配置/驱动脚本）。
- GPU idle 0%/15MiB；/data 160G free（extent max 200G OK）；无残留引擎/lock（残留 p0fix2 观察者 bash 循环为僵尸 watcher，无 launch_server/schedul 进程）；**22151 未动**；/opt/sglang/l3-admin-key 可读。
- **dispatch 声称 "gate3_capacity.py 已部署本地/远程可用性确认" 不实**：远程无 `/root/gate3_capacity.py`，本地 3090-dev/gate3_capacity.py 的 shape（50K/80K + warm_repeats 无 180±jitter delta）与协议 §②.2 形状（H0=52-56K、delta=180±(64-256)、TURNS=20、串行 COLD prime→并发 warm）不符。按协议授权"按 shape 规范自行构造"，新建驱动 `/root/cap_ratio_driver.py`（tester 自建，仅测试资产）。

### 构造的测试资产（仅配置/测试层，未动产品代码）
| 文件 | 作用 |
|---|---|
| `/root/cap_ratio_driver.py` | ② 形状驱动：N=8、H0=54500（tokenizer 截档实测 54500，偏差 0.00%）、delta mean 179.9/152 次、TURNS=20、串行 COLD prime→并发 warm、stream:true 真 TTFT、per-req 全记录 + prefill_*_delta 交叉 |
| `/root/direct-launch-cap-ratio.sh` | FP8+graph bs8+c8+RH OFF+L3 extent 200G+**`--mamba-full-memory-ratio`**（替换原 wrapper 硬编码 `--max-mamba-cache-size 64`，ratio 路径，§②.0） |
| `/root/cap-ratio-run.sh` | 每档 runner：fresh namespace boot→驱动→采集 boot/mid/final metrics→SIGTERM→确认 idle |

### C0 标定实测（核心证据）
**C0 (r=0.90) boot：GPU 池分配成功，host 池分配失败**
```
[18:29:22] Mamba Cache is allocated. max_mamba_cache_size: 106, conv 0.12GB, ssm 5.02GB
[18:29:22] KV Cache is allocated. dtype: fp8_e4m3fn, #tokens: 376091, K 2.87GB, V 2.87GB
[18:29:43] max_total_num_tokens=376091, available_gpu_mem=0.82GB
[18:29:43] Allocating kv hierarchical KV host pool: 564137 tokens, 9.24 GB
ValueError: Not enough host memory available. Requesting 8.24 GB but only have 7.53 GB free. (mamba host pool)
```
复现 2 次（18:29、18:43）完全同值（7.53GB）→ **确定性**，非 transient。

### C3 (r=0.33) 实测
```
[18:54:14] Mamba Cache is allocated. max_mamba_cache_size: 55, conv 0.06GB, ssm 2.62GB
[18:54:14] KV Cache is allocated. dtype: fp8_e4m3fn, #tokens: 536435, K 4.09GB, V 4.09GB
[18:54:36] Allocating kv hierarchical KV host pool: 804653 tokens, 13.18 GB
ValueError: Not enough host memory available. Requesting 4.28 GB but only have 3.53 GB free. (mamba host pool)
```

### T（rest memory）标定 — 与 architect 假设偏差 +14%
由两档**相互独立地**反解 T（mamba 式 `预算=T·r/(1+r)`，per_slot=48.9MiB）：

| 档 | r | slots | KV tokens | T 反解 |
|---|---|---|---|---|
| C0 | 0.90 | 106 | 376,091 | **10.79 GiB** |
| C3 | 0.33 | 55 | 536,435 | **10.78 GiB** |

→ **T_实测 ≈ 10.78 GiB**（两档 0.1% 内一致）。architect 假设 T≈9.45 GiB → **偏差 +14% > 10% 重标定阈值** → 按协议 §②.1/§②.4 必须重推档。推论：协议预测表整体偏低 ~8-15%（e.g. C3 预测 498K/51 slots vs 实测 536K/55 slots）。

### Host-RAM 墙 — ratio 无关，全档阻塞
Host 池尺寸 = device_pool × hicache_ratio(1.5)×1.61(padding)。分配次序：**kv host 先（成功）→ mamba host 后（在剩余 budget 上检查失败）**。实测两档均吻合模型：
```
pre-kv budget ≈ 16.7 GB（= psutil available 26.7 - reserve 10，波动 ±0.1）
kv host 成功 → 剩余 budget = 16.7 - kv_host
mamba host 需 ≤ 剩余 → 失败当 mamba_host > 16.7 - kv_host
```
因 **kv_host + mamba_host ≈ 1.61×device_total ≈ 17.2 GB（= 1.61×10.78，ratio 无关恒值）> 16.7 GB 预算**，故 r∈[0.9,0.15] **所有档 total host 恒超 0.5GB**，mamba host（第二分配）在剩余 3.5-7.5GB budget 上均失败（除非 mamba_host ≤ ~3.5GB 即 r≤~0.2 且 kv_host ≤ ~13GB 的极窄窗，但 total 17.2 恒 > 16.7 仍失败）。**任何 ratio 档均不可 boot。**

对照 ledger 1589 / mamba-sizing-e1：既往 478K 成功用 **显式 max-mamba-cache-size 64**（mamba host 5GB → total 16.75GB 恰好 fit，且 479/480K 偶发 host RAM 失败 4.25-4.99GB 波动）。本 sweep 走 ratio 路径（协议 §②.0 要求），mamba device 池大（106 slots@0.9）→ mamba host 8.24GB → total 17.5GB 超出。**协议选择 ratio 路径（以观测 memory-computed 池）与已知 host-RAM 墙冲突** —— 协议未继承 ledger 1589 的 boot 约束。

## evidence
- 远程：`/root/evidence-cap-sweep/calib/`（c0-engine.log、c3-engine.log、CALIBRATION.txt、status logs）；`/root/cap_ratio_driver.py`、`/root/direct-launch-cap-ratio.sh`、`/root/cap-ratio-run.sh`
- 本地副本：`work/evidence-cap-sweep-calib/`（同内容）+ 本报告同目录 3 个脚本。
- 源码佐证：`kv_cache_configurator.py:2124-2157`（ratio 预算/分档式）、`:2075-2081`（显式 size 绕过 ratio）、`pool_host/base.py:51-58`（PSUTIL_AV 预算 = available - 10GB 保留）、`pool_host/{base,mamba}.py:84,101`（host=×ratio，超额 raise）、`hybrid_pool_assembler.py:729-733`（mamba host 按 device×ratio）。
- ledger 权威先例：ledger.md:1589-1591（host RAM 31GB 是 KV pool 瓶颈，max 478K，479+ 失败于 available 波动 4.25-4.99GB）。

## 环境复原
- namespace `/data/l3/p2io-cap-ratio-{c0,c3}` 已清 + rmdir；/data 回 160G free。
- GPU idle 0%/15MiB；无残留引擎/锁（/tmp/p2io-cap-ratio-* 空）；无 cap-ratio/launch_server/schedul 进程；8024 端口空；**22151 未动**。
- 引擎日志保留：`/root/engine-cap-ratio-c0.log`、`/root/engine-cap-ratio-c3.log`（boot 失败段）。

## followups
- **① 裁决 host 池通路**（orchestrator/authorization）：sweep 能否把 `hicache_ratio` 从 1.5 降≈1.3（host total 17.2→14.9GB，可 boot）？此为**仅 host/L2 侧改动**——sweep 主判据（device KV pool tokens、mamba slots、c8 活性）不受 host 池大小影响，但更改协议 §②.0 固定基线（cross-run 可比性 + 长尾 L2 行为），需 architect 确认不改变 ② 语义。备选：显式 `--hicache-size`（GB）控制 host 池（§②.0 未用），或重跑显式 max-mamba-cache-size 路径（违背协议 ratio 观测要求）。
- **② T 重推档**（architect）：按 T=10.78 GiB、per_slot=48.9MiB、cell=15.27KB 更新候选档表（见下节预测），再分派 tester 跑。
- **③ ratio-NO-OP 提醒**：ledger 1589 记录"显式 max-mamba-cache-size 下 ratio 全 NO-OP"。本 sweep 走 ratio 路径（未设显式 size），ratio 有效（C0 106 slots vs C3 55 slots 实证差异）——与既往结论不冲突（既往是显式 size 分支）。

## 按 T=10.78 GiB 重推档预测（供 architect 复核，不裁决）
| r | slots | KV tokens | total host |
|---|---|---|---|
| 0.90 | ~105 | ≈372K | 17.2GB FAIL |
| 0.60 | ~83 | ≈441K | 17.2GB FAIL |
| 0.50 | ~74 | ≈471K | 17.2GB FAIL |
| 0.45 | ~69 | ≈487K | 17.2GB FAIL |
| 0.40 | ~63 | ≈504K | 17.2GB FAIL |
| 0.33 | ~55 | ≈534K | 17.2GB FAIL |
| 0.30 | ~51 | ≈543K | 17.2GB FAIL |
| 0.25 | ~44 | ≈565K | 17.2GB FAIL |

→ **KV 覆盖目标 400-480K 在 r≈0.4-0.55 区间**（r*=候选 0.45-0.50），但识别 host 墙前一切 boot 均失败。

## open_issues
- 无产品缺陷。阻塞为**环境（host RAM 31GB）× 协议启动配置（ratio 路径 + hicache_ratio 1.5）不可兼得**——协议未继承 ledger 1589 已知 host 墙。
- dispatch 声称 gate3_capacity.py 已部署与实际不符（本 epoch 已按协议自建形状驱动；若 orchestrator 后续仍要用 coder 驱动，需先部署其 gate3_capacity.py）。