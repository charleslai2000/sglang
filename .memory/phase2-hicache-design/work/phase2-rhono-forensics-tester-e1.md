# phase2-rhono-forensics-tester-e1 — P1 证据缺口闭合（30.4GiB vs 81.6GiB early recycle）

- status: **done**
- epoch: e1
- 任务: 独立取证（只读远程 3090 实验机 175.155.64.171:24052，禁止改任何代码/配置/引擎）
- 目标: 闭合 P1（RH 早回收 30.4GiB vs 81.6GiB）的证据缺口；回答 4 问
- 纪律: 全程只读；仅 `grep -n -F` 字面量 + Read 局部窗口；大日志用行号窗口读；无跨距正则（56-regex-safety）；未取到显式标「未取到」

## 0. 现场与产物

- 远程日志：`/root/engine-gate3-ab-a-off.log`（RH OFF, run A，100MB）、`/root/engine-gate3-ab-a-on.log`（RH ON, run B，91MB）
- 启动 wrapper（远程）：`/root/direct-launch-gate1.sh`（A）、`/root/direct-launch-gate1-rhon.sh`（B）
- 驱动（本机+远程）：`/tmp/rh_ab_work/gate3_ab.sh`（本地与 `/root/gate3_ab.sh` 一致）
- 证据目录：`/root/evidence-gate3-ab-a-off/`、`/root/evidence-gate3-ab-a-on/`（boot-metrics / metrics-final / engine-alloc / engine-events-*）
- 代码（本机只读）：`extent_file_backend.py` / `extent_allocator.py` / `hicache_restore.py` / `server_args.py` / `scheduler.py` / `hicache_storage.py` / `hybrid_cache_controller.py`
- 取证方式：SSH 只读命令 + 从引擎日志/evidence 提取，交叉核验；未修改远程任何文件、未启动/停止引擎、未写远程。

---

## 1. 硬证据一：A/B 实际启动参数（从日志启动头 / wrapper / server_args 提取）

来源：远程 `/root/gate3-ab-a-off-status.log`、`/root/gate3-ab-a-on-status.log`、`/root/direct-launch-gate1*.sh`、引擎日志 `server_args` 行（engine-gate3-ab-a-on.log:8）、`ExtentFileBackend:` 行（engine-gate3-ab-a-on.log:658）。

| 参数 | Run A (RH OFF) | Run B (RH ON) | 来源 |
|---|---|---|---|
| tag / wrapper | ab-a-off / direct-launch-gate1.sh | ab-a-on / direct-launch-gate1-rhon.sh | status.log |
| `--enable-ready-horizon` | **False**（未传） | **True**（A/B 唯一 diff，diff 仅 +1 行） | wrapper diff |
| FILE_SIZE（`SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE`） | `90G`（status 记录）→ 实测 **90GB decimal = 83.82 GiB** | 同 90G → 同 83.82 GiB | status.log + ExtentFileBackend 行 |
| extent_size | 67108864 B (64 MiB) | 同 | ExtentFileBackend 行 |
| **slots** | **1341** | **1341** | ExtentFileBackend 行（两行均实测） |
| MAX_SIZE | 200G | 200G | status.log + server_args `hicache_storage_backend_extra_config={"max_size":"200G"}` |
| min_free_space | 10G | 10G | ExtentFileBackend 行 `min_free=10000000000` |
| `hicache_restore_wait_timeout_s` | **60.0**（默认，未覆盖） | **60.0**（默认，未覆盖） | server_args 行 |
| `ready_horizon_state_p95_tokens` | — | **0**（默认） | server_args 行 |
| `ready_host_watermark_low/high` | — | **43513 / 87026**（默认） | server_args 行 |
| `hicache_prefetch_speculative_fraction` | — | 0.6（默认） | server_args 行 |
| `max_mamba_cache_size` | — | 106（`--max-mamba-cache-size 32` 未传 → server_args None → 实测日志 Mamba Cache allocated max=106） | engine-alloc.txt |
| tp/kv/mamba 配置 | 同（tp1, bf16, extra_buffer, write_back, wait_complete） | 同 | wrapper |
| 启动/首写/首回收 | 12:34:33 / 12:37:13 / 12:42:28（+314.5s） | 14:38:50 / 14:42:09 / 14:44:16（+126.5s） | status.log + 日志 ts |

**关键参数确认**：
- **文件实为 90GB decimal（= 83.82 GiB，非 90GiB）**，`1341 slots × 64MiB = 90,000,000,000 B`。`slots=1341` 来自启动行（engine-gate3-ab-a-on.log:658 / -a-off.log:658），**这是用户指定要取的关键证据，已取到**。
- **A/B 的启动参数除 `--enable-ready-horizon` 外完全相同**（wrapper diff 仅 1 行）。timeout=60s、state_p95=0、watermark 43513/87026 均为默认值，**A/B 两 run 未覆盖**。
- 首回收时间/字节（复核自日志 ts）：A +314.5s / 76.05 GiB（logged 累计，先前报告 81.6GiB 含未对账差异，见§3）；B +126.5s / 30.45 GiB。

---

## 2. 硬证据二：首 recycle 前后 ≥120s 时间线（事件并排）

来源：B log 行 13220-13300（首回收前 ~50 行原始日志）；`extent_write`/`extent_recycle`/`restore_*`/`ready_pool` 事件 grep。

### 2.1 B（RH ON）首回收前时间线（-126s → 0s）

| offset(s) | 事件 | 备注 |
|---|---|---|
| 0 | 首 extent_write（14:42:09）| B 首写 ts=1788590529937 |
| ~+2.3 | `restore_state WAIT_CAPACITY reason=DEVICE_QUOTA` 首次出现（ts=1788590523222）| DEVICE_QUOTA 在首写前已开始 |
| 0→~85 | kv/mamba 交替 extent_write（每 ~30-40ms 一批：kv 1024 keys/32MiB、mamba 1 key/49.12MiB）| 写率 244 MiB/s |
| ~+60 | `restore_recompute cause=timeout` 首现（ts=1788591779700 是首个 timeout，但 cause=miss 在 0s 前已大量出现）| 见§5 |
| +85→121 | 持续 extent_write + restore_backup + admission + `restore_state WAIT_CAPACITY reason=DEVICE_QUOTA/FRONTIER/PREFETCH_BUDGET` 交替 | 容量门持续卡 |
| **+121.1** | **最后一次 restore_success**（B 全 run 21 次，最后在 +121.1s）| restore_success 此后永久冻结 |
| **+121.7** | **最后一次 ready_pool 事件**（38 个，最后 +121.7s）| ready_pool 此后永久冻结 |
| +126.5 | **首 extent_recycle**（14:44:16, ts=1788590656441）| 距首写 126.5s / 30.45GiB |
| +126.5~126.7 | 首回收 burst：377 个 recycle，slot 0..541，gen 1..13，**非升序**，含 slot=0 | 见§2.2 |
| +126.5 后 | thrash 持续：B 全 run 36,527 次 recycle，gen 分布 1..36163 | 见§2.3 |

首回收前 50 行（13220-13272）显示：前一刻仍是正常 kv/mamba extent_write + restore_backup + admission，无 ENOSPC / 磁盘错误 / evict 日志行。首回收事件本身是 `_gc_evict` 或 cursor-advance 触发，日志不区分（`extent_recycle` 事件格式相同），但 gen/slot 形态判别（§2.2-2.3）。

### 2.2 A vs B 首回收 burst 形态（决定性判别）

来源：`extent_recycle` 事件 grep + 本地 replay 脚本。

| 判别维度 | A (RH OFF) | B (RH ON) |
|---|---|---|
| 首回收 offset | +314.5s | +126.5s |
| 首回收 burst 事件数（前 5s）| **25** | **377** |
| 首回收 burst gen 分布 | **全 gen=1** | **gen 1..13（{1:365,2:1,...,13:1}）** |
| 首回收 burst slot 范围 | **1..63 严格升序** | **0..541 非升序，含 slot 0** |
| 首回收 burst freed 总量 | ~1.3 GiB | ~19.9 GiB |
| 全 run recycle 总数 | 6,513 | 36,527 |
| 全 run distinct gen 数 | **20**（gen 1..20，均匀 378-466/档）| **36,163**（gen 1..36163，几乎每档恰 1 次）|
| 全 run slot 范围 | 0..1340（完整循环）| 0..541（未满一轮）|

**A 首回收形态 = 干净的 cursor-advance**：25 个 slot、全 gen=1、严格升序（1,3,5,...63）——这是 pack cursor 顺序前进时逐 slot 跳过并 drop 首次经历；A 全 run 20 个 distinct gen 均匀分布在 slot 0..1340，是 cursor 在 1341 slots 上循环 ~5 轮的**健康 cursor-wrap** 形态。

**B 首回收形态 = thrash / GC 驱动**：首 burst 377 slots、gen 1..13（同一批内 slot 被反复 drop，gen 快速爬升）、含 slot 0、非升序。B 全 run **36,163 个 distinct gen（几乎每档恰 1 次，max_gen=36163）** 说明同一批 slot 被反复 evict-rewrite 数千次（1341 slots 被平均回收 ~27 次/个）——**这是持续 thrash**，与 A 的健康 cursor 循环截然不同。

> 判别依据（代码）：`_gc_evict`（extent_file_backend.py:863-885）在 `statvfs f_bavail < min_free(10G)` 或 `used_bytes > max_size*0.9` 时循环 `evict_slot_lru()`（extent_allocator.py:174-184），每次 `_drop_slot`（:197-218）bump gen 并 emit `evt=extent_recycle`。**cursor-advance 的 `plan()` 里 `passed` drop（extent_allocator.py:110-151）gen 从 0→1 单次**，而 GC 循环可让同一 slot 多次 drop（gen 快速爬升）。A 首 burst 全 gen=1 = cursor-advance 单次 drop；B 首 burst gen 1..13 = 同批内 GC/复用多次 drop（thrash）。

### 2.3 B 全 run thrash 数字

- B 全 run `extent_recycle` 36,527 次（A 6,513 次，5.6x）；distinct gen 36,163（A 20）。
- B 首回收后，`evt=extent_recycle` 持续高频，无 ENOSPC 报错（磁盘满但 pwrite 到已预分配稀疏文件不报 ENOSPC——文件 `ftruncate` 预分配 90GB，逻辑块位图不因 pwrite 超出分配，除非物理用尽）。
- B `restore_state WAIT_CAPACITY reason=DEVICE_QUOTA` 全 run **6,356 次**（+ FRONTIER 845 + PREFETCH_BUDGET 139，共 7,433 次 WAIT_CAPACITY）；`restore_success` 21 次后冻结（+121.1s）；`ready_pool` 38 个事件后冻结（+121.7s）；`restore_recompute` 9,122 次（cause=miss 9,102 + timeout 20）。

---

## 3. 硬证据三：30.4GiB 是 telemetry logical write 还是 backend 实际写量

**判定：30.4GiB 是「engine 侧 telemetry logical write 累计（evt=extent_write bytes 求和）」，且在本引擎数据路径下≈backend 实际 pwrite 字节**（证据：logged 累计与物理文件块数在同一量级；无单 key set() 绕过日志的路径被使用）。

### 3.1 数字对账

| 项 | B (RH ON) | A (RH OFF) |
|---|---|---|
| 首回收前 logged extent_write 累计 | **30,694,796,288 B = 30.45 GiB**（905 行）| 76.05 GiB（A 首回收 logged 累计；先前报告 81.6GiB 差异见下）|
| 首回收前 mamba/kv 分量 | mamba 10.41 GiB (217行) / kv 20.04 GiB (688行) | — |
| 全 run logged extent_write 累计 | 1,278.22 GiB (37,068 行) | 1,344.63 GiB (39,415 行) |
| 数据文件物理块（跑完）| **31 G**（blocks=63,922,576×512）| **84 G**（blocks=175,767,656×512）|
| 文件 apparent 大小 | 90,000,000,000 B = 83.82 GiB（稀疏）| 同 |

- B 首回收 logged 累计 30.45 GiB 与**先前报告「30.4GiB」完全吻合**（rh-ab-e2 的 30.4 即此 telemetry 求和）。
- A 首回收：rh-ab-e2 报 81.6GiB，本取证按 logged 求和得 76.05 GiB。差异来源：rh-ab-e2 的 81.6GiB 很可能来自 metrics/snapshot 的累计写计数或含未日志成分，**本取证以日志 `evt=extent_write` 求和为准（76.05 GiB）**；两值均为「首回收前累计写」口径，差异不影响 A/B 相对结论（B 远小于 A）。
- B 物理文件 31G ≈ B 首回收后持续 thrash（重写已回收 slot，稀疏文件不增长到 84G）。A 物理文件 84G = A 从未 thrash，最终填充近满。

### 3.2 telemetry 与物理写的关系（代码语义）

- `evt=extent_write` 由 `_log_extent_write`（extent_file_backend.py:356-374）在每次成功 extent batch 后 emit，`bytes` = 该 batch 各 key 字节和（`sum(len(v) for v in sizes)`）。
- 三个写入口均调 `_log_extent_write`：
  - `batch_set_v1`（kv 零拷贝, :537-541）→ `component="kv"`（logged）
  - `batch_set`（v1, :388-390）→ `component="kv"`（logged）
  - `batch_set_v2`（mamba/kv pool, :716-751, :745）→ `component=transfer.name`（logged，mamba 走此路）
- 因此**本引擎数据路径下每次 backend 物理 pwrite 都会有一条 evt=extent_write 记录**，`bytes` = 实际写字节。

### 3.3 物理写是否可能大于 logged（写放大 / 未日志写）

- **写放大（extent 粒度）**：`_write_pages` 按 ref 精确 pwrite（`_pwritev(extent_id*extent_size+offset, bufs)`），非整 extent 覆盖写放大不产生额外字节（同文件已预分配，pwrite 仅写 data 区域）。因此 logged bytes ≈ 实际写字节（无重复写放大字节计数差异）。
- **未日志写（单 key set()）**：见§4——**本引擎路径不调用 extent 单 key `set()`**，所有写都经 batch_set_v1/v2（logged）。故**无未计量写**。
- **结论**：30.45GiB（B 首回收）是 telemetry logical write 累计，且 = backend 实际 pwrite 字节累计（本路径下）。**不是「logical 远小于 physical」的情况**。

---

## 4. 硬证据四：Mamba `set()` 是否绕过 `_log_extent_write`

**判定：本引擎数据路径下 mamba 写**不经单 key `set()`**，全部经 `batch_set_v2`（logged），因此**无绕过计量**。**

### 4.1 代码证据

- extent 单 key `set()`（extent_file_backend.py:313-322）：`return self._write_pages([...])`，**不调 `_log_extent_write`**——代码级确认（任务指定行 :313-322，已读）。
- `batch_set_v2`（:716-751）：`ok = self._write_pages(...)`; `if ok: self._log_extent_write(transfer.name, ..., storage_keys, values)`——**mamba 走此路并计量**（:745）。
- 调用链：hybrid_cache_controller `_page_backup`（:734-736）→ `storage_backend.batch_set_v2(backup_transfers)`。mamba pool（`PoolName.MAMBA`）的 transfer 走 batch_set_v2（hybrid_pool_assembler.py:747/859 构造 `name=PoolName.MAMBA` 的 transfer）。
- extent 单 key `set()` 在数据路径的调用者：grep 全代码，`storage_backend.set(` 仅出现在 `hicache_storage.py:564/677`（**file backend** wrapper 的 `set`/`_write_page`），extent backend 不通过 `hicache_storage.py` 被调用（`L3_BACKEND=extent` 直接构造 ExtentFileBackend，backend_factory.py:203）。**故 extent 单 key `set()` 在本实验未被调用**。

### 4.2 日志证据（mamba 写全被计量）

- B log：`component=mamba keys_n=1 bytes=51511296` 共 **12,453 条**，字节分布**唯一**（全部 51,511,296 = 49.12 MiB/条）——mamba 写全部经 batch_set_v2 以 keys_n=1 记录，**无未计量 mamba 写**。
- 首回收前 mamba 分量 10.41 GiB（217 条）已计入 30.45GiB。

### 4.3 若真有单 key set() 绕过，漏计比例估算（假想值，非本实验实测）

- 若某路径用单 key set() 写 mamba（每 key 49.12 MiB）而不计量，漏计量 = 该路径写字节。本实验日志 mamba 占首回收前写量 34%（10.41/30.45 GiB），kv 占 66%。
- **本实验无该路径被用**，故漏计比例 = 0（实测）。若未来引擎改用单 key set() 写 mamba，则漏计可高达「mamba 写量占比」（~34% 量级），需补 `_log_extent_write`（见§6 Q4）。

---

## 5. 硬证据五：DEVICE_QUOTA 60s timeout 是否实际生效

**判定：T13（`hicache_restore_wait_timeout_s=60.0`）确认生效，且已被触达（20 次 `restore_recompute cause=timeout`）；但恢复失败根因是「timeout→recompute→立即 re-WAIT/re-miss」，不是 timeout 未触发。**

### 5.1 timeout 生效证据

- server_args：`hicache_restore_wait_timeout_s: 60.0`（默认，A/B 均未覆盖）——引擎实际装载值。
- 事件：B 全 run `restore_recompute cause=timeout` **20 次**（ts 列表见下），间隔实测多为 **60s±**（如 63.8s、56.7s、53.2s、60.0s），确认 T13 时钟生效。
- 单例核查（rid f45103af42a543a7891c4816d446f81a）：15:25:50 `restore_state state=WAIT_CAPACITY reason=FRONTIER` → 15:26:50（**恰 60s 后**）`restore_recompute cause=timeout`。**T13 精确 60s 触发**。

### 5.2 为何 timeout 后仍无法恢复（WAIT→recompute→再 WAIT 循环）

- B 全 run `restore_recompute` 9,122 次：**cause=miss 9,102** + timeout 20。绝大多数 recompute 是 **cause=miss**（非 timeout）。
- 循环证据（rid 3c6072...）：
  - 15:01:56 `restore_disposition disposition=RECOMPUTE reason=revoked:miss`
  - 15:01:56 `restore_recompute cause=miss`
  - 15:01:59 `restore_state WAIT_CAPACITY reason=DEVICE_QUOTA`
  - 15:02:04 `restore_state RESTORING`
  - （随后又 revoke:miss）
- **机制解释**：T13 timeout 触发后进入 recompute 路径，但 recompute 需从 L3 storage 读回（restore）；由于 extent 持续 thrash（slot 被回收、generation bump），读回的 key 在 `_read_pages` 的 generation re-verify 处失败 → `revoked:miss` → 立即重新 `WAIT_CAPACITY reason=DEVICE_QUOTA`（host 容量仍满、headroom 冻结）→ 循环。**不是 T13 没触发，而是触发后每次 recompute 因容量仍满 + extent 抖动而再次被打回 WAIT**（WAIT→recompute→revoke:miss→WAIT 无限环路）。
- host headroom 冻结（代码+metrics）：B `hicache_host_used_tokens=97,370` / `total=98,305`（metrics-final），working ≈ 全满 → `_ready_host_headroom = available + ready_resident ≈ 近 0` → `headroom_fits`（ready_horizon.py:371-379）对一切 speculative stage 恒失败 → ready_pool 冻结于 0（§2.1，+121.7s 后无事件）。这是 timeout 后无法恢复的容量侧根因。
- **ready_pool 冻结（+121.7s）先于首 recycle（+126.5s）**：即容量压力→ready_pool 冻结在前，extent 早回收是其后继 thrash 的下游症状，不是冻结的原因。

---

## 6. 最终回答 4 问

### Q1：30.4GiB early recycle 的真实根因（(a)/(b)/(c) 判定）

**判定：(c) 写形状 / extent slot churn（thrash）——RH 的预取+恢复失败→重写抖动使 extent slot 被反复 drop-reuse，首回收提前到 30.4GiB；(a) 与 (b) 均被证伪。**

- **(a) file<90G：证伪**。实测文件 = 90GB decimal = 83.82 GiB，`slots=1341`（启动行，两 run 均取到）。文件 NOT 小于 90G。且 cursor 全环绕（满 83.82GiB 才 wrap）本就不能解释 30.4GiB 首回收——recycle 不是 cursor-全环绕触发。
- **(b) set() 未计量：证伪**。本引擎数据路径 mamba/kv 全经 batch_set_v1/v2（logged），单 key set() 未被调用；30.45GiB = 实际 pwrite 字节（logged 求和 = 物理写）。无漏计。
- **(c) 大件/写形状加速 slot churn：成立（机制）**。B 首回收 burst = 377 slots、gen 1..13、非升序、含 slot 0 = **thrash 形态**（GC/复用反复 drop），A 首回收 burst = 25 slots、全 gen=1、严格升序 = **健康 cursor-advance 形态**。B 全 run 36,163 distinct gen（每档恰 1 次）vs A 20 个 distinct gen = **B 持续 thrash，A 健康 cursor 循环**。RH 预取写 + restore 失败（DEVICE_QUOTA 冻结）→ 同一 key 反复 prefetch/rewrite → extent slot 反复 drop-reuse → 首回收提前。
- **补充因果链（时间序，来自日志）**：容量压力 → ready_pool 冻结(+121.7s)/restore_success 停(+121.1s) → 首 recycle(+126.5s, thrash 形态) → 后续 36K thrash。**早回收是容量冻结的下游症状，非冻结原因**（与 architect 矛盾 1 的 host headroom 冻结根因一致，矛盾 2 的「file 非 90G / set() 未计量」两分支被证伪，收敛到「写形状+thrash」）。
- **对 disk-GC（min_free=10G）的核查**：B 首回收时重建磁盘物理空闲 ≈18G（>10G），未触达 min_free 阈值，故**首回收主因非磁盘 GC**；但 `/data` 现已 100% 满（1.9G 空闲）、A/B 及后续 run 文件堆叠是环境污染，extent 无 hole-punch（evict 不释放物理块），磁盘压力是长期环境风险而非本次早回收的直接主因（重建有不确定性，见 limitations）。

### Q2：DEVICE_QUOTA timeout 是否生效 + 为何无法恢复

**生效**：T13=60.0s 确认装载且被触达（20 次 `cause=timeout`，单例实测恰 60s）。**无法恢复原因**：不是 timeout 未触发，而是每次 timeout→recompute→立即 `revoked:miss`（extent thrash 使 key generation 失效）或 `WAIT_CAPACITY reason=DEVICE_QUOTA`（host 容量仍满、headroom 冻结）→ 无限 WAIT→recompute→WAIT 环路。B 全 run 9,122 recompute 中 9,102 为 cause=miss（非 timeout），即真正阻断是「recompute 后 miss 再被打回」，不是「timeout 被跳过」。

### Q3：Fix A/B 是否仍是最小正确修复面

**是**。根因收敛支持 architect 的 Fix A（host headroom 门事件化自愈）与 Fix B（DEVICE_QUOTA 出口加固，timeout 后强制降格放行而非继续循环）作为 P1 最小修复面：
- 冻结主因 = host headroom 门无自愈输入（ready_pool 冻结）+ WAIT→recompute→WAIT 环路（DEVICE_QUOTA 出口未降格）。Fix A/B 正对这两点。
- Fix C 的「取 `slots=` 行」子步已完成（= 1341，file=83.82GiB，**(a) 证伪**)；Fix C 的「set() 补计量」**本路径不需要**（(b) 证伪，无漏计）。Fix D（水位定标）仍可作为可选项（state_p95=0→固定 43513 语义失真），但非本 bug 主因。
- **Fix C 剩余取证项（首回收前后 120s 事件并排）已完成**：早回收 = thrash 形态，非 (a)/(b)。**Fix C 作为根因修复可关闭，仅需在报告中降权「extent 早回收」作为独立缺陷**。

### Q4：是否需要 telemetry 修正（set() 补 `_log_extent_write`）

**本实验数据路径下不需要（无漏计，30.45GiB 已完整）**。但**代码级存在一个真实的不一致**：`extent_file_backend.py:313-322` 单 key `set()` 不调 `_log_extent_write`，而 `batch_set`/`batch_set_v1`/`batch_set_v2` 都调。**一旦未来有路径经单 key set() 写（如 mamba 单 key 写），将产生未计量写（漏计量可达 mamba 写占比 ~34% 量级）**。建议作为低风险 hygiene 修复（一处调用）纳入，但不阻塞 P1，也不改变本 A/B 结论。

---

## 7. OBSERVED / INFERRED / NOT_ESTABLISHED 分类

**OBSERVED（日志/文件实测）**：
- `ExtentFileBackend: ... extent=67108864 slots=1341 max_size=200000000000 min_free=10000000000`（两 run 启动行）
- A/B 首回收：A +314.5s / logged 76.05GiB；B +126.5s / logged 30.45GiB
- A 首回收 burst 25 slots 全 gen=1 升序；B 首回收 burst 377 slots gen 1..13 非升序含 slot0
- A 全 run 6,513 recycle / 20 distinct gen；B 全 run 36,527 recycle / 36,163 distinct gen
- B ready_pool 最后事件 +121.7s；restore_success 最后 +121.1s（21 次）
- B `restore_recompute` 9,122 次（miss 9,102 / timeout 20）；WAIT_CAPACITY DEVICE_QUOTA 6,356 次
- T13=60.0s 装载；单例 WAIT→60s→timeout recompute 精确 60s
- server_args：enable_ready_horizon=True（B）、state_p95=0、watermark 43513/87026、timeout 60.0
- 数据文件物理：B 31G（apparent 83.82GiB 稀疏），A 84G
- 磁盘：/data 现 100% 满（1.9G 空闲）；B 首回收重建空闲 ~18G（估算）

**INFERRED（代码+日志推断）**：
- 30.45GiB = telemetry logical write = backend 实际 pwrite（本路径全部 logged，无漏计）
- B 首回收 burst = thrash/GC 形态（gen 1..13），A = cursor-advance 形态（全 gen1）
- 早回收是容量冻结下游症状；恢复失败 = recompute→miss→再 WAIT 环路
- disk-GC 非首回收主因（重建空闲>10G），但磁盘满为长期环境风险

**NOT_ESTABLISHED（未取到/不确定）**：
- B 首回收时刻磁盘精确空闲量（重建法有不确定性：dir mtime 采样 + 当前物理 size 反推，误差 ±5-10G）——故 disk-GC 触发与否非 100% 定论，但首 burst 的 thrash 形态（gen 1..13、含 slot0）不依赖磁盘数值，是独立确证。
- A 首回收 logged 累计 76.05GiB 与 rh-ab-e2 报 81.6GiB 的差异来源（rh-ab-e2 未在本报告对账，两值均「首回收前累计写」口径，不影响相对结论）
- restore_success/ready_pool 冻结与 extent thrash 的精确先后毫秒级边界（冻结 +121.xs 先于 recycle +126.5s，已确认先后，未到毫秒）

---

## 8. limitations / followups

**limitations**：
- 磁盘空闲为重建估算，非直接采集（引擎无 statvfs 指标）。首回收主因判定主要依赖 gen/slot 形态（确证），磁盘 GC 角色为次要不确定项。
- A 首回收 logged 累计与本会话对账口径（76.05GiB）与先前报告（81.6GiB）有差，未深挖 81.6 来源；不影响 A/B 相对结论。
- 未对 B 首回收 burst 的每个 slot 做逐 key 归属（rh_keys.py 需 engine 日志 rid 级数据，本会话未逐 rid 重建写回）。

**followups（建议，非本会话执行）**：
- [建议] 若需 100% 确认 disk-GC 角色：在干净磁盘（预留 ≥40G 空闲）重跑 B（RH ON, 90G/200G），观察首回收是否仍 30.4GiB 及 burst 形态。
- [建议] 在 `/data` 清理至 >30G 空闲后再跑后续实验（当前 100% 满，任何 extent 写都有磁盘压力风险）。
- [建议] 低风险 hygiene：`extent_file_backend.set()` 补 `_log_extent_write`（一处），防未来单 key 写路径漏计。

## 9. verdict 汇总

- claim1（root cause = (c) 写形状/extent thrash；(a)(b) 证伪）：**confirmed**（gen/slot 形态 + 文件 1341 slots + 全 logged 无漏计）
- claim2（DEVICE_QUOTA timeout 生效但无法恢复 = 环路）：**confirmed**（20 次 timeout 实测 60s + miss 9,102 的 recompute 循环）
- claim3（Fix A/B 仍为最小修复面）：**confirmed**（冻结主因 + 环路正对 Fix A/B；Fix C 子步已完成并证伪 (a)(b)）
- claim4（telemetry 修正非本路径必需，但 set() 不一致真实存在）：**confirmed**（本路径无漏计；代码级不一致为真实待 hygiene 项）
