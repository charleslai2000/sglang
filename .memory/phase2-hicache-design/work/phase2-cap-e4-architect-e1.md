# phase2-cap-e4-architect-e1 — ③ 真实 Claude capacity curve 运行规格细化（可执行 spec）— **e1-r2 / GATED**

- Agent: architect
- Epoch: 1, **revision r2**
- Date: 2026-09-07
- Scope: 纯设计（只读）。把 architect 协议 §③ 细化成 tester 可直接照跑的执行 spec。**r2 = 用户重定义最终验收为 4 硬 Gate（A/B/C/D）后的全量修订**：③ 判据被 **Gate D** 整体替换（原 p99≤40s / TPS≥450 / >30s>60s 比例判据全部作废，见 §3 GATED banner）。不跑 GPU、不改产品代码、不实现驱动（驱动 reconciliation 只标注并路由回 coder/tester）。
- 输入（Read 引用）：`work/phase2-cap-protocol-architect-e1.md`、`work/phase2-load-driver-design-coder-e1.md`、`work/phase2-cap-e2-tester-e1.md`、`ledger.md:2407-2536`（含新增"4 硬 Gate 权威版"节 2480-2536）、`3090-dev/gate3_capacity.py`（就地核对）。
- **supersedes**：本文件 e1（r1，旧判据版）中 §3.2/§3.3（旧 TTFT/TPS/比例判据）、§1.1 R8 降格注释、§4.2 R8 语义 被本修订取代；55k tier 补丁推荐（§2.2）、执行序 shell（§4.1 结构）与 R1-R9 其余规则保留并重标注。

---

## status: done

## artifacts
- 本报告（e1-r2 / GATED）：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e4-architect-e1.md`
- 已核对输入：protocol §③/§②/§5/§6；coder-e1；tester-e1；`ledger.md` Gate A/B/C/D 权威节（2480-2536）；`gate3_capacity.py:91-95,320-341,291-317`（write_outputs 确认无 aggregate TPS）

## evidence（文件 + 行号）

| 事实 | 出处 |
|---|---|
| **Gate D 定义（本 spec 判据源）**：固定 workload 50–80K prefix/Agent；output 固定 **256 tokens 标准档**；FP8 KV；pool64 或 sizing 后最终 profile；Graph ON。测 c4/c6/c8；c8 目标 aggregate decode TPS≥500 / per-Agent≥60 / TTFT p50≤2s·p95≤5s·p99≤10s / >30s=0 / avoidable history recompute=0% / DEVICE_QUOTA pathological wait=0 / OOM·HTTP error·zero-progress=0。**"c8 8/8 都返回 200" 不算成功；c8 不达降 c6，找最大满足所有 latency/cache Gate 的 effective concurrency**。 | ledger:2504-2514 |
| Gate A 语义：L3-fit 时 avoidable historical recompute rate = **0%**（允许：新增 tokens、Mamba TRAILING_PAGES 少量；禁止：50K 历史重新 prefill、revoked:miss full recompute、admission 导致重算） | ledger:2494-2499 |
| Gate B/C（④ 与 RH 验收用，③ 仅引 p99≤10s 边界与 >30s>60s=0 语义） | ledger:2499-2503 |
| ③ 执行影响（权威）："③ 判据升级为 Gate D（原 p99≤40s / TPS≥450 / >30s>60s 比例全部作废）" | ledger:2532-2533 |
| ② 定稿配置（③ 继承：r* + graph bs8 + c8 + RH OFF + L3 200G + memory-computed 池） | protocol-e1:162-164,80-89；ledger:2450-2452 |
| ③ 负载 shape（H0=55K、delta 短、每 turn 重发全历史、prime 串行 COLD + 并发 warm） | protocol-e1:167-173,119-124 |
| c8 基线 ≈596-606 tok/s（compute-bound）→ per-Agent 均 ≥62.5 才达 aggregate≥500 | protocol-e1:42-43 |
| e2 实测锚：448K 池 kv_used max=341,818、TTFT p50=0.6/p99=45.5、DQ≥55s=0 | tester-e1:44-76 |
| 驱动 CLI：`--agents 4|6|8`、`--tier choices={50k,80k}`（无 55k）、default 64k **非法**、`--cold-max-new 12 / --warm-max-new 64`、`--warm-repeats`、`--stagger` | gate3_capacity.py:91-95,320-341 |
| **驱动无 output tokens/s 聚合**：verdict.json 仅 requests_total/requests_ok/elapsed_s；逐行有 completion_tokens（可聚合但 driver 不自带） | gate3_capacity.py:291-317；_mkrow L160-190 含 completion_tokens |

---

## summary

# ③ 真实 Claude capacity curve — Gate D 可执行运行规格（e1-r2 / GATED）

## 0. 前置条件（③ 只能在这些成立后开跑）

1. **② 已完成**，输出 `r*`（推荐 0.33，区间 [0.30,0.45]）；③ 继承 ② 定稿配置（protocol-e1:162-164；**Gate D "pool64 或 sizing 后最终 profile" = ② 的 r* 定档 memory-computed 池为准**，pool64 仅为锚参照）：
   ```
   kv_cache_dtype=fp8_e4m3
   --cuda-graph-max-bs 8            （Graph ON，Gate D 前提）
   --max-running-requests=N         ← ③ 每 cell 的 N（R7：c=N）
   --mamba-full-memory-ratio=r*     ← ② 定稿值，③ 一律固定
   RH OFF（③ 档；RH 相关验收归 Gate C/④）
   L3 extent 200G/10G + waite_complete + write_back + hicache_ratio 1.5
   不设 --max-total-tokens（memory-computed 池 ≈498K @ r*）
   ```
2. **驱动 55k tier 就绪**（§2.2 选项 A，补丁已另派 coder）——主矩阵 H0=55K 依赖，不滞后于主矩阵。
3. **Gate D 测量前置项就绪**（新，§4.1 Step 0）：
   - **output 256 标准档**：驱动以 `--cold-max-new 256 --warm-max-new 256` 调用（Gate D "output 固定 256 tokens"；cold prime 虽也 256，但统计从稳态窗取值，prime 段排除）。
   - **aggregate / per-Agent decode TPS 聚合段**（§4.0 决策）：driver 不输出聚合 → 由 tester 在现成 gate2_analyze 口径上聚合 runs.csv `completion_tokens`（Σ/稳态窗；per-agent 分组），或 coder 小补丁在 write_outputs 加 summary 字段（可选、非阻塞）。**决策标注**：优先 tester 轻量聚合（零 driver 改动）；不阻塞 ③。
   - **avoidable recompute 分类段**：从每 req `prompt_len − (device+host+storage)_hit` 中扣 delta+tail 允许量，取其超出量 = avoidable（Gate A 语义，§4.0 口径）。
4. 24052 空闲（GPU 0%/15MiB、零残留/lock）、/data 每 cell fresh namespace、deploy md5=495b8851/465b6c68 核对。
5. 每 cell 用引擎 `--max-running-requests=N`；N=8 cell 复用 ② C2 档配置（② C2=③ 配置复验点）。

### 4.0 Gate D 测量口径定义（先定口径再给表）

| 量 | 定义 | 计算 |
|---|---|---|
| aggregate decode TPS | 稳态窗内 Σ(completion_tokens) / 稳态窗 wall_s（realtime_tokens_total mode=decode delta 交叉验证） | runs.csv completion_tokens 聚合 + engine counter |
| per-Agent decode | 稳态窗内 Σ(completion_tokens of agent) / 该 agent 稳态窗活跃 wall | per-agent 分组聚合 |
| avoidable history recompute rate | Σ_avoidable / Σ_served；`avoidable(req) = max(0, prompt_len − (device+host+storage)_hit − delta_len − tail_budget)`，tail_budget≈256 token（TRAILING_PAGES 允许量） | per-req 分类后聚合 |
| zero-progress | client 侧超时且无 decode 进度 / 引擎 `num_running_reqs` 停滞窗口 | runs.csv rc + mid-run metrics 诊断 |
| DEVICE_QUOTA pathological wait | DEVICE_QUOTA 型 WAIT_CAPACITY（容量排队导致），排除 FRONTIER 正常等待 | engine 日志 WAIT reason 分类 |

## 1. 档位矩阵定稿（Gate D workload：output 256 标准档）

### 1.1 必跑主矩阵（Gate D：测 c4/c6/c8 × H0=55K × output 256）

| cell | N | H0（tier） | warm_repeats R | R×N（稳态请求） | per-Agent 稳态输出 | 预期 working set（×8） | 相对 498K 池裕量 | 角色 |
|---|---|---|---|---|---|---|---|---|
| **m3-1** | **8** | **55k** | 19 | **152** ≥150 | 256×19≈4.9K | ≈ 444-467K | ≈ 31-54K >0 | **Gate D 主目标 c8**（aggregate≥500 / per-Agent≥60 判据点） |
| **m3-2** | **6** | **55k** | 25 | **150** ≥150 | 256×25≈6.4K | ≈ 333-350K | 池充裕 | **降档候选 c6**（c8 失败时判据反射点） |
| **m3-3** | **4** | **55k** | 38 | **152** ≥150 | 256×38≈9.7K | ≈ 222-233K | 池重裕 | **最小并发 canary c4**（descent 底；**不再是 R8"相对 60%"降格**） |

> working set 计算同 r1：`8×(H0 + Δ̄×R)`；Δ̄≈30 token（warm delta 短）/turn 上限 ≈ 55K+3.4K。**判定以实测 `kv_used_tokens` 为权威**。
> warm_repeats 目标仍为稳态请求 ≥150（统计力，protocol-e1:172）。Gate D 的 output=256 使稳态 decode 量 ≈ 150×256 = 38.4K tokens ≈ 64-77s decode 下限（500-600 tok/s），cell 全程仍 ≈ 6-10 min（不含 boot 7.3min）。

### 1.2 可选追加（预算内，均 N=8，output 256）

| cell | N | H0 | 定位 | 预期 |
|---|---|---|---|---|
| m3-4(opt) | 8 | 50k | Gate D 前缀下界 50K | WS≈405K，裕量更大；测短历史是否更稳/更快 p99 |
| m3-5(opt) | 8 | 80k | Gate D 前缀上界 80K / **显式超配探针** | WS≈645K >> 498K 池 → 预期强制 evict/recompute、kv_available min=0、avoidable>0 → **overshoot 退化曲线（非 Fail-运行）**，同 ④ oversubscription 语义（ledger:2473-2475 精神） |

### 1.3 每 cell 参数模板（同 shape，仅 N/H0/R 变）

```
agents       = N
tier         = "55k"（或 50k/80k 可选）
warm-repeats = R（§1.1）
cold-max-new = 256            ← Gate D output 固定 256（prime 段排除出统计）
warm-max-new = 256            ← Gate D output 固定 256
stagger      = 2
client-max-time = 1200
snapshot-interval = 5
evidence-dir = /root/evidence-capacity-<tier>-c<N>
```
- **Prime**：N×COLD 全 H0（空 cache 首 turn）错峰 2s；COLD 数据归档。≈ N×(15-25)s。
- **稳态**：R 轮并发 warm，**每 turn 重发全历史 + assistant + delta**（warmctx 模式），TCP backpressure 并发控制，注入窗口=N（R7）。
- **稳态窗定义**：warm r2..rR（排除 prime 与首 1-2 轮预热），窗内请求数 ≥150（主 cell）。

## 2. 驱动调用规格 + reconciliation

### 2.1 契约 vs 实际差异表（Gate D 修订后）

| 架构协议契约 §5.1 | gate3_capacity.py 实际 | 差异 | reconciliation |
|---|---|---|---|
| `--agents N ∈ {4,6,8}` | `--agents int` | ✔ | 直接可用 |
| `--history-tokens H0 ∈ {50000,55000,80000}` default 55000 | `--tier choices {50k,80k}` 无 55k；default "64k" 非法 | **H0=55K 不可表示（主矩阵阻塞）** | **§2.2 选项 A（补丁已另派 coder）** |
| delta 短（warmctx 模式） | 固定 talky follow-up（warm_max_new） | 兼容；**Gate D 改为 warm_max_new=256 output 标准** | tester 传 --warm-max-new 256 |
| `--turns 20`（首=COLD） | `--warm-repeats` | turn 数维度差 | 本 spec §1.1 R 表 |
| aggregate/per-Agent decode 聚合 | **driver 无聚合输出**（verdict.json 仅 requests_total/ok/elapsed，逐行有 completion_tokens） | **Gate D 判据所需** | §0.3 → §4.0 决策（tester 聚合，可选 coder 补丁） |
| 健康断言 | _mkrow 记 rc/finished/output_sha16；无硬断言 | tester 事后断言 | §3.4 |
| max effective active = N（R7） | 线程自由运行，并发靠 engine --max-running-requests | wrapper 控制 | tester 传 N；mid-run 验证 |

### 2.2 **关键 reconciliation——55k / 64k tier（unchanged，推荐不变，补丁已另派 coder）**

实况（gate3_capacity.py:91-95,324）：`TIER_TARGETS={"50k":50000,"80k":80000}` 无 55k；`--tier` default="64k" ∉ choices → **argparse 对 default 亦校验，不带 --tier 必崩 `invalid choice: '64k'`**；coder 自身 docstring/建议命令均用 `--tier 64k`（现必失败）。

| 选择 | 做法 | 推荐 |
|---|---|---|
| **A（推荐，已另派 coder）** | `TIER_TARGETS` 加 `"55k":55000`（+顺手补 `"64k"` 或改 default 为合法值），同步 24052 | **A**（③ 主判据依赖 H0=55K） |
| B | `--tier 50k` 代理 | 仅临时探针，不作主判据（H0 偏离裁决 ~9%） |
| C | 加 `--history-tokens int` | 可选（A 已满足全部所需） |

### 2.3 驱动调用实际命令（A 落地后；Gate D：output 256）

```bash
# 主矩阵（必跑）
cd /root && python3 gate3_capacity.py --agents 8 --tier 55k --warm-repeats 19 \
  --cold-max-new 256 --warm-max-new 256 --stagger 2 \
  --evidence-dir /root/evidence-capacity-55k-c8
python3 gate3_capacity.py --agents 6 --tier 55k --warm-repeats 25 \
  --cold-max-new 256 --warm-max-new 256 --stagger 2 \
  --evidence-dir /root/evidence-capacity-55k-c6
python3 gate3_capacity.py --agents 4 --tier 55k --warm-repeats 38 \
  --cold-max-new 256 --warm-max-new 256 --stagger 2 \
  --evidence-dir /root/evidence-capacity-55k-c4
# 可选（预算内）
python3 gate3_capacity.py --agents 8 --tier 50k --warm-repeats 19 \
  --cold-max-new 256 --warm-max-new 256 --evidence-dir /root/evidence-capacity-50k-c8
python3 gate3_capacity.py --agents 8 --tier 80k --warm-repeats 19 \
  --cold-max-new 256 --warm-max-new 256 --evidence-dir /root/evidence-capacity-80k-c8
```
- 引擎 wrapper 传 `--max-running-requests=N` 与 ② 定稿 flag；每 cell 记录 engine-alloc.txt。

## 3. 测量与判定表模板（**GATED**）— 旧判据（p99≤40s / TPS≥450 / >30s>60s 比例 / recompute≤5%）经 ledger:2532 **正式作废**，本节全量替换为 Gate D

### 3.1 每 cell 对照表（8 列 + 长尾行）——Gate D 目标列

| 列 | 指标 | Gate D 目标 / 口径 |
|---|---|---|
| 1 | cell | `N=8 × H0=55K（tier 55k, R=19, output 256, WS 目标 440-480K）` |
| 2 | resident device KV | `kv_used` **max/p90/p50/mean**；`kv_available` **min（>0）**；`kv_evictable` max/mean |
| 3 | 命中分布 | `device_hit / host_hit / storage_hit` tokens（每 cell 总和 + per-req 比例） |
| 4 | avoidable history recompute | **= 0%（Gate A 语义）**；recompute fraction；restore_recompute（口径 §4.0） |
| 5 | TTFT（稳态窗） | **p50 ≤ 2s / p95 ≤ 5s / p99 ≤ 10s**；**>30s = 0**；**>60s = 0**（报告保留 p50/p95 + 两比例绝对值） |
| 6 | decode | **aggregate ≥ 500 tok/s**；**per-Agent ≥ 60 tok/s**；per-req TPS(TPS/N) |
| 7 | GPU | util mean/p50、mem mean、0 OOM |
| 8 | 健康 | **DEVICE_QUOTA pathological wait=0**；**OOM / HTTP error / zero-progress=0**；finished=100%；sha16 非空 |

### 3.2 判定模板（Gate D：全 AND；**descent search，非逐档松绑**）

| # | 判据 | Gate D 阈值 | 备注 |
|---|---|---|---|
| 1 | 100% finished ∧ 0 OOM/HTTP error/**zero-progress** ∧ sha16 非空 | — | **"c8 8/8 返回 200" 不构成成功**（ledger:2513） |
| 2 | 稳态 TTFT **p50 ≤ 2s** ∧ **p95 ≤ 5s** ∧ **p99 ≤ 10s** | ≤2/≤5/≤10s | Gate B/D 边界（p99=40s 当 PASS 正式作废） |
| 3 | **>30s = 0** ∧ **>60s = 0**（绝对计数为 0，非比例阈值） | 0 / 0 | 原 ≤0.5%/≤2% 比例判据作废 |
| 4 | aggregate decode **TPS ≥ 500** ∧ **per-Agent ≥ 60**（c8 目标均线联立：60×8=480 <500 → aggregate 强制均 ≥62.5） | ≥500 / ≥60 | 原 TPS≥450 作废 |
| 5 | **avoidable history recompute = 0%** | 0% | Gate A 语义（原 recompute≤5% 作废） |
| 6 | **DEVICE_QUOTA pathological wait = 0** | 0 | 排除 FRONTIER 正常等待 |
| 7 | 稳态 **kv_available min > 0**（工作集 resident）；若消失 → **降 r=0.30 重跑该 cell** 或触发 descent（§3.3） | min>0 | protocol §③.3-5 保留 |

FAIL 类型（Gate D 语境）：
- **FAIL-D-select**（descent 触发）：任一主判据不达 → **降并发**(c8→c6→c4) 重测，不再用"相对 60%"等松绑。
- **FAIL-挤压**：kv_available min=0 且 avoidable recompute>0（池迫运行）→ 降 r=0.30 重跑该 cell 后再判，或先走 descent。
- **FAIL-运行**：OOM/BackendError/HTTP error/zero-progress/finished<100%/sha16 空。
- **FAIL-数据**：稳态窗 <150 请求（统计力不足）→ 标记不硬判。

### 3.3 ③ 整体判定（Gate D：max effective concurrency）

```
③ 整体（Gate D）：
  c8 verdict = PASS / FAIL（全 7 判据 AND；8/8 200 不算 PASS）
  if c8 PASS  -> N* = 8
  elif c6 PASS -> N* = 6（c8 失败原因如实报告：TTFT p99 / per-Agent TPS / avoidable ...）
  elif c4 PASS -> N* = 4（canary 底）
  else         -> N* < 4；报告各 N 退化曲线（c8->c6->c4 的 TPS/TTFT/avoidable 单调性）与限制因子
  汇总句（N*=8 例）："3090 在 r* 下稳定支持 N=8 个 active Agent × 55K history × 256-token output
    （TTFT p50/p95/p99 = a/b/c s，>30s=0，per-Agent >= 60，aggregate >= 500 tok/s，
     avoidable recompute=0%，DQ pathological=0，zero-progress=0，kv_available min=m>0）"
```
- **与 ② 衔接**：② 出 r*（≥C2 档配置被 ③ m3-1 复验）；③ 任一主 cell FAIL-挤压 → 按 ② 规则降 r=0.30 重跑该 cell 后 descent 再判；③ 完 → ④（已授权）。
- **descent 内部一致性**：c6/c4 cell 的 workload 与 c8 逐项同构（同 H0、同 output 256、同 seed 语义），仅并发不同 → 各判据可比。

### 3.4 报告/输出模板（主对照表 + 汇总句）

```
③ capacity curve 对照表（Gate D：r*=0.33，FP8，output 256，Graph ON，c=N）

| cell | N | H0(R) | WS | kv_used max/p90 | kv_avail min | dev:host:stor(tok/%) | avoidable% | TTFT p50/p95/p99/max | >30s | >60s | TPS agg/(/N) | GPU util | DQ-path | zero-prog | finished% | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m3-1 | 8 | 55k(19) | 464K | 450K/.. | 38K | ../../.. | 0% | 0.4/1.8/4.2/28 | 0 | 0 | 562/(70) | 92% | 0 | 0 | 100% | PASS -> N*=8 |
| m3-2 | 6 | 55k(25) | 348K | .. | .. | .. | 0% | .. | 0 | 0 | .. | .. | 0 | 0 | 100% | PASS（descent 反射）|
| m3-3 | 4 | 55k(38) | 280K | .. | .. | .. | 0% | .. | 0 | 0 | .. | .. | 0 | 0 | 100% | PASS（canary）|
| m3-4 | 8 | 50k(19) | 405K | .. | .. | .. | 0% | .. | 0 | 0 | .. | .. | 0 | 0 | 100% | PASS（可选）|
| m3-5 | 8 | 80k(19) | 645K | .. | 0 | .. | >0% | .. | >0 | >0 | .. | .. | >0 | 0 | 100% | overshoot（非 FAIL）|

③ 整体（Gate D）：max effective concurrency N*=8 -> "3090 稳定支持 8 active Agent x 55K...（全文见 §3.3）"
```

## 4. ③ 执行序 + R1-R9 中 ③ 生效规则（**GATED** 修订）

### 4.1 ③ 执行序（接 ② 之后；Gate D 测量前置项并入 Step 0）

```
Step 0  先决：② 完成 -> r* 定稿；55k tier 补丁（A）落地 + 24052 同步；
        **Gate D 前置**（新增）：output 256 参数（§1.3）；aggregate/per-Agent TPS 聚合段（§4.0，tester 或 coder 补丁）；
        avoidable recompute 分类段（§4.0）；24052 idle(0%/15MiB)+md5 复核+/data free
Step 1  m3-1 (N=8×55K)：Gate D 主目标 c8。boot -> engine-alloc 核对（max_running=8、r*、KV 池实测、graph ON）->
        prime(8 COLD) -> 稳态(R=19) -> 采集/断言 -> verdict（c8 PASS？）
Step 2  m3-2 (N=6×55K)：c6。若 c8 PASS 仍跑（descent 反射点 + 趋势）；若 c8 FAIL -> 本 step 即 descent 判据反射
Step 3  m3-3 (N=4×55K)：c4 canary（descent 底；不再 R8 相对 60%）
Step 4  （预算内可选）m3-4 (8×50K)、m3-5 (8×80K)：80K 按 overshoot 单元报告
Step 5  exit grid：对照表 + N* 整体判定 + 汇总句（§3.3/3.4）；环境复原（namespace 清理、GPU idle、md5 复核）
Step 6  汇合报告 -> ③ 完 -> ④（R1 已裁决，两语义）
```
- 每 cell：boot ≈7.3min + cell ≈ 6-10min ≈ 13-17min/cell；main 3 cells ≈ 40-50min；含可选 5 cells ≈ 65-85min GPU（预算内，protocol-e1:268）。

### 4.2 R1-R9 中 ③ 生效规则（**按 Gate D 重标注**）

| 规则 | Gate D 下 ③ 生效处理 |
|---|---|
| **R7（c=N）** | **仍适用（硬）**：`--max-running-requests=N`；驱动 #agents=N 线程（N<8 不注入 8）。mid-run `num_running_reqs max` 必须=N；N<8 温启动慢 -> 如实记录实际 running，不判 FAIL-活性。 |
| **R8（N=4 降格）** | **被新裁决取代（ledger:2512 "c8 不达降 c6" 权威）-> R8 旧"相对 60%"语义作废**。新语义 = **descent search**：c8->c6->c4 找最大满足 Gate D 全判据的 effective concurrency；N=4 是最小 canary（PASS 即为 N*=4），无降格松绑。**冲突解决：新裁决 >> R8**。 |
| **R5（λ 调节）** | 调整：③ 并发自由运行（TCP backpressure）。Gate D output=256 使稳态 decode 量≈38.4K tokens（150×256）-> 稳态时长下限 ~64-77s；若某 cell GPU util<70% 或 turns 未喂饱 -> 如实记录空窗，不静默加并发；窗口请求<150 标 FAIL-数据。 |
| **R6（history 文本统一）** | **仍适用**：统一 `_CORPUS` 确定性文本 + 每 session 唯一 marker（跨 cell 可比；影响 FP8 数值/radix 分布）。 |
| **R9（FP8 scale=1.0）** | **仍适用**：FP8 默认 scale-factor=1.0 为已知近似；③ 出现 hit-count/correctness 异常（sha16 失败/cached_* 崩坏/avoidable 异常跳）-> **先升级诊断再信容量数字**。 |
| R2（clamp warning） | 仍适用（继承）：③ 沿用 memory-computed 池；boot 出现 clamp warning -> 记录 warning 值、退顶格 600000 标注 cap 值。预期 r*≈498K 无 clamp。 |
| R4（free VRAM<1.2GB） | 仍适用（继承）：每 cell boot 后确认 `startup_available_gpu_memory_gb >= 1.2`（e2 实测 1.74）。 |
| R3（mamba dtype） | 仍适用（继承）：float32 对齐 e2；③ 不 mid-sweep 切换（池不足->回调 ② 降 r，不切 bf16）。 |
| **R1（④ 磁盘预算）** | 已用户裁决（ledger:2468-2476）：不影响 ③；③ 每 cell namespace 独立 /data 清洁。 |

### 4.3 健康断言 & 环境复原（每 cell）
- all HTTP=200 ∧ all finished ∧ sha16 非空 ∧ **0 zero-progress** -> 否则诊断 + FAIL-运行。
- run 后 SIGTERM + 回 15MiB idle；namespace 清理；deploy md5 复核（495b8851/465b6c68）；22151 未动；/root/engine-<cell>.log 保留。

## 5. 与 coder 驱动参数对齐清单（Gate D 修订；55k 补丁已另派）

| # | 项 | 现状 | 需要 | owner |
|---|---|---|---|---|
| 1 | **加 55k tier（不变，已派）** | TIER_TARGETS 仅 50k/80k | `"55k":55000`（**主矩阵依赖**） | coder（补丁已另派，同步 24052） |
| 2 | **修 --tier default=64k 非法（不变，已派）** | default="64k" ∉ choices -> 不带 --tier 必崩 | 补 64k 或改 default（如 "50k"） | coder（同上） |
| 3 | **output 256 标准档（新）** | `--cold-max-new 12 / --warm-max-new 64` | 调用改为 256/256（**tester 照 §1.3，无需改动**；若需 driver 内置标准档选项 `--output-tokens 256` 则 coder 可选） | tester（调用级） |
| 4 | **aggregate/per-Agent decode TPS 聚合（新，决策标注）** | driver 无聚合（verdict.json 仅 counts；逐行 completion_tokens 有） | **决策：tester 在现成 gate2_analyze 口径聚合 runs.csv（Σ completion_tokens/稳态窗；per-agent）**；可选 coder 在 write_outputs 加 summary（aggregate_tps/per_agent_tps） | tester（主）/ coder（可选非阻塞） |
| 5 | **avoidable recompute 分类段（新）** | 驱动按 turn 记 prompt_len/hits | tester 分析段：`avoidable=prompt_len−hits−delta−tail(≤256)`；cold prime 排除 | tester |
| 6 | 55K 截档 token 精确性 | tokenizer 精确截档 + history_tokens 记录 + assert H0±2% | tester 24052 dry-run 确认实际 token 数（64K->64030 先例） | tester |
| 7 | 分析复用 | gate2_analyze.py / runner warmctx_analyze.py | ③ 长尾/TPS 聚合基础可复用；per-N descent 对照建议轻量 `cap3_analyze.py`（可选 coder） | tester（先用现成） |

## 6. Alternatives / 关键取舍（Gate D 修订）
1. **descent（c8→c6→c4）vs 旧 3 档并列判据**：新裁决（ledger:2512）定 descent——"c8 8/8 200 不算成功，不达降 c6"。旧"N=4 相对 60%"松绑作废 -> 本 spec 的 c6/c4 cell 为 descent 反射/canary，非独立 PASS 空间。若偏好仍列全 3 档对照（信息性）-> 全档保留在对照表（§3.4），但整体结论只取 max PASS N*。
2. **H0=55K 主判据 vs 50K 代理**：不变——主矩阵坚持 55K（用户裁决）；50K 仅可选下界探针；55k tier 未落地前不派主矩阵。
3. **output 256 对 warm delta 语义**：warm_max_new=256 使每 turn completion 256 tokens（Gate D 标准）；delta（新 user 消息）仍短——稳态 decode 是主要 time-budget（~64-77s/150req 下限），经 §4.0 口径计量。
4. **m3-5 80K**：80K 装不进 498K 池 -> 定位 overshoot 退化探针（non-PASS/FAIL 判定）；预算紧则最后跑或不跑。
5. **区别对待 RH**：③ 全部 RH OFF（Gate D 判据不含 RH 承诺）；RH 的"Host-ready-before-admission ≥95%"属 Gate C/④ 验收，③ 不混入。

## 7. followups
- **coder**：55k tier 补丁（§2.2 A，已另派）+ default 修复；可选：output 256 标准档选项、write_outputs 加 TPS summary、cap3_analyze.py。
- **tester**：③ 前置（output 256 调用 + TPS 聚合段 + avoidable 段）就绪后按 §1.1/§4.1 照跑 m3-1->m3-2->m3-3（descent 语义）-> 可选 m3-4/5；报告按 §3.3/3.4（Gate D 全表 + N*）。
- **② 汇合**：③ 依赖 ② r*；② C2 档与 ③ m3-1 同源复验。
- **④（后续）**：④ 驱动两语义修改（coder，parked-v2）+ Gate A/B/C spec（architect e5）；④ 判据加严（S=100 fit 正式验收 / S=500-1000 oversubscription 退化曲线 + recompute 归因 + RH ON/OFF A/B）。

## open_issues
- **55k tier（§2.2，主矩阵阻塞）**：补丁已另派 coder；落地 + 24052 同步后 tester 接 ③。架构推荐不变（选项 A）。
- **aggregate/per-Agent TPS 聚合（§4.0/§5 #4，Gate D 测量前置）**：driver 无此输出；决策 = tester 聚合（现成口径）或 coder 可选补丁。需在 ③ Step 0 前确认路径。
- 55K 实际 token 数需 24052 dry-run 确认（风险低）。
- avoidable recompute 0% 的 tail_budget（256 token）为 TRAILING_PAGES 允许量的估算值；若实测出现可解释的少量"delta 超尾重算"，记录并从 avoidable 中归因（Gate A 允许集合），不误报。

---

## Return envelope（e1-r2 / GATED）

```text
status: done
artifacts:
  - spec（e1-r2/GATED，supersedes 旧判据）：/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e4-architect-e1.md
evidence:
  - ledger.md:2480-2536（4 硬 Gate 权威版：Gate A/B/C/D + parked 两档 + "③ 判据升级 Gate D 旧判据全废"）
  - gate3_capacity.py:291-317（write_outputs 确认无 aggregate TPS -> §4.0 测量前置项）
  - 其余同上 e1
summary:
  Conclusion: ③ spec 已按 Gate D 全量修订（e1-r2/GATED，同文件新版本段，标注 supersedes）。
    - 判据表整体替换：c8 目标 aggregate>=500 / per-Agent>=60 / TTFT p50<=2s. p95<=5s. p99<=10s / >30s=0.>60s=0 / avoidable history recompute=0% / DQ pathological=0 / OOM.HTTP error.zero-progress=0；旧 p99<=40s / TPS>=450 / >30s>60s 比例 / recompute<=5% 全部作废。
    - 判定变为 descent search（c8->c6->c4，max effective concurrency N*）；"c8 8/8 200"不算 PASS；R8 旧"相对 60%"语义被新裁决取代（新裁决 >> R8）。
    - workload 固定：output 256 tokens 标准档（--cold-max-new 256 --warm-max-new 256）、FP8、② 最终 profile、Graph ON。
    - 55k tier 补丁推荐不变（§2.2 选项 A，已另派 coder）。
    - 测量缺项确认：gate3_capacity.py 无 aggregate output tok/s -> 决策 = tester 现成口径聚合（可选 coder 补丁），列入 §4.1 Step 0 前置。
  Current Architecture: ② 定稿配置继承（r*+graph bs8+c8+RH OFF+L3 200G+memory-computed 池）；gate3_capacity.py；gate2_analyze 口径。
  Problem / Forces: 55k tier 阻塞（已派）；Gate D 需要 output-256 调用 + TPS 聚合 + avoidable 分类（新测量前置）；descent 语义与旧 R8 冲突已按新裁决解决。
  Proposed Architecture: Gate D 档位矩阵（m3-1..5，output 256）+ 8 列判定表（Gate D 目标）+ descent 判定（max N*）+ ③ 执行序（Step 0 含新前置）+ R1-R9 重标注（R7 适用、R8 被取代、R5/R6/R9 适用）。
  Alternatives: descent vs 3 档并列（整体只取 max N*，对照表仍列全档）；80K 作 overshoot 探针；RH 属 Gate C/④ 不混入 ③。
  Migration / Impact: 零产品代码改动；coder 依赖 = 55k tier 补丁（已派）+ 可选 TPS summary；tester 需按 Gate D 前置（output 256、聚合段）闭环。
  Open Decisions: aggregate TPS 聚合路径（tester 聚合 vs coder 补丁）——本 spec 决策 = tester 现成口径优先（§5 #4 标注）。
open_issues:
  - 55k tier（§2.2）= ③ 主矩阵阻塞，补丁已另派 coder，落地+同步后接 ③。
  - aggregate/per-Agent TPS 聚合（Gate D 专属测量前置，§4.0/§5 #4）：driver 缺输出；tester 现成口径聚合或 coder 可选补丁，需 Step 0 前确认。
  - avoidable recompute tail_budget（256 token 估算）若出现可解释的 delta 超尾重算需归因处理（Gate A 允许集合）。
```