# phase2-cap-e5-architect-e1 — ④ parked 按 Gate A/B/C 全量验收 spec（executable）

- Agent: architect
- Epoch: 1
- Date: 2026-09-07
- Scope: **纯设计（只读）**。把 ④ parked fleet 的 Gate A / B / C 三个硬 Gate 编排为 tester 可直接照跑的 executable spec：门-实验映射、Gate B 四层分层测量表、Gate C RH 兑现、S=500/1000 oversub stress、执行序与 GPU 预算、对 ④ 驱动（coder 正在改）与 tester 的 dependency 清单。与 ③(Gate D) spec（`work/phase2-cap-e4-architect-e1.md`）正交衔接，**不重复判断 Gate D**。不跑 GPU、不改产品代码、不实现驱动。
- 输入（Read 引用，未重新侦察）：ledger.md:2488-2536（用户 4 Gate 权威裁决 + parked 两档）；`work/phase2-cap-protocol-architect-e1.md` §④（旧两语义协议）；`work/phase2-cap-e4-architect-e1.md`（③ spec 格式参照）；`work/phase2-load-driver-design-coder-e1.md` 与 **`3090-dev/gate3_parked.py` 现行树**（coder v2 修改目标已落在树上，本 spec 以该目标为准设计）；`work/phase2-cap-e2-tester-e1.md`（e2 基线）；`work/phase2-hicache-design-tester-rh-ab-e2.md` / `-e1.md`（RH A/B 先例）；`work/phase2-rhfix-tester-e1.md`、`work/phase2-rhfix-architect-e1.md`（RH 容量行为先例）；源码核对（ready_horizon.py / scheduler.py / extent_allocator.py / extent_file_backend.py / server_args.py）。
- Repo（只读）：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt` @ 9c9e7b7c7c（24052 部署 md5 495b8851/465b6c68）；真卡 24052 `ssh -i ~/.ssh/id_ed25519 -p 24052 root@175.155.64.171`。

---

## status: done

## artifacts
- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e5-architect-e1.md`

## evidence（文件:行 或 源码路径）

| 事实 | 出处 |
|---|---|
| 用户 4 硬 Gate 权威裁决全文（A/B/C/D + parked 两档 + 执行影响；③ 判据作废旧表） | ledger.md:2488-2536 |
| Gate A：L3-fit 时历史不得重算；允许=本轮新增+Mamba TRAILING_PAGES tail 少量重算；禁止=50K/100K 历史重新 prefill / storage-resident→revoked:miss→full recompute / DEVICE_QUOTA/frontier/admission 导致的重算；**avoidable historical recompute rate=0%** | ledger.md:2493-2497 |
| Gate B 分层 TTFT 目标表（GPU 1/2、Host-ready 1.5/3、RH-staged 2/4、L3 on-demand 3/6、任意 hit p99≤10、>30s/>60s=0） | ledger.md:2499-2509 |
| Gate C：Host-ready-before-admission ≥95%、RH ON vs OFF p95 显著下降、L3 sync restore wait 显著下降、historical recompute 不增、无提前 recycle/Host starvation/L3 写放大/capacity deadlock | ledger.md:2511-2515 |
| Parked 两档：S=100=L3-fit 正式产品验收（recompute=0、p95≤5/p99≤10、storage-hit 稳定、无 recycle）；S=500/1000=显式超配退化曲线（允许 recycle、每次 full recompute 可解释为容量淘汰、禁宣称完整驻留） | ledger.md:2531-2535 |
| ④ 旧两语义协议（S∈{100,500,1000}×H0=55K、active 恒 8、禁 WAIT/pause、age bucket、R1 L3/磁盘预算） | protocol-e1:198-227,243-256,271,287 |
| e2 基线：FP8+pool64+graph bs8+c8+RH OFF+L3 extent 200G；kv_used max=341,818/p90=216,244、池 avail min=163、KV 6.84GB@448K、mamba 64 slots=3.12GB、running max 8、DQ≥55s=0、restore timeout=1、Phase B restore ttft p50=0.5s / TTFT p99=45.5s | e2-tester:44-76,107-116 |
| warmctx 锚：64K 历史 warm TTFT p50=0.45s 全 device-hit（prefill_input 7-33 = 仅新 delta）→ "每 turn 重发全历史"是 resident 驱动形状；COLD 预填 64K≈19s/128K≈47s | warmctx-e1:27-31,47-49 |
| RH A/B：共同 recycle=0 clean window 内 RH ON storage_hit 2.26x、recompute 0.51x、restore_success 持平 → RH 状态机**无独立缺陷**；首 recycle A=314.5s/81.6GiB vs B=126.5s/30.4GiB；recycle 后 ready_pool 永久冻结 + restore_success→0 = thrashing feedback 根因 | rh-ab-e2:88-123 |
| 磁盘 GC confound：冻结/恢复由 min_free 跨越 + 纯容量耗尽驱动（str-bl 存活 / str-fx2 崩溃 backup assert）；`MAX_SIZE=200G FILE_SIZE=30G` 为"大 extent 小 cursor"压力档先例 | rhfix-tester:37-75,139-145,193-208 |
| ③ spec（格式参照 / 正交边界）：③=Gate D，N={4,6,8}×55K、输出固定 256、aggregate≥500、TTFT p50/p95/p99≤2/5/10、c8 内 55K 挡 working set 444-467K ≤ 498K 池 | e4-architect:57-77,161-186 |
| 驱动 v2（当前树已含）：`--mode fit|oversub`、`--rh on|off`、`BUILD_TIERS` 含 55k 且 default=55k、`L3_FIT_SESSIONS=170`/`FIT_SESSIONS=100`/`OVERSUB_SESSIONS=(500,1000)`、`classify_hit_parent`（GPU-resident/Host-ready/RH-staged/Host-ready-STAGED/L3-on-demand/miss）、recompute 归因（capacity_evicted/state_machine/other）、`eviction_observed` coarse sampler、verdict.json semantic_caveats | gate3_parked.py:145-161,318-348,435-617,636-666,735-748,795-832 |
| 驱动仍缺（本方 dependency）：**park window 梯（cohort 制造四层状态）与 `--build-workers` 并发 COLD build**；`--rh` 的 docstring 明言"engine 能否 toggle RH 是 launcher 依赖，tester 验 24052" | gate3_parked.py:684-688 |
| 引擎 ready-horizon 入口 flag `enable_ready_horizon`（NS memory, default False） | server_args.py:2866 |
| 引擎侧事件格式（rid 可 join）：`evt=ready_stage rid result state ready headroom`(:3455)、`evt=ready_pool size tokens watermark`(:3487)、`evt=restore_recompute rid cause final_storage_survivability`(:3325)、`evt=restore_state rid state reason`(:3378)、`evt=restore_ready rid`(:3303)、`evt=admission rid pos qlen running_bs can_run`(:4726)、`evt=restore_success rid n_tokens`(:4779)；`evt=extent_recycle slot generation freed`（extent_allocator.py:212）、`evt=extent_write node component`（extent_file_backend.py:379） | scheduler.py + extent 源码 |
| ready_horizon staging 机制：frontier=waiting_queue 前 N、`staging_candidates`/`refill_plan`/`headroom_fits`/NO_HEADROOM declines、watermark LOW/HIGH | ready_horizon.py:256-545 |
| mamba ratio NO-OP 结论：显式 max-mamba-cache-size 时 ratio 完全无效；④ 引擎配置继承 ② 定稿并须核对 mamba slots / KV 池与 c8 | mamba-sizing-tester:53-57；取 ② 输出 r* |
| ④ 驱动力学缺口：顺序 COLD build 1000×55K 将耗 hours 级（128K 先例 47s/次）→ 必须并发 build | coder-e1:open_issues-3 |

---

## summary

## Conclusion（先行结论）

1. **④ 按用户 4 Gate 重排 = 五个 GPU 阶段**：Gate A/B 共用 **S=100 fit 两次启动（RH OFF 基线 + RH ON 正式）**，同一 seed/同一 park 梯 → 一次测量同时产出 Gate B 四层表（OFF 臂取 GPU/Host/L3-on-demand；ON 臂取 RH-staged）；Gate C 复用同一对 run 的引擎事件；Gate D 由 ③ 承担（本 spec 不含）；Oversub stress = S=500/1000 各自 RH OFF/ON（ON 为可选）。
2. **Gate B 四状态需要"故意制造"**：驱动现为 uniform park 窗，无法保证每层样本 → **park 梯（cohort 窗带）+ `--build-workers` 是唯二新驱动依赖**，其余全部落在已修改的 v2 驱动上（fit/oversub、RH 档、hit 标签、归因表、eviction 采样均已具备）。
3. **Gate C 的 Host-ready-before-admission 判定必须走引擎事件**（driver 的 RH-staged 标签是粗代理，含永久化 bias）：join `restore_ready`/`ready_stage`/`admission` 的时间戳；**tester 须在 24052 先验事件可用性**（P2A trace 是否默认开、rid 是否与驱动 SSE rid 一致），这是 Gate C 的最大未决前置。
4. **Oversub 的容量档位与 S=100 相反**：S=100 fit 需大 FILE_SIZE 保证 0 recycle（≥120G 且 /data 可容纳）；S=500/1000 需**小 FILE_SIZE（30G 级）**使 cursor-wrap 在 45-60min 内反复出现、物理盘驻留受控——这正是"测退化曲线"的机制实现。
5. **合格条件（state_machine=0）不是逐事件硬判而是归因闭环**：driver 初判 + analyze 用 engine `extent_recycle` 事件对每次 full recompute 复核（recycle 必须先于 recompute、session 先有 L3 durable），得出终判；曲线本身非 PASS/FAIL。

---

## 1. Gate A → S=100（capacity-fit 正式验收）

### 1.1 前提条件（S=100 只能在这些成立后开跑）

1. **② 已完成**，输出 `r*`（推荐 0.33，区间 [0.30,0.45]）与全套频率级判定；④ 继承 ② 定稿 engine 配置（protocol-e1:162-164）：
   ```
   kv_cache_dtype=fp8_e4m3
   --cuda-graph-max-bs 8
   --max-running-requests 8        （active 定值 = engine c8）
   --mamba-full-memory-ratio=r*    （② 输出；注意 mamba-sizing 已证"显式 max-mamba-cache-size 时 ratio NO-OP"，④ boot 必须核对解析出的 mamba slots / KV 池）
   --enable-hierarchical-cache + write_back + wait_complete prefetch + hicache-ratio 1.5
   L3 extent backend：max_size=200G；**FILE_SIZE（cursor 容量）≥ 120G**（见 1.4 项 3）；min_free=10G
   不设 --max-total-tokens（memory-computed 池 ≈498K @ r*）
   ```
2. **③(Gate D) 已完成**：③ 输出 effective concurrency（c8 或降级点）与 Gate D 全套判据；④ active=8 与 ③ 的 c8 结论一致即开；若 ③ 判定降 c6，④ active 需同步改为 6（本 spec 以 c8 为主写，降级时替换 `--active` 与 engine c）。
3. 24052 空闲（GPU 0%/15MiB、零残留/锁）、deploy md5 复核（scheduler 495b8851 / test 465b6c68）、/data fresh namespace、`/data free ≥ FILE_SIZE+20G`。
4. 驱动 v2 已就绪（mode/rh/55k/归因/ladder/build-workers，见 §6）、`gate3_parked_analyze.py` 已就绪（Gate B 分桶 + Gate C engine-join + oversub 矩阵）。

### 1.2 档位参数模板（RH OFF / RH ON 各一次；唯一的档间差异 = engine RH toggle）

| 参数 | 值 | 说明 |
|---|---|---|
| `--mode` | `fit` | 正式 L3-fit 语义（verdict 打 `l3_fit_formal_capacity_test_S100` caveat） |
| `--sessions` | `100` | S=100 锚点（200G extent @55K 容量上限 ~170，100 留裕量） |
| `--build-tier` | `55k`（default） | H0=55K 权威档（ledger:2473；驱动 BUILD_TIERS 已含 55k） |
| `--active` | `8` | engine c8 定值；**不传其它值**（本 spec 不测 active 敏感度） |
| `--rounds` | `60` | ≈ 45-60min 稳态；turns 数见 1.3 |
| `--seed` | `20260907` | **两臂同一 seed**（RH OFF/ON A/B 配对前提） |
| park 梯 | `hot=0-30@n_hot, mid=120-300@n_mid, cold=600-2400@n_cold`，`n_hot=5 / n_mid=30 / n_cold=65`（见 §6 依赖 #1；未就绪时 fallback uniform 30-900，Gate B 每层 n 事后分桶并可能 <floor） | 制造四层 hit 状态 + 保随机 resume |
| `--pick-lam` | `1.0` | turn 级 cooldown 几何均值（HOT 成员可调 2-4 防满窗，见 §1.4 项 4） |
| `--obey-ac` | 传 | 客户端并发封顶 8（不人为制造 headroom 缺口） |
| `--turn-max-new` | `256` | 输出标准档（对齐 Gate D 固定 256；④ 每 resume 同理） |
| `--build-max-new` | `12` | build COLD 短回复 |
| `--build-workers` | `8` | 并发 COLD build（顺序 build 100×55K≈25-35min，8 并发≈4-6min；见 §6 依赖 #2） |
| `--build-client-max` / `--client-max-time` | `1500` / `1200` | 55K COLD 预填保守超时 |
| `--snapshot-interval` / `--coarse-interval` | `2` / `60` | 双速率采样（coarse 带 L3 物理足迹） |
| `--l3-backend-dir` | `<fresh namespace>` | 物理足迹（st_blocks × 512） |
| `--evidence-dir` | `/root/evidence-parked-fit-55k-{off,on}` | 每臂独立 |
| RH | **引擎 flag `--enable-ready-horizon` OFF / ON** | OFF 臂 = Gate A 基线 + Gate C OFF leg + Gate B 的 GPU/Host/L3-on-demand 层；ON 臂 = Gate A 正式 + Gate B RH-staged 层 + Gate C ON leg |

### 1.3 turns / 时长估算（稳态窗定义）

- 稳态窗 = rounds 中 **排除 build 与"首次全池轮询"**（第一轮 each session 的 first-turn 为 COLD 后过渡，warmctx r1 先例 3.5-6.5s 一次性偏慢）：稳态 = round ≥ 2 之后的全部 resume 行。
- RESUME 量估算：active=8，单 turn wall ≈ warm prefill 1-2s（hit）+ decode 256 token @~75 tok/s ≈ 3.5s ≈ **4.5-5s/turn** → 满窗 ~5760 turns/h；park 梯为上限且实际受 due 集合约束，60min 实际 ≈ **1500-2500 稳态 resume**（HOT cohort 占多数，COLD≈100-150，MID≈200-400——均 ≥ 每层 floor）。
- Gate B 每层 floor：GPU-resident ≥30（目标 ≥100）、Host-ready ≥50、RH-staged ≥30、L3-on-demand ≥30；稳态窗 resume 总数 ≥ 1000。
- 时长：build（workers=8）≈5min + rounds 60min + 采closure ≈ **cell 全程 ≈ 70-75min**（含 boot 7.3min ≈ 总 80min/臂）。两臂 ≈ **2.6-2.8h GPU**。

### 1.4 判定步骤（每臂）

**Step 1 — boot + 配置核对**
- boot 后读 engine-alloc：`max_total_num_tokens`（memory-computed 值 ≥ ② 预测）、mamba slots≥c8 需要、`startup_available_gpu_memory_gb ≥1.2`、无 clamp warning（有则按 R2 规则记录退顶格）、RH flag 生效值（ON 臂 log 应见 enable_ready_horizon=true）。
- `grep extent_recycle`：**整个 fit run 必须 0 次**（build + rounds 全程）。若 build 期已 recycle → FILE_SIZE 不够，停、放大 FILE_SIZE 重跑（1.2 前置）。

**Step 2 — build**
- 100×55K COLD（8 并发）；确认每 session history_tokens ∈ 55K±2%（tokenizer 实测记录）；build 后抽查 L3 物理足迹 ≈ 100×840MB（55K×15.27KB/FP8）= **~84GB**。

**Step 3 — rounds**
- 稳态至 round 60。记录 runs.csv（含 hit_parent_mux、age_at_wake_s、prefill_*_delta）、mid-run 双速率采样、engine log 全量保留（Gate C join 用）。

**Step 4 — Gate A 判定（全 AND）**

| # | 判据 | 阈值 | 取法 |
|---|---|---|---|
| 1 | **avoidable historical recompute = 0%** | 0 次 full-history recompute；`history_recompute_tokens=0` | ① driver attribution：`recompute_attribution.csv` 中 `full_history_recompute` 事件 = 0；② `recompute_tokens = Σ max(0, prompt_len − (device+host+storage)_hit)`；③ 历史重算分量 = `Σ max(0, recompute_tokens − delta_len)`，**预期 ≈0**；④ engine `restore_recompute cause=miss|timeout` = 0（fit 下 revoked:miss 理论不可发生）；⑤ 显式禁止项各自为 0：`DEVICE_QUOTA` wait、`/pause`（驱动零调用，静态断言） |
| 2 | Mamba TRAILING_PAGES 允许项复核 | `history_recompute_tokens` 非零值**只能**解释为 Mamba trail tail | 任何非零须从 engine log 核对为 mamba checkpoint/tailing pages 重算（mamba_component TRAILING_PAGES hit_policy），并 ≤ 小界（warmctx 先例 prefill_input−delta≈0）；无法解释 → FAIL-状态机 |
| 3 | TTFT（稳态窗） | **p95 ≤ 5s** ∧ **p99 ≤ 10s** ∧ max≤60s ∧ >30s=0 ∧ >60s=0 | runs.csv ttft_s（stream:true 真 TTFT）；完整 hit 路径（含 L3 on-demand）计入 |
| 4 | storage-hit/session 稳定 | 每 session 命中率跨 turn 无异常崩 | per-session cached/prompt 分位：任 session 命中率在后续 turn 跌到 <0.9×自身中位数且无 recycle 解释 → 计 1 例异常；**异常 = 0** |
| 5 | 无 recycle | extent_recycle = 0；forced_drop = 0；write 失败 = 0 | engine log + metrics |
| 6 | 健康 | 100% finished、0 OOM/BackendError/EngineError、sha16 非空、GPU idle 复原 | runs.csv + gpu-util |

**Step 5 — verdict 输出**：每臂一张表 + 双臂并列（见 §1.5）。**Gate A 正式接受判据**：ON 臂全 AND（RH 为产品配置）；OFF 臂作为 Gate C 基线 + Gate B OFF 现实层。若 ON 臂 FAIL 而 OFF 臂 PASS（仅 p95/p99 上的差异）→ 不是容量失败而是 **RH 未兑现**，路由 Gate C/RH 处理，不静默改口径。

### 1.5 输出模板（每臂；双臂并列成表）

```
Gate A: S=100 fit（H0=55K, active=8, seed=20260907, park-ladder ✓, rounds=60）
engine: r*=<②输出>, FP8, graph bs8, c8, L3 max200G/FILE_SIZE=<值>, RH=<OFF|ON>

| arm | p50 | p95 | p99 | max | >30s | >60s | hist-recompute% | full-recompute(state_machine) | recycle | storage-hit stability | finished% | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OFF | 0.6 | 2.8 | 5.1 | 18 | 0 | 0 | 0.0% | 0 | 0 | stable | 100% | PASS(baseline) |
| ON  | 0.7 | 3.1 | 6.2 | 21 | 0 | 0 | 0.0% | 0 | 0 | stable | 100% | PASS(formal) |

hit 分布（ON arm 参考）：GPU:% / Host:% / RH-staged:% / L3-on-demand:%（token 合计 + per-req 比例）
summary: 三级 HiCache 在 S=100（L3-fit）下随机 resume historical recompute=0%、TTFT p95≤5s / p99≤10s、storage-hit 稳定、0 recycle —— Gate A <PASS/FAIL>（<解释>）
```

---

## 2. Gate B — 分层测量表

### 2.1 四层定义与触发/识别（driver `classify_hit_parent` + engine 事件复核）

| 层 | 语义 | 制造/触发（park 梯） | 识别（per-request） | 数据来源 |
|---|---|---|---|---|
| **GPU/L1 resident** | 历史驻留 device | HOT cohort（park 0-30s、pick-lam 2-4）→ turn 结束后数秒内重 pick，KV 未被其它 55K 逐出 | `hit_parent=GPU-resident`（device_hit ≥ host 且 storage=0）；age_at_wake_s 小 | driver label + `prefill_devicehit_delta` |
| **Host-ready** | 历史在 Host L2，device 已被自然逐出 | MID cohort（park 120-300s）→ device 被后续 active 55K 压出、写 L2 | `hit_parent=Host-ready`（host_hit>0、storage=0、**RH OFF 臂** 或 ON 臂但无 L3 先例） | driver label + `hicache_host_*` gauge |
| **RH-staged** | L3 由 RH 提前 staging 到 Host，admission 前已 ready | COLD cohort（park 600-2400s）+ **RH ON 臂** | 驱动代理：`hit_parent=RH-staged`（host_hit + rh=on + 该 session 曾有 storage hit）；**终判走引擎**：该 rid `restore_ready`/`restore_state=READY` 时间戳先于 `admission`（→ Gate C §3 复用） | driver label（采样）+ engine 事件（裁决） |
| **L3 on-demand** | 同步 L3 extent restore | COLD cohort + **RH OFF 臂**（RH 未预先 staging → storage 直读） | `hit_parent=L3-on-demand`（storage_hit>0） | driver label + `prefill_storagehit_delta` |

> **代理 bias 声明**：`classify_hit_parent` 的 `session_has_storage_hit` 为 session 级永久旗标（once-true-stays-true）→ RH-staged 标签**可能 over-claim**（后续 host hit 未必真是 RH staging）。**采样结构性使用 driver label；每层 verdict 的"已 ready"事实必须由 engine 事件确认**（Gate C §3.3 的 rate 计算即该确认）。Gate B 的 RH-staged 行若非引擎确认 → 降级标注 "Host-ready(疑似 staged)"，不冒充。

### 2.2 最小样本量与统计

- **每层 floor**：GPU-resident ≥30（目标≥100）、Host-ready ≥50、RH-staged ≥30（ON 臂；COLD cohort≈65×~2.4 wakes ≈150，floor 可达）、L3-on-demand ≥30（OFF 臂 COLD）。
- 统计口径：TTFT 用 稳态窗（§1.3）；per-layer p50/p95 报告 **n 与 CI 提示**（n<50 时标注"p95 估计噪声大"）；n<floor 层 → `NOT_SAMPLED`，不硬判。
- **故意制造 vs 事后识别**：park 梯是"制造"（每层样本由 cohort 决定）；`hit_parent` 从 per-request cached_tokens_details 识别是"鉴别"。二者都必需：制造不足则识别层样本为空，识别错误则制造无效。

### 2.3 判定与报告行模板

```
Gate B: S=100 分层 resume latency（同一对 run；OFF 臂测 GPU/Host/L3-on-demand，ON 臂测 RH-staged）
| layer | arm/cohort | n | TTFT p50 | TTFT p95 | >30s% | >60s% | vs 目标(p50/p95) | verdict |
|---|---|---|---|---|---|---|---|---|
| GPU/L1 resident  | OFF, HOT   | 210 | 0.6 | 1.4 | 0 | 0 | ≤1 / ≤2        | PASS |
| Host-ready       | OFF, MID   | 320 | 1.1 | 2.6 | 0 | 0 | ≤1.5 / ≤3      | PASS |
| RH-staged        | ON,  COLD  | 120 | 1.3 | 3.2 | 0 | 0 | ≤2 / ≤4        | PASS（engine-ready 复核 ✓） |
| L3 on-demand     | OFF, COLD  | 140 | 2.2 | 5.1 | 0 | 0 | ≤3 / ≤6        | PASS |
| 任意 hit 路径合计 | 两臂全部  | ~2k | —   | —   | 0 | 0 | p99≤10 | PASS |
```
- 每层判定：p50/p95 均 ≤ 目标表（ledger:2500-2508）∧ n≥floor ∧ >30s/>60s=0。**Gate B 整体 PASS ⇔ 四层 + 全局 p99≤10 + 两尾部=0 全部成立**。
- 输出附加：`age_at_wake_s` × TTFT 桶表（<1min /1-5min /5-30min /30min+，协议 ④.2 行）；每层 hit token 合计 + per-req 比例，与 e2 锚（Phase B restore p50=0.5s）对照。

---

## 3. Gate C — RH 兑现 spec

### 3.0 参照 run
Gate C 复用 **S=100 fit 的 OFF/ON 同一 seed 对**（§1）。ON 臂 = RH 兑现臂；OFF 臂 = 无 RH 基线。同一 park 梯 → 每 session 每次 wake 的请求形状完全一致，唯一差异 = RH。

### 3.1 需要观测的引擎事件（tester 24052 先验 + 采集）

**事件**（scheduler.py:3303,3325,3378,3455,3487,4726,4779；extent_allocator.py:212；extent_file_backend.py:379）：
```
evt=ready_stage     rid result=issued|declined state ready headroom
evt=restore_ready   rid
evt=restore_state   rid state=READY|RESTORING|WAIT_CAPACITY reason
evt=admission       rid pos qlen running_bs can_run
evt=restore_success rid n_tokens
evt=restore_recompute rid cause=miss|timeout final_storage_survivability
evt=ready_pool      size tokens watermark
evt=extent_recycle  slot generation freed
evt=extent_write    node component
```
**假定/待 tester 确认（24052 一次性 smoke run）**：
1. P2A/P3 trace 事件在目标引擎默认日志级别**实际发射**（rh-ab 先例已见 ready_stage/ready_pool/restore_*；`admission` 走 `_p2a_trace`，须 grep 确认）；
2. 事件里的 `rid` 与驱动 `runs.csv` 的 `rid`（`common.extract_sglext` 的 SSE rid）**可 join**；不可 join 时 fallback：以 ts 窗（±2s）+ session/turn 对齐并标注置信度；
3. `restore_ready` 在 RH ON 下对预 staging 的 COLD session **确实发射**（否则 rate 的 ready 判定降级为 ready_stage=issued + 无后续 restore_recompute 推理，须标注降级）。

### 3.2 Host-ready-before-admission rate ≥95%（测量口径）

- **分子** = ON 臂 rescue 事件数中，满足「存在 restore_ready（或 restore_state=READY）时间戳 `t_ready`，且最近一次 `admission` 时间戳 `t_adm` 满足 `t_ready ≤ t_adm + grace`（grace=1s）」的 rid。
- **分母** = ON 臂所有「RH 预测命中」的 session wake：即该 resume 的 rid 存在 `ready_stage result=issued` 事件（RH 曾为其预 staging）的 rid 集合（与 COLD+MID 预测目标一致）。
- **rate = 分子/分母 ≥95%**。
- **语义核对**：分母中每个 rid，若满足分子 → admission 时 state 已 READY = "scheduler 真正运行时 state 已 ready"（ledger:2515 核心 KPI）。rate<95% → Gate C FAIL-未兑现。
- driver 代理（RH-staged label 占比）只作结构参考，**不作裁决**（§3.1 假定 2 的 join 是硬前提）。

### 3.3 ON vs OFF delta（同 seed A/B）

| 量 | 计算 | 判据 |
|---|---|---|
| p95 TTFT（全 resume） | 每臂稳态窗 ttft_s 的 p95 | ON < OFF **显著**（相对降幅 ≥20% 或绝对 ≥0.5s）∧ ON ≤ Gate B Host-ready 带 |
| COLD cohort p95（RH 核心对象） | ON(≈RH-staged)→应入 Host 带（≤4s）；OFF(=L3 on-demand)→≤6s | ON p95 ≤4s 且 < OFF p95 |
| L3 synchronous restore wait | 引擎：rid 在 WAIT/RESTORING 的驻留时长（restore_state 事件 ts 差）；或 COLD 层 TTFT−warm 基准 | ON 臂 ≈0（预 staging 消掉同步 restore）；OFF 臂 >0 可见 |
| historical recompute | §1.4 判据 1 的 `history_recompute_tokens` + `restore_recompute` 计数 | **ON ≤ OFF**（不增加）∧ 两者均 0（fit） |
| 吞吐守恒 | turns/hour、decode TPS、finished% | ON 不显著低于 OFF（对掉 >15% = 危险信号，rh-ab B 轮 15% 少吞吐先例） |

### 3.4 副作用监控（指标与阈值）

| 副作用 | 指标 | 阈值（proposal） |
|---|---|---|
| 提前 recycle | 两臂首 `extent_recycle` ts 与当时累计写 | fit 下**两臂均 0**（S=100 大盘不 recycle）；若 ON 确有 recycle 而 OFF 无 → FAIL-副作用（rh-ab 先例 126.5s vs 314.5s） |
| Host starvation | `hicache_host_used_tokens` max/total；`ready_stage result=declined` 计数；NO_HEADROOM | 稳态 host_used ≤ 97% ∧ declined 不呈风暴（任意 60s 窗 declined ≥ 50% candidates → flag）；available headroom min > 小界 |
| L3 write amplification | `extent_write` bytes/次数 ON vs OFF（同 seed） | 比值 ≤1.5（rh-ab clean-window 1.08x 参照）；backuped/evicted delta 不入失控 |
| capacity deadlock | >60s TTFT=0；`restore_success` 持续增长；`ready_pool` 事件不被冻结 | 三者全成立；ready_pool 停滞 ≥120s → FAIL-死锁（rh-ab/rhfix 根因签名：ready_pool 冻结 + restore_success→0） |

### 3.5 Gate C verdict（全 AND）
1. Host-ready-before-admission ≥95%（§3.2，engine 事件裁决）；
2. p95 显著下降 ∧ COLD p95 ≤4s（§3.3）；
3. L3 sync restore wait ON≈0；
4. historical recompute ON ≤ OFF 且均 0；
5. 四项副作用均在阈值内。

> **诚实边界**：若 24052 无法产出 `admission`+`restore_ready` 可 join 事件（§3.1 假定 1/2 不成立），Gate C verdict 须降级为「driver-proxy rate + engine ready_pool/restore_* 汇总」并显著标注 **NOT_FULLY_VERIFIED**，同时把事件缺口作为 blocker 报 orchestrator（这正是 Gate C 在本 spec 里被识别为"最大未决前置"的原因）。

---

## 4. S=500/1000 oversubscription stress spec

### 4.1 语义框架（禁止宣称完整驻留）
- 定性 = 明确超配：S×840MB @55K vs 200G extent → S=500≈420GB（2.1x）、S=1000≈840GB（4.2x）。**允许 extent recycle**（不 fault）。**禁止**断言"200G 能完整 park S×55K"（driver/analyze 措辞护栏已内置 verdict caveats + FORBIDDEN CLAIM 注释）。
- **容量档位（与 fit 相反）**：extent **FILE_SIZE=30G 量级**（cursor 小 → 45-60min 内反复 recycle，物理驻留受控），MAX_SIZE 仍 200G 上限。理由：大 FILE_SIZE 下首 recycle 出现在 81-120G+cumulative 写，S=500 前 build 已写 420GB → 全程 thrash 但首 recycle 太晚、45-60min 观察窗内只能看到一次 cursor-wrap 边界；小 FILE_SIZE 让每次 recycle 密集、退化曲线有足够点。先例：rhfix 的 `MAX_SIZE=200G FILE_SIZE=30G`（extent gen 1-15 cursor-wrap 健康）。**这是一等规格维度，devops launcher 必须按档传 FILE_SIZE**。

### 4.2 档位参数模板

| 参数 | S=500 | S=1000 |
|---|---|---|
| `--mode` | oversub | oversub |
| `--sessions` | 500 | 1000 |
| `--build-tier` | 55k | 55k |
| `--active` | 8 | 8 |
| `--rounds` | 60 | 60 |
| `--seed` | 20260907 | 20260907 |
| `--park-min/--park-max` | 30/300（uniform；oversub 不需梯） | 30/300 |
| `--pick-lam` | 1.0 | 1.0 |
| `--obey-ac` | 传 | 传 |
| `--build-workers` | 8（**必选**；顺序 build 500×55K≈2h / 1000×55K≈4h，不可行） | 8 |
| `--turn-max-new` | 256 | 256 |
| `--client-max-time` | 1200 | 1200 |
| RH 臂 | RH OFF（必跑）+ RH ON（必跑，见 4.5） | RH OFF（必跑）+ RH ON（**可选**） |
| engine FILE_SIZE | 30G | 30G |
| evidence-dir | `/root/evidence-parked-ov500-{off,on}` | `/root/evidence-parked-ov1000-{off,on}` |

预计时长：build（workers=8）≈20min（500）/≈40min（1000）→ + rounds 60min + boot 7.3 ≈ **1.5h / 1.8h 每臂**。

### 4.3 测量列（退化曲线矩阵）

X 轴：S ∈ {100,500,1000}（or 超配比例 = S×840MB/200G ∈ {0.42, 2.1, 4.2}）。每 S 每 RH 臂一行，列：

| 列 | 口径 |
|---|---|
| L3 residency | `l3_extent_physical_bytes`（coarse sampler）、L3 逻辑占用 slots/tokens（extent occupancy）、Host `hicache_kv_host_usable/used` |
| hit 分布 | per-arm device/host/storage hit tokens + per-req 比例（COLD 层预期随 S 跌） |
| **recycle-GC** | extent_recycle 次数；distinct_gen（thrash 度量，rhfix 先例 5 健康 vs 7500 thrash）；`evicted_tokens_total` / `backuped_tokens_total` / `load_back_tokens_total` delta + bytes；GC/evict 事件数与触发原因 |
| recompute | total recompute tokens + fraction；`restore_recompute cause=miss|timeout` 计数；recompute_attribution.csv 初判（capacity_evicted/state_machine/other） |
| random resume TTFT | p50 / p95 / p99 / max；>30s% / >60s%；稳态窗 |
| throughput | turns/hour、aggregate decode TPS |
| **per-event recompute 归因** | 每 full recompute 一行：session/turn/ts/prompt_len/hits/recompute_tokens/driver_reason/engine 复核列（见 4.4） |
| 健康 | finished=100%、0 OOM、DQ≥55s、restore timeout、GPU util |

### 4.4 合格条件（不是 PASS/FAIL，是归因约束）

**每一次 full recompute 都必须归因于容量淘汰 ⇒ 终判 state_machine 类 = 0。**

归因闭环（driver 初判 + analyze 引擎复核）：
1. driver 对每 full-history recompute 打初判（capacity_evicted / state_machine / other）——已实现（gate3_parked.py:519-546）；
2. `gate3_parked_analyze.py` 对每事件复核：若该 session **先有 L3-durable 证据**（build 或 prior storage hit）且存在 `extent_recycle` 事件 `ts_recycle < ts_recompute`（该 session 的 L3 entry 被容量淘汰）→ 终判 `capacity_evicted`；否则→ 终判 **`state_machine`（异常）**；
3. **终判条件：`state_machine 计数 = 0`**（= "每一次 full recompute 都能解释为对应 cache entry 已被正常容量淘汰"，ledger:2533）。driver 初判与终判不一致的逐条列差异表。
4. 曲线本身**无 PASS/FAIL**：按 S 输出退化趋势 + 归因约束合规性 + 退化机制句（预期 L3/disk recycle 主导，非 GPU/架构——protocol-e1 ④.3 预测）。

### 4.5 RH 臂在 oversub 的含义
- ON 臂是 **write amplification / deadlock 压力测试**：RH 预 staging 在容量耗尽 + cursor-wrap 密集下是否重演 rh-ab 的"ready_pool 冻结 + restore 永久失败"（ledger:1043 的 deferred known issue）。观察 ready_pool 冻结签署、restore_success 增长、`>60s=0`、host starvation。
- 若 S=500 ON 臂出现冻结/死锁 → **如实记录为退化曲线的一部分 + 单独 flag 为 RH-under-pressure 已知问题重现**，不伪装成 oversub 正常退化。
- GPU 预算紧时 S=1000(RH ON) 可省（S=500 ON 已对压力路径取样），但报告须标注未测臂。

### 4.6 输出模板

```
④ oversubscription stress degradation（H0=55K, active=8, seed=20260907, FILE_SIZE=30G）
| S | oversub(×200G) | L3 phys | stor-hit% | recycle# | distinct_gen | recompute% | attribution(cap_evict/state_machine/other) | TTFT p50/p95/p99/max | >30s% | >60s% | turns/hour | verdict-guard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 0.42 | 85G | 41% | 0 | 5 | 0.0% | 0/0/0 | 0.7/2.9/5.8/22 | 0 | 0 | 2100 | fit（Gate A 区） |
| 500 | 2.1 | 30G | 23% | 812 | 612 | 8.4% | 301/0/2 | 1.4/9.2/28.3/58 | 2.1% | 0.3% | 900 | att=0 ✓ |
| 1000| 4.2 | 30G | 14% | 1731 | 1488 | 15.7% | 852/0/5 | 2.0/16.5/44.1/61 | 4.4% | 1.1% | 760 | att=0 ✓ |
degradation mechanism: <expected recycle-GC / L3 write-back dominant; GPU/architecture NOT limiting — quantified above>
qualification: every full recompute attributable to capacity eviction: state_machine=0 → <合格 / 不合格（列出 state_machine 事件）>
```

---

## 5. 执行序 + GPU 预算 + 停止条件

```
Stage 0  ② ratio sweep（已在跑）→ 输出 r* + 频率级判据
Stage 1  ③ capacity curve = Gate D spec（e4，已授权）→ 输出 effective concurrency(c8 或降级) + Gate D 全套
Stage 2  ④ S=100 fit RH OFF（Gate A 基线 + Gate B OFF 现实层 + Gate C OFF leg）
Stage 3  ④ S=100 fit RH ON（Gate A 正式 + Gate B RH-staged 层 + Gate C ON leg）
            └─→ §1.5 / §2.3 / §3.5 verdicts（A/B/C 三 Gate 的 S=100 结论）
Stage 4  ④ S=500 oversub RH OFF → RH ON
Stage 5  ④ S=1000 oversub RH OFF →（预算内）RH ON
Stage 6  oversub 矩阵 + 归因闭环 + 退化曲线（§4.6）
```

| 阶段 | 前置 | boots | GPU 预算 | 停止条件 |
|---|---|---|---|---|
| 0 ② | —（running） | 6-7 | ~1.5-1.8h | ② 判据表出齐（r* + PASS/FAIL） |
| 1 ③ | r*、55k tier 驱动（已路由 coder） | 3-5 | ~0.8-1.3h | Gate D 判据（aggregate≥500 / TTFT p50/p95/p99≤2/5/10 / >30s=0 / recompute=0 / DQ=0） |
| 2 ④ S100 OFF | ③ 结论（c8 确认）、驱动 v2+ladder+build-workers、analyze 脚本、event join 先验（§3.1） | 1 | ~1.3h（boot+5min build+60min） | Gate A 结构失效（full recompute>0 / recycle>0）→ **停、上报 root-cause，不往下** |
| 3 ④ S100 ON | 同 | 1 | ~1.3h | Gate C 死锁（ready_pool 冻结 / >60s>0)→ 停、上报 RH-under-pressure 重现 |
| 4 ④ S500 | /data free≥FILE_SIZE+20、oversub launcher(FILE_SIZE=30G) | 2 | ~3h | 无法本轮完成的不可静默缩 H（协议 R1 精神）；写放大失控也不中断（曲线要与归因） |
| 5 ④ S1000 | 同 | 1-2 | ~1.8-3.6h | 同；预算紧省 ON 臂 |
| 6 汇总 | 全部 evidence | 0 | 分析 | — |

**总 GPU：④ 合计 ≈ 7-11h；含 ②③ ≈ 9.5-14h。**（②③ 若已消耗部分按实抵减。）每 cell 后环境复原（SIGTERM→15MiB idle、namespace 清理、md5 复核）。

---

## 6. 对驱动（coder v2 目标）### 6.1 已满足（当前树 gate3_parked.py v2 已含，本 spec 直接消费）

| # | 能力 | 位置 | 本 spec 消费点 |
|---|---|---|---|
| 1 | `--mode fit\|oversub` + semantic caveats（禁宣称完整驻留） | gate3_parked.py:638-666,735-748 | §1.2、§4.1、§4.6 guard |
| 2 | `--rh on\|off` 配对档 + verdict rh 字段 | :682-688,653 | §1.2、§3.0 双臂 |
| 3 | `--build-tier` 55k（default）|BUILD_TIERS 含 55k|:149-154,689-691 | H0=55K 权威档 |
| 4 | `classify_hit_parent` 六类 hit 标签（GPU-resident/Host-ready/RH-staged/Host-ready-STAGED/L3-on-demand/miss） | :318-348,502-503 | §2 Gate B 层识别 |
| 5 | recompute attribution（capacity_evicted/state_machine/other 初判） | :504-546,594-619 | §1.4 Gate A、§4.4 归因闭环 |
| 6 | `eviction_observed` coarse sampler（evicted/backuped/load_back delta） | :795-832 | §4.4 复核输入之一 |
| 7 | L3 物理足迹 `st_blocks×512`（extent sparse 感知） | :299-315 | §1.4、§4.3 L3 residency |
| 8 | FIT/OVERSUB session 常量（FIT=100 / L3_FIT=170 / OVERSUB=(500,1000)） | :156-161 | §1.2、§4.2 |

### 6.2 本 spec 新增依赖（向 coder / tester 转交）

**coder（新增驱动补丁，仅两项）**：
1. **park 梯（cohort 窗带）**：按 session id 区间分段 park 窗，制造 Gate B 四层状态（§2.1）：
   - `--park-ladder "HOT:0-30@5,MID:120-300@30,COLD:600-2400@65"`（fit 档；oversub 档仍 uniform 30-300，不需梯）；
   - 实现：`Sched.retire` 按 cohort 段取 `uniform(cohort_min, cohort_max)`；`--park-min/--park-max` 保留（uniform 模式）。
2. **`--build-workers N`（并发 COLD build）**：顺序 build 100/500/1000×55K 分别 ≈25-35min/2h/4h（128K 先例 47s/次），不可行；8 并发 ≈5/20/40min。driver 现状 run_builds 顺序（:391-421）。**这是 S≥500 能否执行的硬依赖。**
   - 附带：并发 build 期间 L3 写入同样并发，注意 `--build-gap` 语义不变（防瞬时同前缀驻留）。

**tester（24052 先验确认，Gate C 硬前提 + 分析层）**：
3. **engine-ready join 事件可用性**（§3.1 假定 1/2/3）：P2A/P3 trace 在目标引擎是否默认开、`admission`+`restore_ready`+`ready_stage`+`restore_recompute` 是否发射、事件 rid 与驱动 SSE rid 是否 join 得上；**一次性 smoke boot 验证**（boot + 数 request，grep 事件）。
4. **RH toggle 可用性验证**：`--enable-ready-horizon`（server_args.py:2866）在 24052 当前部署 md5 下开、生效（ON 臂 engine log 见 ready_stage/ready_pool 发射；OFF 臂无）。drive `--rh` 只打标签，真正 toggle 在 launcher（driver docstring 已明言依赖，ledger 同步）。
5. **`gate3_parked_analyze.py`（新分析脚本，coder 可选 / tester 可造）**：Gate B 分桶（hit_parent×TTFT p50/p95/p99 + n）、Gate C engine-join（rid 时间戳对齐 rate + delta + 副作用）、oversub 矩阵（§4.3 列）+ 归因复核（§4.4 step 2，用 `evt=extent_recycle` ts < `evt=restore_recompute` ts + session 的 L3-durable 先例）。**这是 Gate C 裁决与 oversub 归因闭环的必需件**（driver 只产原始行）。
6. **oversub launcher 档位**：S≥500 用 `FILE_SIZE=30G`（cursor 小、物理驻留受控、退化曲线有足够点；rhfix `MAX_SIZE=200G/FILE_SIZE=30G` 先例），与 S=100 fit 的 `FILE_SIZE≥120G` 是**两个不同 launcher 档**。devops/runner 侧配置（本 spec 只定档位语义）。

### 6.3 依赖优先级（阻塞性排序）
1. **P0-阻塞**：`--build-workers`（S≥500 不可行，S=100 也省 30min）、park 梯（Gate B 层样本无法保证）、engine-ready join 先验（Gate C 判定前提）。
2. **P1-必需**：RH toggle launcher 档、`gate3_parked_analyze.py`、oversub FILE_SIZE=30G launcher。
3. **P2-建议**：S=1000 RH ON 臂（预算内才有）。

---

## 7. Alternatives（本 spec 层面考量过并取舍）

1. **uniform park 窗 + 事后 age 分桶 vs park 梯**：uniform 依赖年龄自然分层，S=100 下 COLD（600s+）样本或不足（rh-ab 无梯，B 轮 COLD 少）。park 梯是确定性制造，成本 = 一次驱动补丁。**选梯**；uniform 仅作 oversub（退化曲线不需分层）。
2. **RH-staged 标签作裁决 vs engine-ready join 作裁决**：driver 标签含永久化 bias（§2.1 声明），且不证明"admission 前已 ready"（时间序缺失）。**选 engine join**（restore_ready ts ≤ admission ts）；标签仅作结构参考。
3. **S=100 用大 FILE_SIZE 保 0 recycle vs 小 FILE_SIZE**：Gate A 需 recycle=0，必须大 FILE_SIZE（≥120G）；oversub 需密集 recycle 观察点，必须小 FILE_SIZE（30G）。**两个档位，不是同一个**。
4. **fit 每层 floor 用 n≥30 vs 更强**：n=30 是 p95 分位数的最小统计力（~0.95 位 30 样本 = 第 28/29 个序分位，粗但可用）；n<30 标 NOT_SAMPLED，不硬判。梯子设计已使实际 n 高于 floor（§1.3）。
5. **Gate C 是否并入 ③（Gate D）**：③ 是 c8 内 fixed-concurrency 稳态，不产生 parked COLD 样本，无 Gate C 测量对象 → **留在 ④**（本 spec §3），与 Gate D 正交不重复。
6. **S=1000 RH ON 是否必跑**：S=500 ON 已对 RH-under-pressure 取样；S=1000 ON 加倍成本 → 可选，报告标注未测臂。

## Migration / Impact
- **无产品代码改动**；配置层（launcher FILE_SIZE 两档 + RH toggle）+ 驱动层（parked v2 已含大半 + 2 个新补丁）+ 分析层（analyze 脚本）。24052 代码仍 9c9e7b7c7c（md5 495b8851/465b6c68）不动。
- 与 ③(Gate D) 的衔接：③ 输出 effective concurrency 定 ④ 的 active；④ 不再重复 Gate D 判断，只消费 ③ 结论。
- 与既有验收体系：Gate A/B/C 的 S=100 结论 = 三级 HiCache 的正式产品验收；oversub 是上限研究曲线；Gate D 归 ③。四 Gate 合起来是用户 2026-09-07 重定义的完整最终验收。

## Open Decisions（标注不裁决，路由 orchestrator/user）
- **OD1（Gate C 事件可用性）**：engine-ready join（§3.1）若在 24052 不可 join，Gate C 降级为 NOT_FULLY_VERIFIED 的 proxy rate——是否接受降级结论，或先由 coder 出一段事件 dump/改造（涉产品改动，需授权）。
- **OD2（RH toggle）**：ON 臂需要 `--enable-ready-horizon` 在生产基线（RH OFF 冻结）之外开 RH——是否在正式验收轮开 RH（此前 RH 为 deferred known issue，ledger:1043/context），由用户裁决 Gate C 是否把 RH ON 纳入正式验收（本 spec 按用户 4 Gate 裁决默认纳入，dual-arm）。
- **OD3（oversub ON 臂成本）**：S=500 ON + S=1000 ON 是 RH-under-pressure 压力测试，GPU ~5.4h 额外；预算内省 S=1000 ON 是否可接受。
- **OD4（梯子 cohort 分配）**：HOT=5/MID=30/COLD=65 是设计值；若 HOT 成员因 pick-lam 或 active 窗被 COLD 抢占而样本不足，或 MID 层因 120-300s 落在 GPU 逐出边界而分桶混乱 → 以实测 age 分桶回读为准（analyze 必须用 `age_at_wake_s` 实测再归类，梯子只作注入偏置）。

## followups
- coder：park 梯 + `--build-workers` 两补丁（P0）；可选 `gate3_parked_analyze.py`。
- tester：24052 smoke boot 验证 §6.2 项 3/4（engine-ready join + RH toggle）→ ② 完 → ③(Gate D) → ④ Stage 2-6。
- orchestrator：OD1/OD2/OD3 裁决；③ e4 的 55k tier 补丁路径（若未闭合）同批处理。

## open_issues
- Gate C engine-ready join 可用性 = 本 spec 唯一未在 24052 验证的结构性前提（§3.1）。
- park 梯 cohort 分配的实测 age 回读（OD4）。
- oversub ON 臂是否全跑（OD3）与 RH 正式纳入（OD2）。

---

## Return envelope

```text
status: done
artifacts:
  - spec: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e5-architect-e1.md
evidence:
  - ledger.md:2488-2536（用户 4 Gate 权威裁决 + parked 两档）
  - ③ spec 对照格式：work/phase2-cap-e4-architect-e1.md（Gate D 正交边界，未重复）
  - ④ 旧协议：work/phase2-cap-protocol-architect-e1.md §④（S/age/R1）
  - e2 基线：work/phase2-cap-e2-tester-e1.md（kv_used 341.8K、TTFT 分层、DQ 锚）
  - 驱动现状：3090-dev/gate3_parked.py v2（mode/rh/55k/attribution/hit-parent/eviction 采样已具备）+ coder-e1 原设计
  - RH 先例：rh-ab-e2（clean-window 2.26x storage_hit / 冻结签名）、rhfix-tester/rhfix-architect（磁盘 GC confound、FILE_SIZE=30G 压力档、Fix A 价值）
  - 源码核对：ready_horizon.py（frontier/staging/watermark/NO_HEADROOM）、scheduler.py 事件格式（ready_stage/ready_pool/restore_recompute/restore_state/restore_ready/admission/restore_success）、extent_allocator.py:212（extent_recycle）、extent_file_backend.py:379、server_args.py:2866（enable_ready_horizon）
summary:
  Conclusion: ④ 已按 Gate A/B/C 重排为 tester 可照跑的 executable spec（S=100 双臂 = Gate A/B/C 一次性测量；S=500/1000 = oversub 退化曲线 + 归因闭环）；与 ③(Gate D) 正交
  Current Architecture: ④ 复用 ② 定稿 engine 配置（r*+graph bs8+c8+RH OFF 基线+FP8+L3 200G）+ parked v2 驱动（fit/oversub、RH 档、hit 标签、归因表均已具备）
  Problem / Forces: Gate B 四层状态需故意制造（park 梯缺）；Gate C 需 engine 事件判定 ready-before-admission（join 未验）；S≥500 顺序 build 不可行（build-workers 缺）；fit 与 oversub 需相反 FILE_SIZE 档位
  Proposed Architecture: 门-实验映射（Gate A/B/C→S=100 双臂）+ Gate B 四层测量表 + Gate C RH 兑现（rate/ON-OFF delta/副作用）+ oversub 退化曲线（state_machine=0 归因闭环）+ 执行序与 GPU 预算 + coder/tester dependency 清单（P0/P1/P2）
  Alternatives: uniform+age 分桶 vs park 梯（选梯）；driver 标签 vs engine-ready join 作 Gate C 裁决（选 join）；fit 大 FILE_SIZE vs oversub 小 FILE_SIZE（两档并存）；S=1000 ON 臂可选
  Migration / Impact: 无产品代码改动；两驱动补丁（ladder+build-workers）+ analyze 脚本 + launcher 两档（FILE_SIZE/RH）+ 24052 smoke 先验；四 Gate 合流为用户 2026-09-07 完整最终验收
  Open Decisions: OD1 engine-ready join 可用性（Gate C 结构性前提）、OD2 RH 是否纳入正式验收、OD3 oversub ON 臂成本、OD4 梯子 cohort 分配以 age 实测回读为准
open_issues:
  - Gate C engine-ready join（restore_ready ≤ admission 时间戳）须 24052 smoke boot 验证（§3.1/§6.2 项3）
  - park 梯 + --build-workers = 唯二新驱动依赖（P0），未就绪前 Stage 2/4 不可执行
  - gate3_parked_analyze.py（Gate B 分桶/Gate C join/oversub 归因复核）为 Gate C 裁决与归因闭环必需件
```
