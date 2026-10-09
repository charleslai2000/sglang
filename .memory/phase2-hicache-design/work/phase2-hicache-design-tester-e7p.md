# phase2-hicache-design-tester-e7p.md — Mamba contract 三 case deterministic harness verdict

## 1. status

done（四 case 确定性 harness 已跑、output=exit 0；recompute 量化已完成；source-check 代码路径已定位；
报告落盘。没有改动生产代码，没有启动 3090 引擎，仅新增一个 3090-dev/ 纯算术量化脚本）。

## 2. artifacts

- harness：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/p2io_e7p_three_cases.py`（磁盘已就绪，未重写）
- 量化脚本（本次新增，纯算术无 torch）：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/p2io_e7p_recompute_quant.py`
- 本次运行命令：
  - `cd /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache && /home/charles/sglang-venv/bin/python 3090-dev/p2io_e7p_three_cases.py`
  - `/home/charles/sglang-venv/bin/python 3090-dev/p2io_e7p_recompute_quant.py`
- 运行耗时：harness ~秒级；量化 ~秒级。全部单 python 实例，无 torch 大 tensor（量化为纯算术）。

## 3. evidence

### 3.1 四 case 原始输出（harness, exit code 0）

```
Unsupported element_size = 32 for JIT HiCache kernel
Failed to load staged JIT HiCache kernel: [Errno 2] No such file or directory: 'ninja'
node=2048 pages, mamba key at chain[2047] = c2dc411aa31742a7

=================== CASE A: exact node boundary ===================
  query full 2048 prefix: kv_pages=2048 extra={'kv': 2048, 'mamba': 2048} usable=2048
  mamba present at: [2047]

=================== CASE B: partial prefix (1892) =================
  query partial 1892 prefix: kv_pages=0 extra={'kv': 1892} usable=0
  mamba present in span: [] (node-last at chain[2047] NOT in span)

=================== CASE C: KV-only (mamba disabled) ==============
  query partial 1892 prefix, no mamba transfer: kv_pages=1892 extra={} usable=1892

=================== CASE A': split-node exact restore ============
  query full node19(3)+node22(6)=9 prefix: kv_pages=9 extra={'kv': 9, 'mamba': 9} usable=9
  mamba present at: [2, 8]

=================== SUMMARY ===================
CASE A  exact node boundary (2048):  usable=2048
CASE B  partial prefix (1892):                usable=0
CASE C  KV-only partial (1892):               usable=1892
CASE A' split-node exact (9):                usable=9
EXIT_CODE=0
```

逐行解读：

- **Case A（exact 2048 node boundary）**：`kv_pages=2048 extra={'kv': 2048, 'mamba': 2048} usable=2048`。
  TRAILING 扫描窗口（`kv_pages=2048` 时 `range(max(0,2048-1),2048)`=最后一页）正好命中写侧 key
  `node.hash_value[-1]`（index 2047）→ mamba boundary=2048 → final_pages=2048 → 全量 restore OK。
- **Case B（partial 1892 within 2048 node）**：`kv_pages=0 extra={'kv': 1892} usable=0`。
  KV allocator 层能找到 1892 页（`rerun_exists` 里 `kv_pages` 字段 = `r.kv_hit_pages` 为 0 是因为
  all-or-nothing 规则把最终 usable 钳到 0；`extra={'kv':1892}` 是底层 `batch_exists_v2` 里
  `hit_count={KV: kv_pages}` 的原始 present 计数）。mamba TRAILING 扫描的窗口是 `keys[1891:1892]`，
  而写侧 mamba key 在 index 2047，不在 span → boundary=0 → `final_pages=min(1892,0)=0` →
  translate-rule（unified_radix_cache.py:2917 的 all-or-nothing 等价）→ usable=0 全丢。
  **这就是实际的 mamba key 位置错位**：读侧 TRAILING 窗口永远查不到写侧 node-last key。
- **Case C（KV-only 无 mamba 侧车）**：`kv_pages=1892 extra={} usable=1892`。KV 层独立健康，
  1892 页判定 present。
- **Case A'（split-node exact：node19(3)+node22(6)=9 页，session-resume full-history 形状）**：
  `kv_pages=9 extra={'kv':9,'mamba':9} usable=9`，mamba present at [2,8]（node19 尾=index2、
  node22 尾=index8）——多节点精确到边界的查询每个节点尾 checkpoint 都对齐。这与 Case A 同语义：
  exact node-tail restore → full usable。

### 3.2 recompute 量化（纯算术模拟，seed=7，2000 sessions × 24 turns = 48000 samples）

模型（与 harness 的 node 模型一致）：node=2048 tokens，mamba checkpoint 只在节点**最后一项**
`hash_value[-1]` 上写一次；turn 增量 ~ Uniform[512,4096]；查询停在 node 中途（partial miss）。

```
simulated turns = 48000
node=2048 tokens; turn delta ~ Uniform[512,4096]

=== 1. last-valid-boundary offset（tail recompute）分布 ===
  mean tail  = 1022.8  tokens（U[0,2047] 理论 ~1023.5）
  p10=206, p50(median)=1022, p90=1839, max=2047
  exact boundary tail=0: 20/48000 = 0.042%
  first-node（P<2048, 无 checkpoint → fallback=full）: 960/48000 = 2.000%

=== 2. per-request effective_cache_ratio（分母 = 标称 context）===
       ctx |  (a) all-or-nothing | (b) fallback avg | (b) fb min（最差单请求）
     32768 |              12.12% |           96.88% |               93.75%
     65536 |              56.06% |           98.44% |               96.88%
    131072 |              78.03% |           99.22% |               98.44%

=== 3. per-request ratio（分母 = 实际当前 prefix P）===
  ctx~   32768 (34606 turns): fallback avg ratio = 96.90%  worst = 88.89%
  ctx~   65536 (20383 turns): fallback avg ratio = 97.72%  worst = 94.12%
  ctx~  131072 (45 turns):  fallback avg ratio = 98.99%  worst = 97.32%

=== 4. session-aggregate recompute fraction（总 tail / 总 token）===
  ctx~   32768: total tokens=1266366908 | fallback recompute=34996668 (2.76%) | all-or-nothing=100.00%
  ctx~   65536: total tokens=916940492  | fallback recompute=20453068 (2.23%) | all-or-nothing=100.00%
  ctx~  131072: total tokens=3022940   | fallback recompute=30812   (1.02%) | all-or-nothing=100.00%

=== 5. 5% recompute-overhead 阈值（fallback）===
  ctx~   32768: recompute_overhead = 2.76%  （<= 5% — node-level enough）
  ctx~   65536: recompute_overhead = 2.23%  （<= 5%）
  ctx~  131072: recompute_overhead = 1.02%  （<= 5%）
```

关键量级：

- **当前 all-or-nothing 路径**（Case B 语义）下 recompute = 整个 prefix → session-aggregate
  recompute 100%，即 effective_cache_ratio = 0%（对每个 partial 请求）。
- **候选 fallback（KV 保留 + mamba 最近 checkpoint + tail recompute）**：last_valid_boundary =
  `2048*floor(P/2048)`，recompute = P − last_valid_boundary = within-node offset，平均 **~1023 tokens**。
  - per-request 标称 context 下：32K 平均 96.9%、64K 98.4%、128K 99.2% —— 都 ≥95%。
  - session-aggregate 下 recompute_overhead：32K 2.76%、64K 2.23%、128K 1.02% —— **全部 ≤5%**。
  - 最差单请求 tail=2047（刚过边界停住）→ 32K 单请求最差 ratio 93.75%，略低于 95%，但这是单请求
    极端，不是 aggregate；且真实 prefix 通常比标称 context 低（turn 停在中途，前缀即该 turn 的
    P），用实际 prefix 作分母时最差 88.9%（P 很小时）但平均值 96.9%+。
  - 早期 turn（P<2048，仍在第一个 node 内）没有节点 checkpoint → fallback 退化为 full 重算；
    48000 个 turn 样本中占 2.0%，贡献的平均 overhead 有限（在 aggregate 中已被稀释）。
    对 agent workload（多个长会话、每个会话动辄数十 turn 累积到 32K+）这个比例更低。

**结论（量化）**：node-level Mamba 下 partial miss 的 recompute overhead 在 1.0%–2.8% 量级
（aggregate，32K/64K/128K 全 ≤5%），**在用户目标（effective_cache_ratio ≥95%）下 node-level
足够**，不需要 checkpoint abstraction。

**临界点提示**：如果 context 更小（~8K，且 prefix 常停在 node 内），tail 占 prefix 比例上升；
但 8K 语境下 turn 累积到匹配 ~4×2048=8192 需要多次 turn，早期 turn 的局部损失被后续长前缀稀释。
若未来 context 降到 ~4K（<2 个 node），fallback 的临界形态在 checkpoint abstraction 和
node-level 之间需要重新评估——但 agent workload（既定 32K/64K/128K）不属于该区间。

### 3.3 source-check：restore 路径上 boundary=0 / full miss 之后的现成 recompute/fallback

**写侧 mamba key**：`mamba_component.py:752-763` BACKUP_STORAGE 分支
`keys=[node.hash_value[-1]]`（写节点最后一项 KV page hash），`hit_policy=TRAILING_PAGES`。
即 mamba state 在一个节点上只 checkpoint 一次，位置 = 节点末尾。

**读侧 TRAILING 扫描**：`extent_file_backend.py:618-673` `batch_exists_v2`
- `kv_pages` 为从 0 开始连续 present 的 KV 页数（`_storage_key = key + config_suffix`）。
- 对每个 `pool_transfer`：`ALL_PAGES`（含 key 非占位）做逐页 component 连续 present 扫描；
  `TRAILING_PAGES`（mamba/SWA PREFETCH 侧车）做窗口扫描 `keys[max(0,prefix_len-trailing):prefix_len]`，
  找最大的连续窗口全 present 的 `boundary`；再 `final_pages = min(final_pages, boundary)`。
- `trailing = len(transfer.keys) or 1`。mamba PREFETCH 侧车 keys 是 `["__placeholder__"]`
  （`mamba_component.py:771`），`_sync_trailing_keys`（`hybrid_cache_controller.py:834-852`）
  prefetch 之后回填为 `all_hashes[kv_hit_pages-1:kv_hit_pages]`（命中区间最后 1 页 hash）。
- 因此 read 侧窗口 = "命中范围内最后一页"，与写侧 "节点最后一项"（node tail）只在 **精确整节点
  命中**时相交；partial 命中（Case B）窗口末页 < node 末页，mamba boundary=0。

**all-or-nothing 丢弃 + boundary=0**：`unified_radix_cache.py:2872-2965` `_check_hybrid_prefetch_result`
（行 2917-2921 判定，行 2921-2964 丢弃）：
- `pool_transfers` = 所有非 KV 的 extra pool（mamba/SWA）。
- `all_succeeded = completed_tokens == expected_tokens and all(count == len(transfer.keys) …)`。
- 若 `pool_transfers and not all_succeeded` → `keep_pages = completed_tokens // page_size`，
  且对 shortfall 的 transfer `keep_pages = min(keep_pages, max(0, len(hash_value)-len(transfer.keys)))`
  （对 1-key mamba = len-1）；然后 `storage_existence_cache.invalidate_beyond(KV, hash_value, keep_pages)`
  （`buffer_mode/storage_existence_cache.py:78-86`：丢弃 `hashes[keep_pages:]` 的 belief）。
- 最终 `prefetch_loaded_tokens_by_reqid=0`，返回 **False（prefetch 被丢弃）** → 调用方把该
  prefetch 当 finished 处理，不 restore，并记 P2A `restore_state`/`restore_recompute`。

**storage_hit=0 时的 revoke + ADMIT_RECOMPUTE（scheduler 消费点）**：
- `unified_radix_cache.py:3480-3494`：`operation.storage_hit_count < prefetch_threshold` →
  `_account_prefetch_outcome(operation, revoked=True)` → `_storage_prefetch_missed_rids.add(req_id)` →
  `revoke_pending_prefetch(req_id)`；`_t38c_log` outcome 记 `revoked_full_miss`（hit=0）或
  `revoked_insufficient`（hit>0 但 < threshold）。
- `revoke_pending_prefetch`（`unified_radix_cache.py:3264`）`record_storage_prefetch_terminal(req_id,"revoked_miss")`。
- scheduler `_feed_restore_terminal`（`scheduler.py:3184-3247`）：outcome=="revoked_miss" →
  `RestoreEvent.REVOKED_MISS, genuine_miss=True` → `_apply_restore_event` → `next_restore`（
  `hicache_restore.py:131-137`）返回 `RestoreState.NONE, RestoreDecision.ADMIT_RECOMPUTE`。
- `_apply_restore_event`（`scheduler.py:3274-3318`）写 `req.hicache_restore_state=NONE`；
  `_feed_restore_terminal` 末尾 `if event is RestoreEvent.REVOKED_MISS: _log_restore_recompute(req,"miss")`
  （`scheduler.py:3240-3241`）。
- **释放释放语义**：decision=ADMIT_RECOMPUTE 只是清状态（state=NONE），请求作为普通 req 继续
  （重算）。GENUINE miss 从 `wait_reason_for`（`hicache_restore.py:191-192`）明确不进 WAIT_CAPACITY——
  "true L3 miss is terminal (ADMIT_RECOMPUTE)"（`hicache_restore.py:11`）。即**当前实现没有为
  partial-hit 提供 segment 级 fallback**：`storage_hit_count` 是折叠后的 usable cut，一旦 < threshold
  全丢，recompute 覆盖整个前缀。fallback（KV 保留 + 最近 mamba checkpoint + tail recompute）在
  现代码中不存在，是需要新增的候选路径（不确定 checkpoint abstraction 是否需要）。

**现成的 recompute/fallback 机制（SGLang 层）**：
- `scheduler.py` 的 `_prefetch_kvcache` 是唯一 restore 入口；decision=ADMIT_RECOMPUTE 后不再
  prefetch，请求回正常 prefill 路径 = 现成的 recompute。
- 没有 segment/partial restore：`_decide_prefetch_result` 只折叠出一个 usable cut（client 层
  `usable`）+ 全丢或全拿；`keep_pages` 截断的 belief 是为了 next FULL check 重写，不是 partial
  restore。
- Ready Horizon 负缓存 `_ready_horizon_negatives`（`scheduler.py:3204-3222`, `NO_L3` entry）阻止
  miss 请求下 pass 立即重试，但也是"等 durable/publish 推进"，不是 partial fallback。

**回答"KV prefix 是否也一起被丢弃"**：在 all-or-nothing 丢弃路径（Case B 语义）里，**KV 层物理页
并没有被 erase**——`invalidate_beyond(keep_pages=2047)` 只是丢弃 storage_existence_cache 里
`hashes[2047:]` 的 belief（对 2048 节点 query 保留 0..2046 的 belief；对 Case B 的 1892 查询全部
可 present）。真正的效应是 **usable 折叠为 0**（`final_pages=0`），host/device 侧的 KV/bounce 不
作为 restore 采用。所以"KV prefix 被丢弃"是**逻辑语义**层面：partial query 在 restore 时 KV 无法
被采用（bounce 全部 drop），prefetch 预算释放，后续若同前缀再次全量查询，需要重新从 L3 读或重算。
物理页在 L3 extent 里仍在（除非 eviction），但没有 partial-restore 消费它们——下一次只能 FULL
（4080）或全 miss 重算。

### 3.4 视图归因（补充）

量化在 3.2 中对用户目标（effective_cache_ratio=1−recompute/context ≥95%）用三种分母做了
cross-check：标称 context（用户裁决的 32K/64K/128K）、实际当前 prefix、session-aggregate
（总 tail/总 token）。三者 node-level fallback 均 ≥95%（aggregate 1.0–2.8% recompute），
most-worst per-request（32K 名义）93.75% 略 <95% 是单请求极端（prefix 刚过边界即停）。

## 4. summary

- **行为证据（harness 四 case）**：
  - Case A（exact 2048 node boundary）：usable=2048 全量 restore OK。
  - Case A'（split-node exact 9 页）：usable=9，mamba present at [2,8]（双节点尾 checkpoint 对齐）——
    multi-node 精确到边界可 restore。
  - Case B（partial 1892，2048 node 内）：usable=0，mamba boundary=0，all-or-nothing 全丢；
    底层 KV raw present 1892（`extra={'kv':1892}`）但折叠后 0。
  - Case C（KV-only 同 1892）：usable=1892，KV 层单独健康。
- **restore-policy 代码路径**：mamba 写 key=`node.hash_value[-1]`（node 尾）；读侧 TRAILING 窗口
  = 命中最后一页；partial 命中永远取不到 node 尾 key → boundary=0 → all-or-nothing 丢弃
  （unified_radix_cache.py:2921-2964, final_pages=0）→ revoked_full_miss → T9 genuine →
  ADMIT_RECOMPUTE（scheduler.py:3196-3197, hicache_restore.py:131-137）→ 整个 prefix recompute。
  **现代码没有 segment/partial fallback**；`keep_pages` belief 截断为了下轮 FULL 重写，不消费
  partial KV。
- **结论（量化数值）**：node-level Mamba 下 partial miss 的 recompute overhead：
  - 当前 all-or-nothing：session-aggregate **100%**（每 partial 请求等效 cold miss）。
  - 候选 fallback（KV 保留 + 最近 node-tail checkpoint + tail recompute）：平均 tail ~1023 tokens，
    session-aggregate recompute 32K/64K/128K = **2.76% / 2.23% / 1.02%**，全部 ≤5% → **node-level
    Mamba 足够，不需要 checkpoint abstraction**。90% 的 turn tail≤1839，tail 上限=1 个 node（2048）。

## 5. followups

1. **mamba key 位置错位是根因级设计问题**（写 node 尾 vs 读命中窗口末页，读侧永远取不到）——
   `mamba_component.py:760` vs `extent_file_backend.py:661-669` vs `hybrid_cache_controller.py:852`。
   这是 e7o 已定性、本次 harness Case B 再次证实的点；建议 coder 侧裁决 key 约定（链尾对齐）。
2. **fallback 路径（KV 保留 + tail recompute）不存在**——现代码对 partial miss 直接
   ADMIT_RECOMPUTE 全 prefix。若要达到用户目标（≥95%），需要在 (a) all-or-nothing（现状）
   与 (b) 新增 segment fallback 之间选择；(b) 是满足目标的候选，且 node-level 即可（≤5% recompute）。
3. **临界 context**：若未来 context 降到 ~4K（<2 node），node-level fallback 的早期 turn 损失占比
   上升，需重新评估 checkpoint abstraction 阈值；当前 agent workload（32K/64K/128K）不涉及。
4. **早期 turn（P<2048）无 checkpoint**：48000 samples 中占 2%；影响 aggregate 但已在量化中计入，
   后续若做 fallback 可给首 node 特殊处理（首个节点也写一个 checkpoint）。

## 6. open_issues

- 本次 harness 是 backend 级（extent backend + batch_exists/_v2）确定性验证；调度级 restore
  （`_prefetch_kvcache` + `ADMIT_RECOMPUTE` + Ready Horizon 负缓存）仍是 e7o 的 12G M4T 实测量测
  （storage_hit=0，396/396 revoked_full_miss）。本 verdict 确认的是"后端合约行为 + 语义路径"，
  未重跑调度级 M4T（内存约束，且非本任务范围）。
- 物理 KV 页在 L3 中仍在（除非 eviction），但 partial-restore 不消费它们；后续若启用 segment
  fallback，`storage_existence_cache.invalidate_beyond` 与 `keep_pages` 语义需与 fallback 对齐。
- metrics 相关代码（`observability/metrics_collector.py` 等）本次只读未改；3090-dev/ 仅新增
  `p2io_e7p_recompute_quant.py`（纯算术）。