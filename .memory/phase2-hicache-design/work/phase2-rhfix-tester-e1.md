# phase2-rhfix-tester-e1 — Fix A/B 集成验证（确定性复现 + A/B + gate）

- status: **done**
- epoch: e1
- owner: tester
- 任务: 在实验机 24052 上执行 Fix A/B 集成验证（确定性复现 + A/B + gate），P1 关键验证环节
- 机: 175.155.64.171:24052（root）；GPU 0%/15MiB 空闲；/data 起始 10%（170G free）
- 代码: /root/sglang-b1-continuity（非 git，editable install 映射到此）；patch=/root/rhfix-a-b.patch（356 行）
- 模型: /root/models/Qwen3.5-9B-w4a16（Qwen3.5-9B-w4a16 GPTQ）；env=sglang-patch
- 驱动: /root/gate3_ab.sh；启动: direct-launch-gate1-rhon.sh（RH ON，唯一 diff +--enable-ready-horizon）

## 0. 环境/前置核实（均通过）

- editable install 核实：`pip show sglang` → Editable project location = `/root/sglang-b1-continuity/python`；import 的三个模块 file 均指向该树 → patch 生效路径正确。
- 基线核实：patch 应用前 ready_horizon.py `host_release`=0、hicache_restore.py `DEVICE_QUOTA_MAX_TIMEOUTS`=0（= 冻结基线）；apply 后 =7 / 3；`patch -p1 -R` 干净回滚。
- patch dry-run 干净应用；import 检查通过：`CausalEpochs.host_release` 存在、`DEVICE_QUOTA_MAX_TIMEOUTS=2`、`device_quota_degraded(2)=True`、`(1)=False`。
- 原 B trace 完好：`/root/engine-gate3-ab-a-on.log` 复核 = 基线复现基准（见 §2）。
- /data 起始 10%（170G free），GPU 空闲，无残留引擎/锁。

## 1. 执行记录（5 run 全跑，每个 30min / rc=0）

| # | tag | 代码 | 磁盘起始 | 说明 |
|---|---|---|---|---|
| 1 | rhfix-bl-on | 基线 | 170G free | 阶段1 基线（RH ON）复现尝试 |
| 2 | rhfix-fx-on | fixed | ~95G free | 阶段2 fixed；**磁盘被 stage1 的 84G 文件占住，起始仅 ~95G free（confound）** |
| 3 | rhfix-bl2-on | 基线 | 170G free | 基线重跑（干净磁盘） |
| 4 | rhfix-fx2-on | fixed | 170G free | **fixed 干净磁盘（正确对照）** |
| 5 | rhfix-blp-on | 基线 | ~86G free | 基线在匹配磁盘压力下（filler 模拟） |

全部 COMPLETE rc=0；GPU 每 run 后回 idle；证据目录保留 `/root/evidence-gate3-*/`。

## 2. 原 B trace 复核（preserved baseline，确定复现签名）

`python3 /root/rhfix_collect.py ab-a-on 7200`（full 7200s）：
- first recycle +126.5s；recycles 36,488；**distinct_gen 36,124**（thrash）
- restore_success 21（最后 +121.1s，永久冻结）；ready_pool 37（最后 +121.7s，永久冻结）
- recompute 9,128（miss 9,110 / timeout 18）；DEVICE_QUOTA WAIT 6,351；extent_write 1,371 GiB
- 与 forensics 报告（36,527 recycle / 36,163 gen / 9,122 recompute / 6,356 DQ）一致（微小差为事件格式/窗口边界）。

## 3. 阶段1-2-3 执行与关键发现：磁盘 confound

### 3.1 阶段1（基线, 170G free）未复现冻结
- restore_success 272（最后 +1712s，持续增长）；ready_pool 511（最后 +1713s，活跃）
- recycles 1,316 / distinct_gen 5（健康 cursor-wrap）；recompute 1,577；DEVICE_QUOTA 1,797
- **结论：clean-disk 下基线不复现原始 B 冻结。** 与 dispatch 预设一致（/data 清理改变了环境）。

### 3.2 阶段2（fixed, ~95G free）出现冻结+thrash → 初判疑似回归
- restore_success 87（**冻结 +359.9s**）；ready_pool 164（冻结 +361.0s）
- recycles 8,205 / distinct_gen 7,508（thrash）；recompute 2,352；gc/evict 日志 895 行

### 3.3 磁盘 confound 判别（决定性）
- 阶段2 起始时 stage1 的 84G 数据文件仍在盘上（我仅在 stage2 完成后清理）→ 起始仅 ~95G free。
- 阶段2 累计写到 +360s ≈94 GiB，磁盘 free 跌破 min_free=10G → **磁盘 GC（_gc_evict）触发** → thrash。
- 对照：三个 clean run（170G free）文件到 84G 时 free≈95G > 10G → 永不触发磁盘 GC → 健康。

### 3.4 决定性对照：fixed clean（fx2-on）vs baseline clean（bl2-on）
- **fx2-on（fixed, 170G free）**：restore_success 263（最后 +1784s 活跃）；ready_pool 495（+1785s 活跃）；recycles 1,473 / distinct_gen 5（健康）；recompute 1,881；gc/evict 311。
- **bl2-on（基线, 170G free）**：restore_success 270（+1796s）；ready_pool 505（+1797s）；recycles 1,338 / 5；recompute 1,712。
- **fixed clean 与 baseline clean 统计不可区分（均健康，无冻结无 thrash）。**

### 3.5 匹配磁盘压力对照：baseline（blp-on, ~86G free）
- restore_success 87（**冻结 +344.1s**）；ready_pool 159（冻结 +344.6s）；recycles 8,066 / distinct_gen 7,440（thrash）；recompute 2,308；gc/evict 315。
- **与 fx-on（fixed 磁盘压力）几乎逐项一致：restore_success=87 vs 87、ready_pool=164 vs 159、distinct_gen 7508 vs 7440、recompute 2352 vs 2308。**
- → **冻结+thrash 是磁盘 GC（min_free=10G 跨越）的环境效应，与 fix 无关。** Fix 不引入冻结；原始 B 的冻结复现需要磁盘压力（clean 环境不再具备）。

## 4. 分阶段证据表（全 run 对比）

| Run | 代码 | 磁盘起始 | restore_success(最后) | ready_pool(最后) | recycles | distinct_gen | recompute | DQ waits | 首recycle | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| ab-a-on(原始B) | 基线 | 100%满 | 21 (+121s 冻) | 37 (+121s 冻) | 36,488 | 36,124 | 9,128 | 6,351 | +126.5s | 冻结+thrash |
| bl-on | 基线 | 170G | 272 (+1712s 活) | 511 (+1713s 活) | 1,316 | 5 | 1,577 | 1,797 | +344s | 健康 |
| fx-on | fixed | ~95G | 87 (+359s 冻) | 164 (+361s 冻) | 8,205 | 7,508 | 2,352 | 1,697 | +330s | 磁盘GC冻结 |
| bl2-on | 基线 | 170G | 270 (+1796s 活) | 505 (+1797s 活) | 1,338 | 5 | 1,712 | 1,871 | +344s | 健康 |
| fx2-on | fixed | 170G | 263 (+1784s 活) | 495 (+1785s 活) | 1,473 | 5 | 1,881 | 1,983 | +321s | 健康 |
| blp-on | 基线 | ~86G | 87 (+344s 冻) | 159 (+344s 冻) | 8,066 | 7,440 | 2,308 | 1,682 | +331s | 磁盘GC冻结 |

## 5. Fix Gate 评估（基于 clean-disk 受控 A/B：bl2-on vs fx2-on）

- **Gate A（ready_pool 不永久冻结）**：fixed clean 不冻结（495 活跃到 +1785s）；matched 磁盘压力下 baseline 与 fixed 都冻结（等效）→ **不成立（无 fix 引发的冻结）**。
- **Gate B（restore_success/storage_hit 恢复增长）**：fixed clean restore_success 263 活跃增长；storage_hit 2.349M / input 5.531M。无回归。
- **Gate C（DEVICE_QUOTA ≤2 timeout 后 progress）**：clean run 均未出现病理 WAIT→recompute→WAIT 环（timeout 仅 2-5 次 vs 原始 B 20；clean 均恢复）。**病理模式未在 clean 环境触达，机制未被压力场景验证**（见 §7 limitations）。
- **Gate D（9K recompute storm 收敛）**：fixed clean recompute 1,881 vs baseline 1,712（+10%，量级相当）；无 9K storm。
- **Gate E（36K gen thrash 消失）**：fixed clean distinct_gen=5（健康 cursor-wrap），无 thrash。**成立（clean 环境）**。
- **Gate F（early recycle 可解释）**：clean run 仅健康 cursor-wrap；磁盘压力 run 的 recycle 由磁盘 GC 解释（两代码等效）→ **可解释**。
- **Gate G（RH clean-window 优势保留）**：fixed clean storage_hit rate=42.5%（2.349/5.531M）vs baseline 48.4%（2.640/5.454M）→ **约 -6pp，略降**，在 run 方差内但需 flag（见 §7）。
- **Gate H（correctness/OOM/zero-progress/HTTP）**：两 clean run HTTP errors=0、OOM=0；t38c 零进度探针无异常。**成立**。

## 6. 结论（final 汇报六问）

1. **baseline 是否成功复现**：**未在 clean 环境复现原始 B 的病理冻结**。原始 B 的冻结需磁盘压力（100% 满 / min_free 跨越）；clean 10% 下基线健康（272 restore_success 持续增长）。但**匹配磁盘压力下基线（blp）复现了冻结+thrash（87 冻结 +344s / 7440 gen）**，证明复现条件 = 磁盘压力，非代码差异。
2. **Fix 后 ready_pool 是否恢复**：clean 环境两代码都无冻结（fixed 495 / baseline 505 均活跃），无 fix 引入的冻结；匹配磁盘压力下两代码同样冻结 → fix 未改变冻结行为（无回归，也未在压力下治愈——见 §7）。
3. **DEVICE_QUOTA 是否真 progress guarantee**：**未能在本实验验证病理环路被打断**。clean 环境未出现病理 WAIT→recompute→WAIT 环，故 Fix B 的有界降格机制（DEVICE_QUOTA_MAX_TIMEOUTS=2）未被压力路径真实触发。unit 层 coder 已验证（本机 sglang-patch env 无 pytest，未能本机复跑 unit），运行时证据缺失。**NOT_ESTABLISHED**。
4. **recompute/miss storm 与 gen thrash 前后数量级**：clean 环境 fixed recompute 1,881 vs baseline 1,712（无 storm）；distinct_gen 5（无 thrash）。磁盘压力下两代码 distinct_gen ~7,400-7,500（thrash，磁盘 GC 驱动，与 fix 无关）。
5. **RH clean-window 收益是否保留**：fixed clean storage_hit rate 42.5% vs baseline 48.4%，**约 -6pp 略降**（单次 run，方差内，需更多重复确认）。restore_success 持平（263 vs 270）。
6. **是否具备进 2h soak / 开 RH optional 资格**：**clean 环境（当前 /data 10%）下 fixed 与 baseline 等效、无回归、gate H 全过**；但 Fix A/B 的核心声明（打断 DEVICE_QUOTA 死循环 / 治愈 ready_pool 冻结）**未在运行时压力场景得到验证**（clean 未出现病理，压力场景下 fix 未治愈）。**进 2h soak 的前置 = 需要在磁盘压力/容量耗尽场景下验证 Fix A/B 确实治愈冻结**，否则 soak 只是重复 clean 健康路径，不验证 fix 的实质。

## 7. limitations / open_issues

- **Fix B 机制未在运行时压力路径真实触发**：clean 环境无病理环路；匹配磁盘压力下两代码都冻结（fix 未治愈），但 blp/fx 的冻结根因是磁盘 GC（min_free=10G 跨越），与 Fix A/B 针对的"host headroom 冻结 + WAIT→recompute→WAIT"环路**不完全是同一路径**——磁盘 GC 冻结是 extent 层回收 churn 导致的 restore key 失效，而 Fix B 针对的是 DEVICE_QUOTA 出口。二者是否耦合，需在**纯容量耗尽（非磁盘 GC）场景**（如 MAX_SIZE/FILE_SIZE 更小以在 170G 盘上触达容量上限、或提升 write rate 让 90G 文件快速填满而不触发磁盘 GC）下隔离验证。
- **Gate G 的 -6pp storage_hit 差异**：single-run，可能为 run 方差；建议在 soak/重复 run 中确认。若为真实，需评估是否 RH 预取行为被 Fix A（host_release epoch 唤醒）改变。
- **Disk confound 溯源**：阶段2 起始磁盘仅 ~95G free（stage1 84G 文件未清理）是本实验最大的环境坑；已用 fx2/blp 双对照完全隔离。后续验证必须在每次 run 前确认 /data 回 10% 且无残留大文件。
- **unit 测试**：coder 已在 HEAD 跑通 346 passed（含 Fix A/B target 14 passed）；本机 sglang-patch env 无 pytest 模块，未能本机复跑 unit——非产品缺陷，属本机 tooling 限制。
- **原始 B 复现条件**：原始 B 冻结发生于 /data 100% 满 + 90G 文件 + 容量耗尽叠加。当前 /data 已清理至 10%，纯粹复现原始条件需重新制造磁盘压力（不建议，违背 /data 水位纪律）。blp 用 filler 模拟磁盘压力已证明冻结是磁盘 GC 效应。

## 8. 产物/证据路径

- 远程日志：`/root/engine-gate3-{rhfix-bl-on,rhfix-fx-on,rhfix-bl2-on,rhfix-fx2-on,rhfix-blp-on}.log`
- 远程证据：`/root/evidence-gate3-{...}/`（metrics-final / join.log / gpu-util.csv / t38c-probe.log）
- 分析脚本：`/root/rhfix_collect.py`（本 tester 独立编写，事件级采集）
- 原始 B trace：`/root/engine-gate3-ab-a-on.log`（未改动）
- patch：`/root/rhfix-a-b.patch`（未改动；验证 dry-run/apply/revert 干净）
- 本报告：`.memory/phase2-hicache-design/work/phase2-rhfix-tester-e1.md`

## 9. 环境最终状态
- 代码：基线（patch 已回滚，flags 0/0）——交付态待 orchestrator 决定
- /data：10%（170G free）；GPU：idle 0%/15MiB；无残留引擎/锁
- 未追加第三个启发式修复；未改任何产品代码逻辑（仅 apply/revert patch）

---

# STRESS 追加段（coordinator 第二轮收紧标准后）

> 本节按 coordinator 第二轮指令（三容量分离 / filesystem-GC=0 前置 / A/B/C 三态判定 / Fix A·B 硬证明 / 无法构造如实回报）追加。**本轮改变了第一轮结论的方向**：在纯容量耗尽（非磁盘 GC）场景下，**FIXED 崩溃冻结，BASELINE 存活** —— 与 Fix 预期方向相反。

## S1. 三容量分离设计与可构造性

| 容量 | 定义 | 本机触发路径 | 结果 |
|---|---|---|---|
| ① 文件系统 free | min_free=10G 阈值，跨越触发 extent `_gc_evict` | 维持 /data≥12%（磁盘 GC=0） | 全程未跨越（磁盘 12-14%，GC=0）✅ |
| ② L3 extent 逻辑 | FILE_SIZE=30G × 447 slots ≈ 200G max | MAX_SIZE=200G/FILE_SIZE=30G | 已达 extent 容量上限（大量 extent_recycle cursor-wrap）✅ |
| ③ Host cache/headroom | `mem_pool_host` = device_pool × hicache_ratio(1.5) ≈ 98304 tokens；headroom = available + ready_resident | 高并发工作集压满 host pool | ready_stage headroom 打到 0（12 次），但 **NO_HEADROOM 状态字符串从未出现**（Fix A 目标状态未以可观测形式触发）⚠️ |

- **Host 容量不可直接缩**：`mem_pool_host` 大小 = `device_pool.size × hicache_ratio`，由 `max_total_tokens=65536` 与 `hicache_ratio=1.5` 固定（`pool_host/base.py` 无 host-only 尺寸 knob）。缩 host 需改 max_total_tokens 或 ratio（会连带改 device pool），**不改产品逻辑前提下无法只缩 ③**。
- **③ 触发了但不可观测**：headroom 数值到 0（12 次），说明 host pool 确实被压满；但 `headroom_fits` gate 失败走 `_park_ready_decline`（NO_HEADROOM 归因），**不打印状态字符串**，日志无 `NO_HEADROOM`/`WAIT_HEADROOM` 可观测事件。故 Fix A 硬证明（NO_HEADROOM→release→epoch bump→waiter→progress）在本机日志格式下**不可直接观测**。
- **Fix B 硬证明（WAIT→T13 timeout→recompute/admit→decode/output 闭环）**：可在纯容量下观测（DEVICE_QUOTA WAIT 1036 次、T13 recompute-timeout 14 次、recompute-miss 1364 次、restore_success 闭环存在）——**但闭环最终被崩溃打断，而非被 Fix B 治愈**。

## S2. 执行记录（matched 纯容量 A/B，filesystem GC=0）

| # | tag | 代码 | 配置 | 磁盘 | 结果 |
|---|---|---|---|---|---|
| str-bl | rhfix-str-bl | **基线** | agents=8 rt=400 MAX_SIZE=200G FILE_SIZE=30G budget=1800 | 14%→10% | 存活满 1800s，0 失败 |
| str-fx(partial) | rhfix-str-fx | fixed | 同 | - | ~10min 被杀（首次尝试，弃用） |
| **str-fx2** | rhfix-str-fx2 | **fixed** | 同 str-bl（完全一致） | 12%（GC=0） | **+1239s 崩溃冻结，2863 请求失败** |

## S3. 决定性证据（str-fx2 fixed 崩溃 vs str-bl baseline 存活）

**崩溃根因**（`/root/engine-gate3-rhfix-str-fx2.log` 115925-115967）：
```
Scheduler hit an exception: Traceback (most recent call last):
  .../scheduler.py:4491 _get_new_batch_prefill_raw -> add_one_req
  .../unified_radix_cache.py:4031 init_load_back -> load_back
  .../unified_radix_cache.py:1983 _load_back_transfers -> evict_for_alloc
  .../unified_radix_cache.py:801 _evict -> writing_check -> _flush_pending_storage_writes
  .../unified_radix_cache.py:2144 write_backup_storage -> _execute_and_commit_kv_backup
  .../unified_tree_core.py:2037 build_backup_spec -> assert device_value is not None
AssertionError
```
崩溃后 py-spy watchdog（05:14:59）+ SIGQUIT + kill_process_tree → 引擎死，此后全部 2863 客户端请求 connection refused。

**关键对照**：

| 指标 | str-bl（基线） | str-fx2（fixed） |
|---|---|---|
| restore_success | 110（活到 +1788s） | 59（+1003s 后几乎停滞） |
| 请求 ok/failed | 573 / **0** | 369 / **2863**（全在崩溃后） |
| **pre-crash 请求吞吐（0-1200s）** | **364** | **364（完全匹配）** |
| forced_drop_to_miss | 2 | **125** |
| promotion_release cause=exception | 0 | **1** |
| Scheduler 异常/崩溃 | **0** | **1（build_backup_spec assert）** |
| 存活时长 | 满 1800s | **冻结 +1239s** |
| 磁盘水位 | 12-14%（GC=0） | 12%（GC=0） |
| extent gen（recycle 健康度） | 1-15 cursor-wrap（3634） | 1-8 cursor-wrap（1896） |

- **pre-crash 吞吐完全匹配**（两 run 各 364 ok 请求/0-1200s）→ 请求量差异（573 vs 3232）**不是预存 confound，而是崩溃的后果**：2863 个"失败"全部发生在崩溃时间戳（1788642894）之后。
- **磁盘 GC=0**（disk 12-14% 全程）→ 非磁盘压力路径。**纯容量耗尽路径下，fixed 崩溃，baseline 存活**。

## S4. 并发隔离核实

- 实验中存在另一 worker 的 run `rhfix-ba20`（baseline flags 0/0，agents=8 rt=400 MAX_SIZE=200G FILE_SIZE=20G），**启动于 05:18:23，晚于 str-fx2 崩溃（05:14:54）约 3.5 分钟**，与 str-fx2 运行期无重叠 → 不构成对 str-fx2 证据的并发干扰。
- 该 run 已将 patch 回滚为基线（0/0）——**交付态被第三方 worker 改写**，与我的验证无冲突但需记录。

## S5. 三态判定（coordinator A/B/C）

**结论 = C（FAILED，最坏情形）**：

- **A 不成立**：baseline（str-bl）在纯容量下并未出现"WAIT/recompute 死循环且无法恢复"——它存活满 1800s。原 B 的死循环在 clean 磁盘 + 纯容量耗尽下**不复现**（与 §3.1 一致），故 Fix 无从"治愈"一个不存在的基线环路。
- **C 成立（关键）**：在本轮唯一能同时满足"filesystem GC=0 + 纯容量耗尽 + fixed 真实运行"的匹配 A/B 中，**FIXED 崩溃（AssertionError + 硬冻结 + 全量请求失败），BASELINE 存活**。这不是"双方都恢复"（B），也不是"双方都不复现"（A），而是 **fixed 比 baseline 更差——引入崩溃回归**。

## S6. 修复与回归属性（诚实归因）

- 崩溃发生在**未被打补丁的** `unified_tree_core.py`（`build_backup_spec` 的 `assert device_value is not None`）——该文件与 `write_backup_storage` 路径均不在 patch 内。
- 但崩溃的**触发路径经过 patched 文件** `scheduler.py:4491`（`_get_new_batch_prefill_raw`），该函数含 Fix B 的 ADMISSION_DENY 重装 gate（patch hunk @@ -4460,7 +4505,27 @@）。崩溃发生在正常 admission→eviction→write-back，非直接位于 Fix B gate 代码行。
- 崩溃仅出现在 **fixed 纯容量 run**（str-fx2，唯一的 fixed 真实容量耗尽 run）。其余 4 个 earlier fixed/基线 clean 或磁盘压力 run 均未崩溃（0 次 Scheduler exception）。
- **属性待定（需 DEEP_DEBUG 归因）**：无法仅凭本证据判定崩溃是"Fix A/B 的 control-flow 变更将工作集推进到更深容量状态而暴露底层 backup 缺陷"，还是"纯容量新触发的既有 backup 缺陷（与 Fix 无关，但 fixed 因行为差异先到达该状态）"。**唯一已确立的事实**：同一配置下，baseline 存活、fixed 崩溃——按 coordinator 定义即 C（FAILED）。
- **Fix B 硬证明未达成**：DEVICE_QUOTA WAIT→timeout→recompute 环路存在（1036 WAIT / 14 timeout / 1364 miss），但被崩溃打断，未形成"decode/output 成功闭环"的治愈证据。
- **Fix A 硬证明不可观测**：NO_HEADROOM 状态无日志可观测（见 S1），headroom 数值到 0 但无法证明 release→epoch→progress 闭环。

## S7. 独立缺陷（record only，未修复）

- **filesystem min_free/extent GC → restore-key 失效 + recompute storm**（第一轮已确立，本轮再次确认）：磁盘 GC 触发时 restore-key invalidation → recompute storm + thrash（distinct_gen 7400-7500）。非本次 Fix 引入，record only。
- **新观察：`build_backup_spec` 的 `assert device_value is not None` 在纯容量耗尽 + 高压力 write-back 下可崩（str-fx2）**。此为备份路径的健壮性缺陷，需底层归因（是否 concurrent eviction 与 write-back 竞争导致 BASE 组件 value 被清空）。record only，不在本验证修复范围。

## S8. 更新后的结论（供 orchestrator）

1. 原 B 死循环**需磁盘压力才复现**（clean 磁盘不复现）——第一轮已定论，本轮纯容量亦确认（baseline 存活）。
2. **Fix 在纯容量耗尽（GC=0）下引入崩溃回归**（C：FAILED）——与第一轮"clean 环境无回归"的结论冲突，原因是第一轮 clean run 未触达纯容量耗尽 + fixed 同时运行的组合。
3. **Fix A/B 不可在现有日志下做运行时硬证明**（A 状态不可观测；B 闭环被崩溃打断）。unit 层证据保留（coder 346 passed），但**运行时压力证据为负向（C）**。
4. **不建议进 2h soak**：soak 前必须先解决 str-fx2 崩溃（backup 路径 assert），否则 soak 会在 fixed 下崩溃。建议回 architect 归因崩溃（DEEP_DEBUG_REQUIRED），并回到 coordinator 的 B 分支讨论是否降级为 defensive patch。

## S9. STRESS 段产物

- 远程日志：`/root/engine-gate3-rhfix-str-bl.log`（基线，存活）、`/root/engine-gate3-rhfix-str-fx2.log`（fixed，崩溃，含完整 traceback）
- 远程证据：`/root/evidence-gate3-rhfix-str-{bl,fx2}/`（join.log / driver.log / metrics-final）
- str-fx2 storage 已清理（/data 回 10-12%）；str-fx（首次 partial）弃用未计
- 崩溃 traceback：`/root/engine-gate3-rhfix-str-fx2.log` 行 115925-115967
- 并发核实：`rhfix-ba20`（他 worker）05:18 起，晚于崩溃，无重叠
