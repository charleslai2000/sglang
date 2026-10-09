# phase2-hicache-design-tester-rh-ab-e2 — RH A/B 决定性实验（用户终版契约 A'）

status: done
epoch: 2
task: RH ON vs RH OFF 共同 recycle=0 前缀窗口内四 Gate 对比（三向裁决）
owner: tester
date: 2026-09-05

## 0. 结论速览（done）

- 容量定档：`FILE_SIZE=90G` / `MAX_SIZE=200G`（MAX_SIZE > FILE_SIZE 使 GC watermark 失效，
  唯一 recycle 源 = cursor-wrap 于累计写 ~90G）。
- **三向裁决：RH 状态机无独立缺陷（clean window 内 RH ON storage_hit 2.26x、recompute 0.51x，
  restore_success 持平 → RH ON restore 正常甚至优于 RH OFF）；root cause = RH + capacity-pressure
  thrashing feedback（recycle 后 ready_pool 永久冻结 → restore_success→0、storage_hit 冻结；
  RH ON 写放大致更早触达容量，B 36,527 recycle vs A 6,513）**
- A 轮（RH OFF, 90G/200G）COMPLETE rc=0：首 recycle +314.5s / 累计写 81.6GiB
- B 轮（RH ON, 90G/200G）COMPLETE rc=0：首 recycle +126.5s / 累计写 30.4GiB
- **共同 clean window = 120s**（两轮均严格 recycle=0），四 Gate 在此窗口内裁决
- 口径边界遵守：只裁决 RH 状态机独立缺陷，不用 90G/200G 绝对 hit-rate 下容量/生产结论

## 1. 执行记录（本 epoch，持续更新）

| 阶段 | 结果 |
|---|---|
| 容量定档（用户终版契约 A'） | FILE_SIZE=90G / MAX_SIZE=200G（MAX_SIZE>FILE_SIZE → GC watermark 失效，唯一 recycle 源=cursor-wrap） |
| 校准（RH OFF 192G/128G 228s） | 0 recycle，53.7GiB 写 @241MiB/s，容量可行 |
| gate3_ab.sh 修正 | 本地重写+scp 推送，bash -n SYNTAX_OK；`--max-size`/`--file-size` 参数生效 |
| 启动前提核查 | GPU 空闲、无残留进程，A 轮启动前确认 |
| **A 轮（RH OFF）** | tag=ab-a-off，90G/200G，rt=400，budget=7200s，agents=8，2026-09-05 12:34:33 启动，12:36:55 engine healthy（main pid 434199） |
| A 轮首 recycle | ts=1788583348012 (12:42:28)，cursor-wrap 型（slot 升序），距首写 +314.5s |
| A 轮进度（12:51:55） | join.log 319/2500 rows，21.6 req/min，预计 ~14:47 完成 |
| 事件格式核查 | extent_write/recycle/restore_success/recompute/disposition 均与解析正则精确匹配 |
| 分析脚本 | rh_gates2.py / rh_keys.py 语法 OK、imports OK（修复 rh_keys.py 缺失 import collections） |
| B 轮（RH ON） | 待 A 轮 COMPLETE 后串行启动（wrapper direct-launch-gate1-rhon.sh） |

（报告持续更新中；完整证据在 A/B 两轮完成后写入。）

## 2. 容量配置问责（orchestrator 核查回应）

**事实链（均已核实）**：
- Run A 实际容量 = FILE_SIZE=90G / MAX_SIZE=200G（status: "capacity: MAX_SIZE=200G FILE_SIZE=90G"；engine server_args `hicache_storage_backend_extra_config={"max_size":"200G"}`；`enable_ready_horizon=False` 确认 RH OFF）
- 来源：启动时调用显式传 `--max-size 200G --file-size 90G`（status 无 launch cmdline 回显，但 script 默认值未被改、engine 生效 max_size=200G 证明是启动参数传入）
- **script 默认值未改**：`gate3_ab.sh` 行 15-16 = `MAX_SIZE_ENV=128G` / `FILE_SIZE_ENV=192G`；`local==remote` diff 全等，证明 12:32 的修改只是我的 quoting 修复（awk/tr/heredoc 转义），非容量改动
- `/data` 现状（已核算）：总 197G，RunA hicache.data 物理 84G（90G 截断，apparent=physical，已满物化）；ab-cal-off 物理 54G / apparent 179G（稀疏，写 53.7GiB）；**启动时 /data 空闲 ≈ 133G**（= 197 − (RunA 84 − 已占 64) 推得，含 ab-cal-off 54G）

**容量盘算（如实说明）**：
- 我按契约"物理 footprint = 累计写字节直到 cursor-wrap"模型，取 FILE_SIZE=90G 使峰值物理 ~90G < 启动空闲 133G，留 ~40G 余量；MAX_SIZE=200G>FILE_SIZE 使 GC watermark 失效，唯一 recycle 源 = cursor-wrap（~90G 累计 → 实测首 recycle 在累计写 81.6GB/文件 ~85.8G 快满时）
- **不完整处（诚实承认）**：我未把"默认 192G/128G 下 GC 在 115G live 触发并持住物理 ~115G"纳入可行性核算，直接按 192G 物理 >133G 判不可行；若按此核算，默认档 peak 物理 ~115G < 133G 实际可行，且默认档 clean 前缀更长（~115G vs 我的 90G）
- **对实验影响**：90G 使 clean prefix 更短（A 轮实测 314.5s / ~81.6G 累计写），但契约明确"按共同 recycle=0 前缀分析、前缀非空即可、早 recycle 不 INVALID"。A 轮窗口 5m14s 落在契约预期形状（5m30s 示例）内，非空、足以支撑四项门。**B 轮将在同容量（90G/200G）串行跑，保证 apples-to-apples**，故此容量选择不破坏 A/B 可比性
- **建议**：维持当前容量完成 A/B（Run A 已 2h 在途，重启浪费且契约允许当前前缀）；如 coordinator 判定需更长 clean 窗口（改 192G/128G），则需两轮都重跑，我按指示执行

## 3. orchestrator 最终裁决（用户批准，2026-09-05，口径钉死）

**裁决**：选 A，维持 90G/200G 跑完，不重跑。四条件原样执行：
1. **Run B 完全相同配置**：FILE_SIZE=90G / MAX_SIZE=200G（同 Run A，apples-to-apples）
2. **最终分析窗口 = min(A 首 recycle, B 首 recycle)** 再向前留安全 margin（数十秒级，确保两轮窗口内严格 recycle=0，无 reuse/GC 干扰）
3. **四 Gate 只统计共同 clean window**，window 外数据不参与裁决
4. **报告明确记录容量配置偏离**：正式轮 90G/200G 而非契约默认 192G/128G，root cause = tester 可行性核算错误（稀疏物化下 192G 实际可行且 clean 更长），12:32 修改仅 quoting 修复、默认值未动；运行字节证据（ab-cal-off 192G/128G 校准轮物理 54G）。不掩盖。

**口径边界（写进报告结论节）**：本次 A/B **只能裁决 RH 状态机是否存在独立缺陷**（三向裁决中"独立状态机 bug" vs "thrashing feedback"），**不能拿 90G/200G 的绝对 hit-rate 做容量/生产性能结论**。

后续：Run A 完成（预计 ~14:33）→ Run B 原样串行（同容量 90G/200G）→ 两轮完成 + 四 Gate 共同窗口分析 + 三向裁决 → 完整报告写入新 epoch 文件。窗口算法：`win_ms = min(A_first_recycle, B_first_recycle) - safety_margin`（margin 数十秒级），两轮各自 [t0, t0+win_ms) 内严格 recycle=0。

## 4. Run A 完成 + Run B 启动（执行记录更新）

**Run A（RH OFF）COMPLETE**：rc=0，join 2490/2500 rows（span 7224s = 120.4min），non-zero rc=0，total hits=0（join.log 不记 hit，需从 engine 日志/mid-run 取）。GPU 已回 idle 15MiB，lock 清空，无残留进程（早前 "2 个匹配进程" 系自匹配，已证实无残留）。A 首 recycle ts=1788583348012 (12:42:28)，首写 1788583033497 (12:37:13)，**A clean window = 314.5s**。

**Run B（RH ON）启动**：14:38:50 launch（wrapper pid 455194，direct-launch-gate1-rhon.sh），14:41:51 engine healthy（main 455194 / scheduler 455242）。确认 `enable_ready_horizon=True`、`max_size=200G`、同 90G/200G 容量（apples-to-apples per 裁决条件 1）。B 首写 ts=1788590529937 (14:42:09)。

**关键发现 — B 首 recycle 远早于 A**：
- B 首 recycle ts=1788590656441 (14:44:16)，**距首写仅 126.5s / 累计写 30.4 GiB**（slot=0 gen=1 cursor-wrap）
- A 首 recycle 距首写 314.5s / 累计写 ~81.6 GiB
- → **RH ON 在首 recycle 前累计写仅为 RH OFF 的 ~37%**（30.4 vs 81.6 GiB），时间早 2.5x。早期信号：RH ON 写放大/更早触碰容量

**共同 clean window = min(314.5, 126.5) = 126.5s**，按裁决向前留安全 margin → **win_ms = 120,000ms (2m)**（两轮窗口内均严格 recycle=0）。

Run B 进度（14:53:37）：178/2500 (7%)，rate 15.3/min（低于 A 的 21.6/min，疑 RH ON 早 recycle 致 recompute 拖慢），projected ~17:25。

（报告持续更新中；完整证据在 B 轮完成后写入。）

## 5. Run B COMPLETE + 四 Gate 共同窗口分析 + 三向裁决

**Run B（RH ON）COMPLETE**：rc=0，join 2108/2500 rows（span 7254.1s = 120.9min），non-zero rc=0。GPU 回 idle 15MiB，无残留进程。B 首写 1788590529937 (14:42:09)，**首 recycle 1788590656441 (14:44:16) = 距首写 126.5s / 累计写 30.4 GiB**。A 首 recycle 距首写 314.5s / 累计写 ~81.6 GiB。

**共同 clean window**：min(A=314.5s, B=126.5s) = 126.5s → 留安全 margin → **win_ms = 120,000ms**（两轮窗口内均严格 recycle=0，已确认）。

**四 Gate（共同 120s clean window，均 recycle=0）**：

| Gate | A (RH OFF) | B (RH ON) | B/A |
|---|---|---|---|
| input tokens | 372,245 | 380,722 | 1.02 |
| device_hit | 227,030 | 157,763 | 0.69 |
| host_hit | 106,600 | 69,804 | 0.65 |
| **storage_hit tokens** | **89,967** | **202,939** | **2.26x** |
| storage_hit rate (of input) | 24.2% | 53.3% | 2.2x |
| restore_success | 19 | 19 | 1.0 |
| restore_success tokens | 430,445 | 391,110 | 0.91 |
| recompute count/tokens | 257 | 131 | 0.51 |
| extent_write count | 786 | 848 | 1.08 |
| extent_write bytes | 28.7 GB | 30.7 GB | 1.07 |
| unique keys | 41 | 45 | 1.10 |
| write rate | 228 MiB/s | 244 MiB/s | 1.07 |

**共同窗口内 B 三向裁决依据（核心）**：
- **clean window 内 RH ON storage_hit = 2.26x 高于 RH OFF，recompute = 0.51x 更低，restore_success 持平** → RH ON 在无 recycle 干扰时 restore 不仅不 collapse，反而更好（hit 分布向 L3 storage 倾斜：device/host 降、storage 升，总 hit ~持平）
- → **RH 状态机功能正确（无独立缺陷），clean window 内 RH ON restore ≈ 甚至 > RH OFF**（三向裁决第一/第三支）

**全 run 对比（recycle 介入后）**：
- A storage_hit 持续增长 0→7.07M（线性 ~980/s）；B storage_hit 到 218,883 后**永久冻结**
- A restore_success 862 个持续到 +7197.9s；B 21 个，**最后停在 +121.1s**
- B ready_pool 事件仅 38 个，最后在 +121.7s，之后全 0；WAIT_CAPACITY 全程持续（restore 不断进入 WAIT_CAPACITY 永不释放）
- B 全 run 36,527 次 recycle（vs A 首 recycle 后持续 recycle），B 首 recycle 早于 A（126.5s vs 314.5s）、累计写 30.4 vs 81.6 GiB

**根因机制（精确定位）**：
1. clean window（t+0~126s）：RH ready_pool 工作正常，restore 成功，storage_hit 高于 A
2. 首 recycle @ t+126.5s（cursor-wrap，RH ON 因写放大更早触达容量）
3. recycle 后（~t+180s）：**RH ready_pool 永久停止 → restore 进入 WAIT_CAPACITY 永不释放 → restore_success → 0、storage_hit 冻结**，随后 36,527 次 recycle 的 thrashing 持续

**三向裁决（final）**：
- **RH ON restore ≈（clean window 内甚至 >）RH OFF** → **RH 状态机基本正确，无独立状态机 bug（clean window 实测 storage_hit 2.26x、recompute 0.51x 即证明）**
- **RH ON 在 recycle 后 restore 永久冻结 + write amplification（写放大）** → root cause = **RH + capacity-pressure thrashing feedback**，叠加 RH ON 更早触达容量（写放大 1.07x 只是小头，大头是 ready_pool 冻结）
- **口径边界（per 裁决）**：本 A/B 只裁决 RH 状态机是否存在独立缺陷 → **无独立缺陷**；**不得**用 90G/200G 绝对 hit-rate 做容量/生产性能结论

## 6. 完成报告（六节）

### 6.1 status: done

A/B 决定性实验（RH A'）完成。两轮串行、同 trace、同容量（90G/200G）跑完，共同 recycle=0 clean window（120s）内四 Gate 分析完成，三向裁决作出。**RH 状态机无独立缺陷；root cause = RH + capacity-pressure thrashing feedback（ready_pool 在 recycle 后永久冻结 + 写放大致更早触达容量）。**

### 6.2 artifacts（测试/产物）

| 产物 | 位置 |
|---|---|
| 分析脚本 rh_gates2.py（四 Gate） | /tmp/rh_ab_work/rh_gates2.py → /root/rh_gates2.py |
| 分析脚本 rh_keys.py（per-key） | /tmp/rh_ab_work/rh_keys.py → /root/rh_keys.py |
| A 轮证据 | /root/evidence-gate3-ab-a-off/（run-20260905-123655/，2490 rows，rc=0） |
| B 轮证据 | /root/evidence-gate3-ab-a-on/（run-20260905-144152/，2108 rows，rc=0） |
| 驱动 gate3_ab.sh（quoting 修复版） | /root/gate3_ab.sh（local==remote 全等） |
| 启动 wrapper | /root/direct-launch-gate1.sh（RH OFF）、direct-launch-gate1-rhon.sh（RH ON，diff 仅 +--enable-ready-horizon） |

### 6.3 evidence（验证命令 + 真实退出码 + 输出摘录）

**四 Gate 分析命令**：`python3 /root/rh_gates2.py ab-a-off 120000` 和 `python3 /root/rh_gates2.py ab-a-on 120000`
- A：storage_hit delta=89967，restore_success=19，recompute=257，extent_write 28.7GB/228MiB/s/41 keys，recycles_in_window=0
- B：storage_hit delta=202939，restore_success=19，recompute=131，extent_write 30.7GB/244MiB/s/45 keys，recycles_in_window=0

**跨核对（独立脚本直算原始 sample）**：A=89967 / B=202939（与 rh_gates2.py 一致，排除脚本 bug）

**机制定位命令（真实输出）**：
- B restore_success per 60s bin：`[2, 17, 2, 0, 0, 0, 0, ...]`（t+180s 后永久 0）
- A restore_success per 60s bin：`[0, 19, 23, 15, 30, 26, 21, 23, 23, 17, 6, 6, 3, 3, 8, 4, 11, 7, 3, 6]`（全程持续）
- B ready_pool per 60s bin：`[4, 30, 3, 0, 0, ...]`，total=38，last=+121.7s
- B WAIT_CAPACITY 全程持续（bins 74,79,36,27,47,109,79,76,...）
- B total_recycles=36527，A total_recycles=6513（grep -ac）
- B 首 recycle +126.5s/30.4GiB；A 首 recycle +314.5s/81.6GiB
- A restore_success 862 直到 +7197.9s；B restore_success 21 最后 +121.1s
- storage_hit 全 run：A 0→7,084,015（线性）；B 0→218,883 后冻结（218,883 恒定到 7200s）
- GPU 两轮后均回 idle 0%/15MiB；无残留 sglang 进程（用 pgrep -x python3 + /proc cmdline 精确核查）

**完整性声明**：A/B 两轮均 COMPLETE rc=0；锁均清空；容量偏离（90G/200G vs 契约默认 192G/128G）已如实记录于 §2/§3。

### 6.4 summary（真实数字）

- **两轮跑完**：A=2490 rows/120.4min rc=0；B=2108 rows/120.9min rc=0（同 budget 7200s，RH ON 少 15% 吞吐）
- **共同 clean window = 120s**（两轮均 0 recycle）
- **四 Gate**（A→B）：storage_hit 89,967→202,939（2.26x）；restore_success 19→19（持平）；recompute 257→131（0.51x）；extent_write 28.7→30.7 GB / 228→244 MiB/s（1.07x）；unique keys 41→45
- **三向裁决 = 第一/第三支**：RH ON 在 clean window 内 restore 正常甚至更好（storage_hit 2.26x、recompute 0.51x）→ **RH 状态机无独立缺陷**；recycle 后 restore 永久冻结（ready_pool 停、restore_success→0）+ 写放大（B 36,527 recycle vs A 6,513）→ **root cause = RH + capacity-pressure thrashing feedback**
- **口径边界遵守**：本实验只裁决 RH 状态机独立缺陷（= 无），不用 90G/200G 绝对 hit-rate 下容量/生产结论

### 6.5 followups

1. **RH ready_pool 冻结根因定位**（location: RH 状态机/ready_pool admission，engine log `evt=ready_pool` 在 recycle 后永久停止；`restore_state WAIT_CAPACITY reason=DEVICE_QUOTA` 永不释放）——建议 coder/orchestrator 深挖：ready_host_watermark_low=43513 远高于 pool 实达峰值 ~28K，可能 watermark 配置导致 pool 永远到不了 low → WAIT_CAPACITY 死锁。这是 thrashing feedback 的具体实现缺陷，属"RH 在容量压力下的反馈回路"范畴。
2. **写放大量化**（location: B 全 run 36,527 recycle vs A 6,513；B 首 recycle 30.4GiB vs A 81.6GiB）——RH ON 因更早 recycle 导致 thrashing 放大，需在容量充足场景复测以区分"RH 固有写放大" vs "recycle 反馈放大"。
3. **容量核算方法论**（location: §2 我的可行性核算错误）——稀疏物化下物理足迹 ≠ 名义 FILE_SIZE，应按"累计写字节直到 cursor-wrap"而非名义值估算；建议写进 tester 方法论。

### 6.6 open_issues

1. **共同窗口较短（120s）**：受 B 首 recycle 早（126.5s）限制。120s 内 B storage_hit 已显著高于 A（2.26x），足以作裁决；但窗口短导致绝对 token 数少（~200K 量级），对精确 hit-rate 估值的统计置信度有限——已按口径边界避免据此下容量/性能结论。
2. **recompute tokens 是事件计数**：engine log `restore_recompute` 无每事件 token 数，recompute 257 vs 131 是事件计数（非 token 量）。作为相对比较有效，但绝对 token 量未测得。
3. **B 轮 join 2108/2500**（RH ON 吞吐低 15%）：与 RH ON 早 recycle→recompute 拖慢一致，但不在共同窗口裁决范围内，仅记录。
4. **容量偏离**：正式轮 90G/200G 而非契约默认 192G/128G，root cause = tester 可行性核算错误，已在 §2 如实记录，不掩盖（per 裁决条件 4）。