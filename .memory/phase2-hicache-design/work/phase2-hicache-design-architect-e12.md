# phase2-hicache-design-architect-e12 — promotion admission 设计（专家裁决第二刀：H→D 容量预约）

## status

done — 只读设计完成（未修改任何引擎文件）。设计交付物
`/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-promotion-admission.md`（新文件，
因 p2-1-design.md 已有 §8 埋点/§9/§10，追加同名节会冲突）。核心决策：budget 检查并入既有
WAIT_CAPACITY[DEVICE_QUOTA]（零新状态）；检查点位于 load_back 入口（锁之前）+ _load_back_transfers
精确门（evict_for_alloc 之前）；reservation 计数器绑定 _OngoingLoadBack、ack 归还；唤醒复用每 pass
T11 谓词重读；margin 初始 2048（算术证明 0 不串行化 2×16K）。所有引用真实（file:line，当前工作树）。

## artifacts

- 设计文档（交付物）: `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-promotion-admission.md`
  （§0 定稿语义逐条映射 / §1 不变量 / §2 现状核查 / §3 机制 / §4 交互 / §5 改动面 / §6 验证 /
  §7 Test B 顺序 / §8 风险 / §9 开放问题）
- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e12.md`
- 引用基线: `p2-1-design.md`（M1/M2 定稿，§2 状态机 / §4 结构）、architect e11 报告（崩溃机制 /
  prefetch 预算先例）、tester e22（Test A K=16 现场）、当前工作树代码（M1b 已实现）

## evidence

| # | 事实 | 证据 |
|---|---|---|
| E1 | H→D promotion 唯一入口链（scheduler 线程内同步提交、异步 ack）：准入循环 → add_one_req → `with _lock_node` → needs_host_load_back → init_load_back → load_back（inc_host_lock_ref 1567 / inc_lock_ref 1570 → _load_back_transfers → evict_for_alloc 1623-1626 → load 1635 → ongoing_load_back 注册 1653-1657）→ ack drain 3289-3293 | unified_radix_cache.py:1557-1659, 3251-3308；schedule_policy.py:1281, 1358, 1401-1419；scheduler.py:3877-3895, 4002 |
| E2 | 锁的 device 总量 = capacity − available − evictable（派生，非计数器）：e11 K=32 崩溃 dump 算术 1033+10231+21504=32768 精确吻合；树侧与调度侧访问器齐备（_component_available_size 645-654、full_evictable_size unified_tree_core.py:2667、available_and_evictable_tokens schedule_policy.py:537-551、size_full multi_ended_allocator.py:1837） | unified_radix_cache.py:645-654, 1623；e11 E1/E5 |
| E3 | 链锁仅 4 处获取（chunk 1143 / backup 1472 / load_back 1570 / ongoing 1655）+ 准入 _lock_node（schedule_policy.py:1132）；load_back 入口时调用方已持准入锁 → 派生 locked 已含本请求前缀 → 检查点无漏计 | unified_radix_cache.py:1143, 1472, 1570, 1655；schedule_policy.py:1129-1143 |
| E4 | budget 拒绝可走既有 RESTORE_DENIED → LOAD_BACK_FAIL → WAIT[DEVICE_QUOTA] 通路（状态机零改动）：load_back False → init_load_back 空匹配 3358-3361 → schedule_policy 1409-1419 → scheduler 3944-3955 → hicache_restore.py:116-117 | 各处行号如上 |
| E5 | 每 pass 唤醒次序成立：check_hicache_events（scheduler.py:3727，内含 loading_check → ack 归还）先于 _reconcile_restore_states（3729，T11 扫描）→ reservation 释放与谓词重读同 pass 可见 | scheduler.py:3727-3729；unified_radix_cache.py:3388-3449 |
| E6 | abort 不取消在途 load：release_aborted_request（2557-2600）只清 prefetch 侧，不碰 ongoing_load_back；drain 按 ack_id 弹队列（3274-3288）与请求存亡无关 → load 必达 ack → 归还必发生 | unified_radix_cache.py:2557-2600, 3274-3293 |
| E7 | 纯 aux（kv_tokens=0）恢复存在（swa/mamba host hit，needs_host_load_back schedule_batch.py:1269-1275）→ budget 必须只挂 FULL-KV promotion（est=0/kv=0 跳过），aux 池有自己的预算（rem_swa_tokens schedule_policy.py:1332-1345） | schedule_batch.py:1269-1275；schedule_policy.py:1332-1345 |
| E8 | 解码侧（disagg）也走同一 init_load_back → load_back（decode_hicache_mixin.py:207），无 WAIT 态（自有 PENDING/READY/FAILED + 每 pass 重试 242 起），且已有恢复量预约（restore_token_count 45-47 / _hicache_pending_restore_tokens 141-151）；launch 脚本无 disagg 参数 → Test 为单机形态 | decode_hicache_mixin.py:45-47, 141-151, 183-240 |
| E9 | margin 算术（2×16K 串行化）：B 在 A 在途时 16K+16K+16K=48K 任何 margin 都拒；A ack 后 16K+0+16K=32K ≤ 32768−margin → **margin=0 通过**（崩溃形态残余），margin≥1 拒，2048（1 chunk）= walker 最小可满足分配底线 | 本设计 §3.1；e11 E1（alloc 2048 失败） |
| E10 | Test A 基线（派发定案）：forced_drop 占比 28.8%（K=32）、K=32 timeout 475/651、OOM=0；K=16 现场 forced_drop 8/29=28%、hollow 21、backup_failed=0（tester e22） | 派发指令 + tester e22 §3.4 |

## summary

### 结论（一句话）

promotion admission = 在 H→D 启动前（load_back 入口，device lock 之前）与 evict_for_alloc 之前做
`device_locked_tokens + inflight_promotion_reserved + new_restore ≤ device_capacity − margin` 的
容量预约；拒绝走既有 RESTORE_DENIED → WAIT_CAPACITY[DEVICE_QUOTA] 通路（**状态机零新状态**）；
reservation 绑定 _OngoingLoadBack 由 load ack 归还（abort 由"load 必达 ack"论证覆盖）；
唤醒复用每 pass T11 谓词重读（同 pass drain→reconcile 次序保证时效）；margin 初始 2048（算术证明
margin=0 不串行化 2×16K，与"0 或小值"直觉相反，标定 sweep {1024,2048,4096}）。

### Current Architecture（当前架构——事实层）

1. H→D 是唯一被 budget 限制的迁移段：L3→H 有 prefetch_capacity_limit（0.5×host=24576，
   cache_controller.py:649-656）按 span 锁步计费、可超发（e11 E15）；H→D 目前无任何前置预算，
   只有 load_back 内 avail<kv → evict_for_alloc → 不足则 return False（unified_radix_cache.py:1623-1630）
   的**事后**容量门（C4，已由 M1b 转为 WAIT[DEVICE_QUOTA]）。
2. M1b 已实现：WAIT_CAPACITY[DEVICE_QUOTA] + T11 每 pass 谓词重读（scheduler.py:3042-3086,
   3160-3192）+ T13 60s 超时 + admission skip（3886-3890）；拒绝事件 LOAD_BACK_FAIL 已存在。
3. 崩溃形态（e11）：锁驻（K=32 共享链 20480 lock=2）≈ 2/3 池 + evictable 不可达 → walker 撞墙 →
   Z3 兜底（forced_drop_to_miss 865-872）→ Test A OOM=0 但 forced_drop 28.8% 偏高 = 撞墙仍频繁。

### Issue-Forces（结构力冲突）

- **F1**：device working set 无前置承诺——两个大 promotion 可先后锁驻同一池（2×16K 超池崩溃史），
  撞墙在锁驻已成事实后才发生（evict_for_alloc 事后腾挪）。
- **F2**：M1b 的 WAIT→wake 循环成本高——T7 拒绝后 T11 谓词不含预算项，wake → re-prefetch →
  finalize → admission 再拒 → 回 WAIT，每循环烧一个完整 prefetch 周期（L3 读 + host 暂存 + 锚钉叶）。
- **F3**：无"锁驻余量"底线——locked 可达 cap（margin=0 的 2×16K 通过），available+evictable 可塌缩到
  小于一个 chunk，walker 无叶可放（Z3 无法帮助）。

### Proposed Architecture（目标）

- **budget 不变量**：`locked + inflight_promotion_reserved + new_restore ≤ capacity − margin`，
  locked 为派生量（capacity − available − evictable，与 P2-0 指标同源），reserved 为新计数器（绑定
  _OngoingLoadBack 第 4 字段，ack 归还）。
- **检查点 1（入口门）**：load_back:1566（inc_host_lock_ref 之前）——est=req.host_hit_length；
  拒绝 = return False → 既有 RESTORE_DENIED 通路；est=0（纯 aux）跳过。满足"reservation 在
  device lock 之前"。
- **检查点 2（精确门 + reserve）**：_load_back_transfers:1621-1623 之间（evict_for_alloc **之前**）——
  exact kv_tokens；拒绝时根本不启动 walker（forced_drop 下降的机制点）；reserve 后全部出口
  （E3 evict 不足 / E4 load None / E5 ack）逐条归还；sanity_check 加 I2 断言
  （reserved == Σ ongoing_load_back）。
- **唤醒**：T11 谓词扩展预算项（DEVICE_QUOTA + host_hit>0 才加）；同 pass 次序（drain 3727 先于
  reconcile 3729）保证释放即见；不建显式 wake 集合（谓词可精确检验 → 无事件可丢）。
- **margin**：初始 2048（1 chunk）；sweep 标定；单测钉死"margin=0 不串行化"。

### Alternatives（对比与为何合并/双计胜出）

| 维度 | 合并进 WAIT[DEVICE_QUOTA]（采用） | 新状态 WAIT_PROMOTION | 说明 |
|---|---|---|---|
| 新路径 | 零（走既有 RESTORE_DENIED/LOAD_BACK_FAIL） | 新事件/新 wait_reason/新时钟/新 admission skip/新 T13 分支 | 拒绝语义与 T6/T7 同族（device 容量瞬态），无区分必要 |
| 唤醒 | 既有 T11 + 一个预算项 | 新谓词 + 新超时 | 双 WAIT 时钟冲突风险 |
| 遥测区分 | evt=promotion_denied + 计数 | 状态名区分 | 遥测已足够 |

| 维度 | 双计式（专家字面，采用） | 系统精确式（在途 span 从 locked 剔除） | 说明 |
|---|---|---|---|
| 公式 | locked(含在途 load 锁) + reserved + new ≤ cap−margin | (locked−reserved) + reserved + new（抵消极） | 同一不变量（running_locked_excl + reserved + new ≡ derived_locked + new）；双计更保守、实现直白、上界 = 在途 span（ms 级延迟） |

| 维度 | 检查点 1+2（采用） | 仅检查点 1（est） | 仅检查点 2（exact） |
|---|---|---|---|
| 拒绝成本 | 入口最廉价（锁前）+ 精确兜底 | est 偏差漏拒/误拒 | 拒绝时已锁链 + build spec |
| evict 前拦截 | 检查点 2 保证 | 不保证 | 保证 |

### Impact（对已验证机制）

- M1b：强化不替代（§3.5 决策）；状态机零改动；T11 谓词只加一个保守项。
- prefetch / P2-0a 8 并发：零触碰（budget 只挂 H→D）。
- Z3：分支零改动；forced_drop 下降为 Test A' 判据（admission 减撞墙、Z3 保逃生）。
- F1/F2/ACK：零触碰（只动 load 路径；ack 归还追加在 pop 之后）。
- 解码侧（disagg）：同一入口自动生效；D 侧无 WAIT，FAILED 每 pass 重试；当前单机形态不受影响。
- 崩溃史（2×16K/单锁 16K）：margin=2048 下 32K 锁驻必拒 → 至多一个 16K 大 promotion 在途。

### 验证设计

1. torch-free 单测（test_storage_regression.py stubenv）：budget 纯函数边界（含 margin=0 钉死）；
   生命周期归还（E3/E4/E5 全路径计数器归零）；拒绝→WAIT 通路（钉"零新状态"）；T11 预算项
   （不足不 wake / 释放后 wake / T6-host_hit=0 不拦截）；16K 串行化集成。
2. Test A'（K=32 同参数，fresh ns）：forced_drop 占比显著下降（基线 28.8%，目标 <15%）；timeout 下降
   （基线 475/651）；OOM=0 + 越 989s 崩溃点 + 优雅退场；promotion_denied>0 且 inflight 峰值 ≤16K。
3. 回归：K=16（128/128 越 470s）、K=1（fresh+warm 12/12）、test_drain_reentry.py、CHAIN_GAP。
4. margin 标定 sweep {1024, 2048, 4096}。
5. Test B（epoch）顺序：本设计先行，串行单变量；文件域零重叠（本设计不碰 storage metadata）。

### 改动面（8 项）

unified_radix_cache.py:1566（入口门）/1621-1623（精确门+reserve）/407+179-184+1653-1657+3289
（计数器+第4字段+归还）/sanity_check 3644-3647（I2 断言）；hicache_restore.py（纯函数
promotion_budget_fits）；schedule_policy.py:537 旁（device_locked_tokens helper）；
scheduler.py:3160-3192（T11 预算项 ⚠ 行号漂移）；server_args.py:2840 旁（margin arg=2048）；
埋点 4 事件。**状态机与 Req 零改动**（本设计最小面的核心）。

## followups

1. 协调人裁决：margin 初始值 2048（非 0——§3.1 算术：0 不串行化 2×16K）；双计式；T11 预算项条件
   （DEVICE_QUOTA + host_hit>0）；批准后 coder 实现 + 单测，tester 按 §6 跑 Test A' + K=16/1 回归。
2. 观测点：promotion_denied/denied_exact/reserve/release 计数 + inflight 峰值；30s 汇总扩展。
3. 后续（非本次）：解码侧 disagg 场景专项验证（改动自动覆盖，验证随场景走）；margin 标定结果写回
   设计文档 §3.1。

## open_issues

- margin=0 与专家"建议初始 0 或小值"的字面冲突：本设计给出反例算术（32K ≤ 32768−0 通过 → 崩溃形态
  残余），建议 2048；最终以 Test A' sweep 数据裁决（O1）。
- est（host_hit_length）与 exact（kv_tokens）偏差在解码侧的幅度未实测（D 侧 req.host_hit_length 与
  rematch 值可能不同）——精确门权威兜底，偏差只影响拒绝时机。
- 双计式对"小 promotion 被大 promotion 在途窗口延迟"的量化（ms 级理论值）留 Test A' 实测
  （h_to_d_wait 指标）。
- 行号漂移（engine 修复并行）：实现时按新树重定位（改动面 2 处 ⚠）。
