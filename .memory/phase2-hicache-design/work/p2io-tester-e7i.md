# p2io-tester-e7i — 330 recompute 分类坐实（READY_HOST eligibility 疑点）

- 任务：e7i（PURSE LOG ANALYSIS，纯日志分析，不改代码、不跑新实验）
- 数据源：`/tmp/p2io-e7h-r2-ev/engine.log`（932 KB，e7h 干净 r2 证据；远端镜像 `/root/evidence-p2io-extent-m4t-e7h-r2/run-20260901-215818/`）
- 日期：2026-09-02（epoch e7i）

## 1. status

**done**（分类坐实完成；结论与用户裁决的 READY_HOST eligibility 疑点方向一致，但机制不同）

## 2. artifacts

- 本报告 `p2io-tester-e7i.md`（六节）
- 数据源 `/tmp/p2io-e7h-r2-ev/engine.log`（330 次 recompute / 90 个 rid / 6497 行）
- 分析命令与原始输出：见 §3（全部在 `/tmp/p2io-e7h-r2-ev/` 目录就地执行，结果可复现）
- 未产生新代码、未改引擎、未跑新实验（遵守 e7i 纯日志分析边界）

## 3. evidence（命令 + 真实输出）

数据源统一为干净 r2 日志（远端 `/root/evidence-p2io-extent-m4t-e7h-r2/run-20260901-215818/`；本机 `/tmp/p2io-e7h-r2-ev/engine.log`）。三份早先证据 `run-20260901-214451/214455/214500` 为 triple-launch 损坏目录（无 engine.log 本体），不参与本次分类。

### 3.1 全局计数

```
$ grep -c 'restore_recompute' engine.log                       → 330
$ grep 'restore_recompute' engine.log |grep -c 'survivability=host'  → 329
$ grep 'restore_recompute' engine.log |grep -c 'survivability=l3'    → 1
$ grep 'prefetch_revoke' engine.log |grep -c 'storage_hit=0'    → 330   # 100% 的 revoke 都 storage_hit=0
$ grep 'restore_recompute' engine.log |grep -oE 'rid=[0-9a-f]{32}' |sort -u|wc -l  → 90
```

### 3.2 用户三类分类的核心事实：`host_hit` 字段在整份日志中不存在

```
$ grep -c 'host_hit' engine.log        → 0
$ grep -c 'host_hit_length' engine.log → 0
$ ssh ... root@175.155.64.171 "grep -c host_hit /root/engine-p2io-m4t-e7h.log" → 0
```

`prefetch_revoke` 事件只携带 `storage_hit`（L3 extent 存储覆盖），**不携带 `host_hit`**：
```
[2026-09-01 21:58:20] [P2A] ts_ms=1788271100216 evt=prefetch_revoke rid=e0830679ef7b48a98d10d958e28f7571 terminated=False storage_hit=0 requested=20910 miss_reason=miss storage_generation=0
```

含义：用户的三类分类（FULL_HOST/PARTIAL_HOST/STALE/INVALID）以 `host_hit` 为判据，
但 `host_hit` 从未埋点。可观测的代理指标是 `storage_hit`（L3 存储覆盖）与
`final_storage_survivability`（host 树根存在性）。**因此按现有日志唯一可证的分类是
"STALE/INVALID：host 元数据存在（survivability=host）但 L3 可装载存储页 = 0"。**

### 3.3 恢复状态机：无任何请求到达 READY

```
$ grep -c 'state=READY' engine.log  → 0
$ grep -c 'evt=restore_ready' engine.log → 0
$ grep -c 'evt=ready_stage'  engine.log → 0
$ grep -c 'evt=ready_pool'   engine.log → 1
$ grep 'evt=ready_pool' engine.log | head -1
[2026-09-01 21:58:04] [P3] ts_ms=1788271084338 evt=ready_pool size=0 tokens=0 watermark=[2/4]
```

`restore_state` 分布：330 NONE / 495 RESTORING / 450 WAIT_CAPACITY，**0 READY**。
`next_restore()`（hicache_restore.py:69）T8 状态机：只有 `FINALIZED` 事件在
`RESTORING → READY`；无 restore_finalized 事件（`grep -cE 'restore_read|restore_success|io_finished|restore_finalized'` = 0）。

### 3.4 准入侧：disposition 全部 granted=0（零恢复准入）

```
$ grep 'restore_disposition' engine.log |grep -c 'granted=0' → 362  (= 全部)
```

disposition 组成（360 RECOMPUTE + 2 WAIT(rate-limit)），无一条 `granted>0`：
每次准入都是纯重算，未从缓存恢复任何 token。

### 3.5 设备侧：38/90 recompute rid 之后拿到 promotion_reserve（准入时竞态 host_hit）

```
$ grep 'promotion_reserve' engine.log |grep -oE 'rid=[0-9a-f]{32}' |sort -u|wc -l → 44
$ comm -12 <(recompute rids) <(promotion rids) | wc -l → 38
```

这 38 个 rid 的"成功"是准入时竞态命中 host 前缀（race-style host_hit），不是
ready-horizon 确定性 restore（那需要 READY 态，而 READY 计数为 0）。

### 3.6 extent_write 总量（写入侧：有写入，但无一次可装载 restore）

```
$ grep -c 'extent_write' engine.log → 135
kv: 90 events / 79746 keys / 2,613,116,928 bytes
mamba: 45 events / 45 keys / 2,318,008,320 bytes
```

135 次 extent_write（node=None，节点/组件标签，无 rid），说明 L3 写回动作确实发生；
但 330 次 revoke 全部 storage_hit=0、330 次 recompute 全部 miss——写入的内容在下次
查找时覆盖为 0。storage_generation 单调递增（0→39），生成号在走，但可装载存储链从未闭合。

### 3.7 运行终止：e7h 实际以 invariant 断言崩溃结束（新增发现，属 e7h 报告范围）

```
[2026-09-01 22:06:13] Sanity check FAILED (4 violations across 71 nodes):
  H-leaf extra: [68]
  Duplicate ghosts: [66, 68]
  1 stale nodes in host_leaves: [68]
  mamba host LRU: +S3=set(), +lru={66, 68}
[2026-09-01 22:06:13] Scheduler hit an exception: AssertionError (invariant_checker.py:470 _check_tree_cache → unified_radix_cache.py:4322 sanity_check → unified_tree_core.py:2752)
```

`invariant_checker` 在 on_idle 对 host_leaves/ghost 树一致性断言失败，scheduler 退出
（随后 22:06:18 kill_process_tree）。即 e7h 主门 G1「无崩溃跑完全程」**实际为假**——
这不是 e7i 任务范围，作为 followup 上报（见 §6）。

## 4. summary（核心结论）

### 4.1 三类分类数量与占比（330 = 329 survivability=host + 1 l3）

| 类别 | 数量 | 占比 | 判定依据 |
|---|---|---|---|
| FULL_HOST（host_hit == requested） | **不可证（0 可证）** | — | `host_hit` 字段未埋点（全日志 0 出现） |
| PARTIAL_HOST（0 < host_hit < requested） | **不可证（0 可证）** | — | 同上 |
| STALE/INVALID（host 元数据存在但实际不可复用） | **330 / 330** | **100%** | storage_hit=0（L3 可装载覆盖=0）× survivability=host（host 树根存在）共存 |

关键语义澄清：`final_storage_survivability=host` 只表示 host KV-tree 根节点存在
（scheduler `_final_storage_survivability` 检查），**不等于** host 前缀可装载用于 restore。
`prefetch_revoke storage_hit=0` 表示 L3 extent 存储查找覆盖为 0（cache_controller
`_storage_hit_query` → `storage_backend.batch_exists`）。二者共存正是用户分类中
"STALE/INVALID：host metadata 存在但实际不可复用"的精确语义。

### 4.2 FULL_HOST 是否显著？

**按可证口径：不是 FULL_HOST（0 可证），而是 100% STALE/INVALID。**
- 330/330 revoke 全部 storage_hit=0；
- 330/330 recompute 全部 cause=miss、final_storage_survivability=host（329）或 l3（1）；
- 362/362 disposition 全部 granted=0；
- 0 个 restore_state 到达 READY。

因此 **READY_HOST eligibility bug 的存在性被佐证，但机制不是用户假设的
"state 已在 Host 却未经 L3 restore 转 READY 而永不被视为 READY_HOST"**——而更基础：
**整个 L3 恢复链从未闭合**（storage_hit 恒 0），所以任何请求都走不到 FINALIZED→READY 转换
（next_restore T8 要求 `RESTORING→READY`，但 restore_finalized 事件数为 0）。ready_horizon
`_is_ready_resident` 要求 `state is READY and staged_tokens>0 and full_prefix`，READY 态恒空 →
ready_pool 恒 `size=0 tokens=0`（全日志仅启动时打 1 行）、ready_stage=0。

### 4.3 代表 rid 案例

- **STALE/INVALID 且最终竞态准入（38 个之一）**：`5acccd11`（M4T 8×12 首个工作 rid）
  — 35 次 recompute（全 miss/survivability=host/storage_hit=0），末次后拿到
  `promotion_reserve n=15513`（22:06 附近）→ 设备准入。35 次重算后才命中一次 host 前缀，
  是准入时刻的竞态 host_hit，非 ready-horizon restore。
- **STALE/INVALID 从未准入**：`e0830679`（run 首个 20910-token 请求）—
  prefetch_issued→RESTORING→revoke(storage_hit=0)→disposition RECOMPUTE(granted=0)→
  NONE→recompute(cause=miss, survivability=host)，全程无 promotion。host 树根存在
  （survivability=host）但 L3 装载覆盖 0，即"host metadata 存在但实际不可复用"。

### 4.4 host 前缀来源：第一次写就留在 Host 还是 L3 restore 到 Host？

**日志无法判定（诚实结论，非编造）**：
- `restore_backup`（49 事件）、`promotion_transfer`（52 事件）均携带 `rid=none`
  （node/component 标签，见 §3.1 字段枚举：node 374 次、component 135 次）；
- `extent_write`（135 事件）同样无 rid；
- 全日志无 `host_hit`、无 restore 成功/完成事件。

因此"这 38 个 FULL_HOST 前缀是首次写落 Host 还是 L3 restore 到 Host"无法从现有埋点
区分。要坐实需 coder 在 `promotion_reserve`/`promotion_transfer` 或 `prefetch_revoke`
事件里补 `host_hit` 字段（或 restore 成功时打 `host_loaded_pages`）。

### 4.5 ready_pool 恒空 + restore_ready=0 的直接证据链（闭环）

1. `restore_ready` 事件数 = 0；`restore_state state=READY` = 0（§3.3）；
2. `next_restore` T8：READY 只由 `FINALIZED` 事件从 RESTORING 迁入，而
   `restore_read|restore_success|io_finished|restore_finalized` 事件数 = 0（§3.3）；
3. `ready_stage` = 0、`ready_pool` 仅 1 行 `size=0 tokens=0 watermark=[2/4]`（§3.3）；
4. `_is_ready_resident` 三条件（READY 态 + staged_tokens>0 + full_prefix）中 READY 恒空
   → `ready_count=0`、`ready_resident_tokens=0` 恒成立 → ready_pool 恒空；
5. 配置确认：`enable_ready_horizon=True`、`ready_host_watermark_low=2/high=4`、
   `ready_horizon_state_p95_tokens=0`（回退到 legacy 2/4 count 水位）、
   `hicache_restore_backup_park=False`。

即：ready-horizon 从未组装出任何 READY 成员，不是水位/预算问题（水位低门槛 2 且
headroom 充足），而是**下游 L3 恢复链从未闭合，上游 READY 态根本不可达**。

## 5. followups（数量 + 位置 + 建议）

1. **埋点补 `host_hit`**：`prefetch_revoke`（cache_controller.py `prefetch_thread_func`
   1291-1344）补 `host_hit=N`；`promotion_reserve/transfer` 补 rid；restore 成功时补
   `host_loaded_pages`。作用：坐实用户 FULL_HOST/PARTIAL_HOST 分类、区分"首写落 Host"
   与"L3 restore 落 Host"。建议 coder 实施。
2. **L3 恢复链为何不闭合（storage_hit 恒 0）**：330 revoke 全 storage_hit=0 而
   extent_write 135 次写入 2.6GB kv + 2.3GB mamba——写入侧在跑、读取侧恒 0。
   需排查 extent backend `batch_exists` 与 `_storage_hit_query` 的键/前缀匹配
   （generation 从 0 单调到 39，疑似 generation/segment 元数据不同步）。建议
   architect/coder 专项。
3. **e7h G1 主门应判 FAIL**：22:06:13 `Sanity check FAILED`（host_leaves/ghost 一致性，
   invariant_checker.py:470）→ scheduler 崩溃，e7h 并非"无崩溃跑完全程"。建议 e7h
   报告修订 G1 结论并补这条证据（本报告 §3.7）。
4. **e7h 30 差额细分门（判据 6）**：e7h 843 vs 1001 的 158 差额中，本分类贡献
   "NEVER/PARTIAL/FULL_THEN_LOST" 的证据——90 rid 全 STALE/INVALID 且 52 个从未
   promotion。可在 e7h 报告中引用本分类（rid 表见 §3.5 附注）。

## 6. open_issues（未解决/风险）

- **`host_hit` 不可测**：用户三类分类的判据字段未埋点，本报告只能给出代理指标下的
  "100% STALE/INVALID"结论；FULL_HOST/PARTIAL_HOST 的绝对数量无法从现有日志给出。
  要给出用户口径的完整分类，必须先落地 §5.1 埋点（属 coder 范围）。
- **Q4（首写落 Host vs restore 落 Host）不可判定**：`restore_backup`/`promotion_transfer`/
  `extent_write` 均 rid=none，现有埋点无法区分两个来源。
- **e7h 运行以 invariant 崩溃结束**：对 P2-IO 三层的"无崩溃"判据是负信号，且
  H-leaf extra/duplicate ghosts/stale host_leaves 指向 host 树 LRU 与 ghost 处理的一致性
  bug——是否与 ready-horizon 恒空同根（host 侧元数据从不清理/从不正确晋升）需专项。
- 本任务为纯日志分析，未动代码、未跑实验；上述问题按 followup 上报，不在此修复。
