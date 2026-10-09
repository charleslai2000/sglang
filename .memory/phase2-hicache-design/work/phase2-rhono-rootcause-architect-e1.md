# phase2-rhono-rootcause-architect-e1 — RH remaining bug 根因收敛

- epoch: e1（本任务首份报告）
- 时间: 2026-09-05
- 任务: P1 主线 — 收敛 Ready Horizon（RH）剩余 bug 的代码级根因（三个硬矛盾）
- 类型: root-cause 收敛（只读分析；**禁止改代码**，本会话无任何代码/schema/依赖修改）
- 依据: Phase-2 已 CLOSED 机制不再重开；六个事后 fix 门（clean window RH 优势 / DEVICE_QUOTA 恢复 / restore_success+storage_hit 不冻结 / 首次回收不显著提前 / 正确性无回归 / 2h soak）

## status

**done**（根因收敛完成；证据缺口以「未定位/证据不足」档显式列出，不猜测补全）

---

## artifacts

本报告正文（现状结论见 summary 节）。支撑工件：

- 分析对象代码（只读，路径见 evidence 节）：
  - `python/sglang/srt/managers/scheduler_components/ready_horizon.py`
  - `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - `python/sglang/srt/managers/scheduler.py`
  - `python/sglang/srt/managers/cache_controller.py`
  - `python/sglang/srt/managers/schedule_policy.py`
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
  - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
  - `python/sglang/srt/server_args.py` / `python/sglang/srt/environ.py`
- 证据报告（tester/scout/orchestrator 已产出，本报告引用）：
  - `.memory/phase2-hicache-design/work/phase2-rhono-bug-architect-e1.md`（前一轮翻车/矛盾梳理）
  - `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-rh-ab-e1.md`、`-rh-ab-e2.md`（A/B 实验冻结结论）
  - `.memory/phase2-hicache-design/work/phase2-hicache-design-scout-remaining-issues-e1.md`
  - `.memory/phase2-hicache-design/work/phase2-hicache-design-orchestrator-gate3-closeout-e1.md`
  - `/tmp/rh_ab_work/gate3_ab.sh`（A/B 驱动）与 `/tmp/rh_ab_work/rh_gates2.py`（四门分析脚本）
  - `gate3-rhon-evidence/metrics-final.txt`（后者跨上下文摘要引用：kv_pool_tokens=98305 / working=96312 / usable=98305 / mamba_host_usable=160，快照自 remote 运行，需以主机侧原始 logs 复核）

---

## evidence（证据与代码定位）

### 0. 方法纪律

- 依据 56-regex-safety：全程仅用 `grep -n -F` / `grep -n -E`（有界/字面量）定位行号 + Read 局部窗口；无跨距正则。
- 本报告「代码证据」（✓ verified）为已实际读过的源文件行；「报告推断」（推断）为基于代码与证据报告的推论，不与代码等权。远程 3090（root@175.155.64.171:24052）上的运行日志与 `ExtentFileBackend:` 启动行是唯一现场证据来源，未取得处的空档一律标「未定位」。

---

### 1. 关键代码支点（均为本会话已读行）

**RH 池与水位**
- `ready_horizon.py:201-207` `_below_low`：token 模式 `ready_tokens < watermark_low`（未发现 tokens/bytes 混用）。
- `ready_horizon.py:209-217` `_issue_budget`：`max(0, watermark_high - ready_tokens)`。
- `ready_horizon.py:345-369` `staging_candidates`：`cc.prefetch_rate_limited() or cc.prefetch_speculative_rate_limited()` → 直接返回 `[]`。→ **冻结候选点**：speculative budget 卡死则池永不补。
- `ready_horizon.py:371-379` `headroom_fits`：`ready_tokens + inflight_tokens <= host_headroom`。
- `ready_horizon.py:381-446` `refill_plan`：`_below_low` → candidates → `headroom_fits` → issue 到 budget，否则 NO_HEADROOM decline。

**调度器侧 RH pass**
- `scheduler.py:3184-3248` `_feed_restore_terminal`：REVOKED_MISS + RH → `NegativeCacheEntry(NO_L3, epoch_cursor=tree_cache.l3_publish_epoch(), ...)`（:3211-3222）。
- `scheduler.py:3274-3318` `_apply_restore_event`：WAIT_CAPACITY → `req.hicache_restore_wait_reason`。
- `scheduler.py:3320-3425` `_ready_horizon_pass`：negatives 仅按 frontier rids 裁剪（:3359-3363）；`headroom = _ready_host_headroom(cc, views)`；NO_HEADROOM park（:3377-3380）；SPEC_BUDGET tail park（:3404-3415）。
- `scheduler.py:3452-3481` `_ready_horizon_views`：`staged = peek_prefetch_loaded_tokens`；`full_prefix = staged > 0`（M6 严格定义的另一半）。
- `scheduler.py:3501-3514` `_ready_host_headroom`：`pool.available_size() + ready_horizon.ready_resident_tokens(views)`。
- `scheduler.py:3516-3543` `_ready_reserve_floor_tokens`：token 模式 = `reserve_tokens + margin_tokens`（state_p95=0 时为 0）。
- `scheduler.py:3632-3696` `_restore_wait_capacity_fits`：FRONTIER/BACKUP_PENDING 谓词；`promotion_wait_blocked`（:3670-3683，DEVICE_QUOTA + host_hit_length>0 + budget 不满足）；最后 `charge = device_charge(...)` < `available_and_evictable_tokens(...)`。
- `scheduler.py:4394-4446` admission：`prefetch_done = check_prefetch_progress`；WAIT skip；`loaded_tokens = pop_prefetch_loaded_tokens`；:4421-4426 记 `evt=restore_success`。
- `scheduler.py:4455-4465` `AddReqResult.NO_TOKEN` + `_restore_potential_for(req)` → `_apply_restore_event(req, RestoreEvent.ADMISSION_DENY)` → **WAIT[DEVICE_QUOTA]**。

**restore 状态机**
- `hicache_restore.py`：`next_restore`（首 WAIT 即武装 clock，非每 WAIT 重武装）— 一次恢复尝试窗口内仅一只；`promotion_budget_fits`（:240-264）`locked+reserved+new_restore <= capacity - margin`；`promotion_wait_blocked`（:267-287）；`capacity_wake_applies`（:342-362）DEVICE_QUOTA/PREFETCH_BUDGET/FRONTIER/BACKUP_PENDING 可测；REVALIDATE/HOST_ALLOC 只能 paced retry 或 T13。

**extent 分配器与 GC**
- `extent_allocator.py:110-151` `plan`：cursor 环绕；`if cursor+length > extent_size: slot=(slot+1)%num_slots; ... passed.append(slot); cursor=0`；generation = `self._generations[slot] + passed.count(slot)`（同一 slot 一圈内两次路过也 +2）。
- `extent_allocator.py:197-218` `_drop_slot`：`self._generations[slot] += 1` 并记 `evt=extent_recycle`。
- `extent_file_backend.py:155-276` `__init__`：`_DEFAULT_FILE_SIZE = 64<<30`；`file_size = _parse_size_to_bytes(...) or _DEFAULT_FILE_SIZE`；`_max_size_bytes`；`_min_free_bytes`（environ.py:704 默认 "0"）；`self._allocator = ExtentAllocator(extent_size, self._file_size // extent_size)`（:271）。
- `extent_file_backend.py:826-859` `_write_pages`：先 `_gc_evict()` 再 plan/pwrite/commit（锁内）。
- `extent_file_backend.py:863-885` `_gc_evict`：`pressure = used_bytes > max_size*0.9 or disk < min_free`。
- `extent_file_backend.py:313-322` `set()`：单 key → `_write_pages`，**不调 `_log_extent_write`** → 未被计量写入（extent_write 潜在低估）。
- `extent_file_backend.py:487-540` `batch_set_v1`（kv，零拷贝，计 component="kv"）；`:716-751` `batch_set_v2`（mamba，也计量）。

**prefetch 分类与预算（M5）**
- `unified_radix_cache.py:2340-2355` `reserve_prefetch(req_id, tokens, kind)`：`_prefetch_reservations`，kind==SPECULATIVE → `cc.inflight_speculative_tokens += tokens`；**double reserve assert**（:2348-2351）。
- `unified_radix_cache.py:2357-2377` `release_prefetch(req_id, reason)`：全 ongoing_prefetch 移除点必经（finalize/revoke/abort/hybrid discard/detach），幂等。
- `unified_radix_cache.py:2650-2683` 分类：T15 wake 重发 = DEMAND；其余（entry issue、paced 重试）= SPECULATIVE（:2678-2682）。

---

### 2. 三个硬矛盾 → 根因判断

> A/B 冻结事实（不再重开）：RH 关闭 run A 首回收 +314.5s / 81.6GiB；RH 开启 run B 首回收 +126.5s / 30.4GiB；common clean window 120s；门：storage_hit 2.26x、restore_success 19=19、recompute 0.51x、extent_write 1.07x；B ready_pool 事件 38 个（最后事件 +121.7s）；B WAIT_CAPACITY 全程；B recycle 36,527 vs A 6,513。

#### 矛盾 1：READY / DEVICE_QUOTA 恢复冻结（ready_pool 卡 0，restore_success 停）

**根因判断：强嫌疑（双层机制，第一层为确认的几何/记账机制，第二层的现场绑定依赖远程日志复核）**

第一层 — **host headroom 冻结（代码级成立，机制闭合）**：
1. B 全程容量压力：metrics 快照 kv_pool_tokens=98305 / working=96312 / usable=98305（推断为 remote 运行；需以主机原始 metrics 复核）。
2. `_ready_host_headroom`（scheduler.py:3501-3514）= `pool.available_size() + ready_resident_tokens(views)`。working 96,312 → available ≈ 98305-96312 ≈ **1,993 tokens**；ready_resident = 0（ready_pool 已空）。
3. `headroom_fits`（ready_horizon.py:371-379）= `ready_tokens + inflight_tokens <= host_headroom`。单 state ~14K（KV）~21K（含 mamba 预算；RH 状态含 kv+mamba 混合 staging）≫ 1,993 → **每个 speculative stage 都被 NO_HEADROOM 拒绝**。
4. `_ready_horizon_pass` NO_HEADROOM park（scheduler.py:3377-3380）只产生 decline 记录、不释放任何 host 资源；不含独立时钟重试，仅 epoch event（scheduler.py:448-463 `epoch_event`：host_headroom up / l3_publish up / spec_budget down / waiting_frontier 变）或 safety_interval 兜底才重跑 —— 但 pool 无任何释放 epoch → **永久冻结**。
5. 与观测吻合：ready_pool 事件仅 38 个、最后事件 +121.7s（≈ 首个 device 到达后顷刻冻结）。

第二层 — **L3 extent 颠簸破坏 restore key（强嫌疑）**：
- extent_recycle 36,527 vs 6,513 = 5.6x 回收率说明 L3 在持续驱逐-重写（同一 key 反复写-回收-再写）。`_drop_slot` generation bump（extent_allocator.py:197-218）+ `entry_cleared` 只认 `cur > epoch_cursor`（ready_horizon.py:275-309 NO_L3）→ 被回收的 key 若在写回与新分配之间被探测到 = 0-hit → NO_L3。
- 这是「restore_success 19=19 不涨、storage_hit 2.26x 冻结」的直接候选解释；但 **storage probe 的确切时序（write→recycle→read 是否在同一 epoch 窗口内）需要远程日志中 extent_write/recycle/restore_disposition 的事件级时间线**才能定为确证（证据不足）。

第三层（次要候选）— **speculative budget 卡死**：
- `staging_candidates` 遇 `prefetch_speculative_rate_limited()` 直接 `[]`（ready_horizon.py:356-359）→ ready_pool 无新候选。release 路径齐全（release_prefetch :2357-2377 覆盖 finalize/revoke/abort），无泄漏迹象；但 A/B run 未对 `--enable-ready-horizon` 的 speculative 上限做过专项日志核验 → 未定位。

**DEVICE_QUOTA 出口核查（确认可逃逸，配置依赖）**：
- WAIT[DEVICE_QUOTA] 进入 = ADMISSION_DENY/LOAD_BACK_FAIL（scheduler.py:4455-4487，正常机制）。
- 出口三路：`promotion_wait_blocked`（hicache_restore.py:267-287）仅对 host_hit_length>0 且 budget 不满足的 waiter 持续 block；device charge wake（scheduler.py:3688-3696）；T13 timeout 60s（server_args.py:2852 `hicache_restore_wait_timeout_s = 60.0`）→ `next_restore` 时钟后 ADMIT_RECOMPUTE。
- → **理论上无死锁必然性**；「B 全程 WAIT」若成立必须是（a）T13 被 A/B 配置覆盖为 0/超大，或（b）recompute 恢复后立即被同一容量压力再次打回 WAIT（无限环路）。现场（B run 的 `--hicache-restore-wait-timeout-s` 实际值 + restore半周期时间线）**未定位**（远程日志待核）。

#### 矛盾 2：RH ON 首回收 +126.5s / 30.4GiB vs RH OFF +314.5s / 81.6GiB

**根因判断：强嫌疑 → 但解释分裂为三支，其中「文件实为 90G」的基座未经现场确认**

代码几何（确认）：90G/64M = 1440 slots；recycle 只在 cursor 环绕（extent_allocator.py:110-151，需 `MAX_SIZE > FILE_SIZE`）或 GC（`_gc_evict`，需 pressure > 0.9*max 或 disk<min_free）触发。累计写入 30.4GiB ≈ 486 slots ≪ 1440 → **cursor 环绕几何不成立**，除非：

- (a) **实际 extent file < 90G**：决定文章是 `SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE`（extent_file_backend.py:155-276）。gate3_ab.sh 传 `FILE_SIZE_ENV`（摘要确认 90G），但 slot 数一行 `ExtentFileBackend: ... slots=` 只能在远程 engine-gate3-ab-a-on.log 拿到 → **最大未决证据缺口**。若 file 实为 90G，则 cursor 环绕在 30.4GiB 次不可能触发 → 早期 recycle 必另有成因。
- (b) **mamba 单 key `set()` 未计量**（extent_file_backend.py:313-322 不写 `_log_extent_write`）：rh_gates2 的 extent_write 只计 batch_set_v1/v2 日志；单 key 写累计被低估 → 实际累计写可能远大于 30.4GiB 日志值 → 但(b)对 A/B 同偏，只改变绝对量、不改变「RH ON 更早」的相对事实。
- (c) **分配形状加速环绕前移**：mamba 每 key 写近满 64M extent（大件、单槽占满）→ slot 前进快；`passed.count(slot)` 一圈双过也 +2。RH ON 的候选形状使写分布更「大件化」→ 相对 A 提前跨越环绕阈值。纯推断，需日志验证分布。

**判定**：首回收「更早」的相对事实（+126.5 vs +314.5）在 RH ON 下与「extent 写入更多更快」(extent_write 1.07x、占用累积更陡) 相容；但**绝对提前量（30.4GiB 处即回收）无法用当前代码几何直接导出** → 证据不足档，阻塞在 (a) 一行远程日志。AV 前提：只有 (a) 打开（file 不是 90G）时此矛盾才「被根因叫停」；(b)/(c) 都只是把真相推到更远的证据层。

#### 矛盾 3：watermark_low=43513 vs ready_pool 峰值 ~28K（仅 2 个 READY × ~14K）

**根因判断：确证级机制（代码）+ 未定的因果开环（现场池尺寸分布）**

1. token 模式默认：state_p95=0（server_args.py:3068）→ `init_ready_horizon` 用固定 43513/87026（scheduler.py:1366-1395）。A/B wrapper 未设 `--ready-horizon-state-p95-tokens` → 默认成立（推断，需 server args 现场复核）。
2. `_below_low`（28K < 43513）恒真 → **refill 永远触发** —— 「low watermark 不可满足」原假说**排除**为冻结主因。
3. 真正锁点 = **headroom/promotion/budget 三重门**（矛盾 1 的第一层 + scheduler.py:3632-3696 + cache_controller prefetch 上限）：池被压到 <=2 个 state，**绑定约束不是水位而是容量门**。43513 仅是「按 state_p95 峰值定标」的结果；在 96K/98K working 的主机池下物理上装不下（2×~14K≈28K 已达几何上限）。
4. 数值：ready_pool 峰值 ~28K 与「池至多 2 个 state」的几何自洽（推断）；**现场 metrics 里 ready_tokens / host_headroom / inflight_speculative_tokens 的时序曲线**是闭合为确证的唯一缺口。

---

### 3. 八个机制点核对（正常 / 异常 / 未定位）

| # | 机制点 | 结论 | 代码定位 / 说明 |
|---|--------|------|-----------------|
| 1 | DEVICE_QUOTA 进入/退出 | 正常（进入），**退出待现场** | 进入 = ADMISSION_DENY/LOAD_BACK_FAIL（scheduler.py:4455-4487）正常；退出 = promotion_wait_blocked + device charge wake + T13；无死锁必然性，T13 生效依赖 A/B 配置 |
| 2 | watermark 域（tokens/bytes 混用） | 正常 | `_below_low`/`_issue_budget` 全 token 域；未发现混用（ready_horizon.py:201-217） |
| 3 | ready-host 记账 | 正常（易误解，注明） | `_ready_host_headroom = available + ready_resident` 是 M1 语义（resident 已占后再加回 available 做「可为之用」），非双重计数；与 `headroom_fits` 的 ready_tokens 参数不同域，见注释 |
| 4 | prefetch revoke release | 正常 | release_prefetch 全移除点必经、幂等、double-reserve assert（unified_radix_cache.py:2348-2377）；代码无泄漏路径 |
| 5 | WAIT 单向性 | 未定位 | 理论 T13 可逃逸；现场 A/B 是否设过 timeout、各 WAIT 周期真实长度缺日志 |
| 6 | RH 写放大 | 正常（不足以解释矛盾） | extent_write 1.07x 确认 RH 略多写；但非 2.7x 回收率差的来源 —— 回收差另有其因（矛盾 2） |
| 7 | extent live/committed/reclaimable | 未定位 | `used_bytes = sum(_slot_bytes)` 与 GC 的 `max_size*0.9` 交互；MAX_SIZE>FILE_SIZE 时 GC 永活但 cursor-wrap 决定回收；远程 slots 行是唯一判定 |
| 8 | 回收触发基座 | 异常（与观测矛盾） | cursor-wrap 需累计写 > file_size，与 30.4GiB 首回收矛盾 → 强指向 file_size<90G（(a)）或计量低估（(b)）；**这是全报告最强开问题** |

---

## summary

### 一、Conclusion（结论）

三个矛盾**不收敛于单一根因**，而是两条半独立、共享容量压力土壤的链：

- **矛盾 1 与 3 同根**：主机池 working ≈ 98%（96,312/98,305）→ `_ready_host_headroom` ≈ 1,993 tokens → `headroom_fits` 对一切 speculative stage 恒失败 → ready_pool 冻结于 0（矛盾 3 的「~28K 封顶」是同一容量上限的镜像：池至多 2 state）。**锁点不是水位，是 host headroom 门**。这是代码级闭合的机制，冻结为「强嫌疑」只因 ready_tokens/host_headroom 现场曲线未取到。
- **矛盾 2 独立**：extent 几何 + 计量 + 分配形状三种解释分流，阻塞在远程 `slots=` 启动行 —— 若 file 非 90G 更是单独缺陷，与矛盾 1/3 无关。
- 共享土壤：capacity pressure 同时喂三条链（headroom 缩、extent churn、promotion budget 挤）；RH+压力 → 抖动反馈（A' 实验已冻结）仍是最上层描述，本次为其给出机制填充。

### 二、Current Architecture（现状，确认）

RH 的准入-预取-恢复三层门（M1 headroom / M2 budget / M3 causal epoch / M4 READY-first / M5 inflight 记账 / M6 strict READY）与 restore 状态机在**单一请求边界内自洽**（A' 判定无独立状态机缺陷）；容量压力下 host headroom 门（scheduler.py:3501-3514 + ready_horizon.py:371-379）成无释放 epoch 的单向锁；extent 层以 cursor-wrap + generation 实现隐式回收，其触发与计量存在与直觉不符的边界（单 key set() 未计量、slot-pass generation +2）。

### 三、Issue-Forces（结构性张力）

1. **host headroom 门无可自愈输入**：`_ready_host_headroom` 只降不升（池满即 lock），lift 输入（host page 释放）在 working≈full 时不存在 → 冻结不稳定平衡。
2. **extent 回收证据双盲**：circlular wrap 触发与日志计量（set() 不计）两处盲区，导致早期回收根因无法从现有日志闭合。
3. **恢复入口与恢复出口的容量语义不对称**：入口看 admission（NO_TOKEN），出口看 promotion budget + device charge —— 两个指标在极端压力下可同时坏，形成 T13 反复打回环。
4. **水位定标无人值守**：43513/87026 是 state_p95 峰值定标，无现场自适应；池几何上撑不起该水位时水位语义失真（虽非冻结主因）。

### 四、Proposed（目标根因定位与最小修复面 —— **方案，不实现**）

**Fix A（矛盾 1/3 主修，host headroom 门自愈）**
- 最小面：`headroom_fits` 判定从「绝对 available」改为「available_lift 事件驱动」：当池空且 host 无释放 epoch 时，允许以 `watermark_high` 形态的宽松门放行**少量** staged（例如 ≤1 state），同时在 `epoch_event` 增加 host_release 单调计数，让「释放发生后」成为重评估锚点。
- 替代：NO_HEADROOM park 改为带 1-2 次重试的小 stopwatch（≤T13），避免无 epoch 空转。
- 风险：放宽过头会重燃 staging 抖动 → 必须配合 inflight_speculative_tokens 硬上限（已有）并验证 clean window 不劣化。

**Fix B（矛盾 1 的 DEVICE_QUOTA 出口加固）**
- 最小面：`next_restore` / T13 的 wait arm 若被 promotion budget 持续 block（`promotion_wait_blocked` 恒真），在 t ≥ timeout 后强制 ADMIT_RECOMPUTE 而非继续 `PREFETCH_BUDGET/DEVICE_QUOTA` 循环；或对 DEVICE_QUOTA 的 budget_fits 判定在 timeout 后降格（margin 归零）放行。
- 需先失「B 全程 WAIT」是否就是该环路的现场证据。

**Fix C（矛盾 2 证据补全 + 记账对称）**
- 第一步（零风险，只探）：远程取 `ExtentFileBackend: ... slots=` 行 + B run 首回收前后 120s extent_write/recycle 原始行 → 判定 (a)/(b)/(c) 三分之几。
- 若为 (b)：`set()` 补记 `_log_extent_write`（一处调用，计量对称）。
- 若为 (a) file<90G：修正 gate3_ab.sh 的 FILE_SIZE 传递或文档化该几何——那不是 bug 而是配置未遂预期。

**Fix D（矛盾 3 水位定标）**
- 若现场证实 state_p95=0 → 固定 43513 语义失真，minimal 变更是把 token 模式默认改为「池容量自适应」（如 min(watermark_low, 容量*系数)）—— 依赖矛盾 1 先修。

> 以上 Fix A-D 均为建议待评审；仅 Fix C 第一子步是「取证」，其余全部需用户/plan 批准后转 coder 实施。

### 五、Alternatives（取舍）

- **否决「加参数绕过 headroom 门」**（ready_horizon 曾出现过的加参绕行）：改判定而不是加旁路，避免二次错位（颠复方法论 3）。
- **否决「放宽到 watermark_low 无条件放行」**：与 RH 抖动根因（A' 冻结）正对撞，必须用可用 epoch 计数而非绝对量。
- 保留「入 metric 的 ready_tokens / host_headroom 曲线」作为不重启的探针优先于再跑 A/B —— 全部所需的 state 已在现有代码里可观测。

### 六、Impact（影响面）

- 冻结机制（矛盾 1/3）的修不需要碰 extent 层；extent 层问题（矛盾 2）即使成立也不阻断 RH 修复的 6 门验证（外环）。——两链独立性意味着**可按 Fix A+B 单独推进**，C 只需取证。
- 若 C(a) 成立（file 非 90G），gate3 A/B 的部分门结论（extent_write、回收窗）需要降权重读但不动 RH 自身判定。

### 七、Open Decisions（待用户/协调方裁决）

1. 是否批准 Fix A（host headroom 门事件化）与 Fix B（DEVICE_QUOTA timeout 降格）作为 P1 修复 `当时最小面`；实施走 coder。
2. 是否授权一次**只读远程取证**（拉 engine-gate3-ab-a-on.log 的 `slots=` 行 + 首回收窗口 120s 事件流、A/B server args 全量）以闭合矛盾 2 与 8 号机制点 —— 这是「证据不足档」的唯一出路。
3. 矛盾 3 的池容量自适应定标（Fix D）是随 A 一并做还是分开再做。
4. 6 个 fix 门里「首次回收不显著提前」的具体阈值需在 Fix C 取证后重定（否则该门无法量化）。

---

## followups

- [ ] 远程取证（阻塞矛盾 2 定档）：`grep -n -F 'ExtentFileBackend' /root/engine-gate3-ab-a-on.log` 拿 slot 数；B run 首回收前后 120s 的 `evt=extent_recycle` / `evt=extent_write`（批改）与单 key `set()` 未计量写入的事件并排时间线；A/B 两 run 的 `--hicache-restore-wait-timeout-s` / `--ready-horizon-state-p95-tokens` 实际参数。
- [ ] 选做：主机侧 metrics 曲线（ready_tokens / inflight_speculative_tokens / host_headroom / watermark）读 RMS 中段，闭合矛盾 1/3 为确证档。
- [ ] Fix A/B/C/D 的可行性设计细化（最小面落实到函数级）待用户批准后转 coder。

## open_issues

- **O1（矛盾 2，最强开问题）**：B 首回收 30.4GiB < file_size 90G 的几何矛盾；三分支 (a) file 实小 / (b) set() 未计量 / (c) 大件分布加速环绕 —— 未能本地闭合，阻塞「首回收提前」定档。
- **O2（矛盾 1 现场绑定）**：NO_HEADROOM 冻结是否需要“ULTRA 立证，来自 remote metrics 时序”；远程曲线未取到。
- **O3（T13 配置）**：B「WAIT_CAPACITY 全程」在 T13=60s 下需要「无限反复打回」解释；A/B 是否覆盖过 timeout 未知。
- **O4（8 号机制点）**：GC 与 cursor-wrap 双重回收语义的 MAX_SIZE>FILE_SIZE 交互仅代码级成立，现场无 slots 行印证。
- **O5（水位）**：43513 定标的「物理不可满足」已代码级解释，但 ready_tokens 现场峰值曲线（~28K）未取到，确证档欠最后一条证据。