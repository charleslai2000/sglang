# Ready Horizon (RH) 使 L3 restore 全灭 — 机制缺陷代码级定位（Bug 报告，可转交外部专家）

## status
done

## artifacts
- 本报告：/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-rhono-bug-architect-e1.md
- 本地权威源码（唯一真相源，远程 175.155.64.171 引擎与本同步，git HEAD = 202a37eba4 "freeze 3090-24g-hicache stable baseline (2026-09-04)"）：
  - `python/sglang/srt/managers/scheduler_components/ready_horizon.py`（537 行）
  - `python/sglang/srt/managers/scheduler.py`（6377 行）
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`（restore/prefetch/revoke 链）
  - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` + `extent_allocator.py`（L3 extent 后端）
  - `python/sglang/srt/managers/cache_controller.py`
- 远程日志证据：`/root/engine-gate3-rhon.log`（92MB，仅经 `ssh -p 24052 root@175.155.64.171` 行级抽样，未整读）
- 本地封存的运行证据：`.memory/phase2-hicache-design/work/gate3-rhon-evidence/rhon-evidence.tar.gz`（runs.csv / mid-run-metrics / verdict.json）

## 现象（含远程日志关键行，行级引用）

Gate-3 Run B（RH ON，20260904-211848，8 agents，7268s，2127 reqs）远程引擎日志，restore 全灭、写侧照常、GC 反高：

- `evt=prefetch_issued` **9305** 次；`evt=prefetch_revoke` **9302** 次；`evt=prefetch_finalize` **3** 次；`evt=restore_success` **2** 次（对比 Run A RH OFF restore_success=852）。
- 首个请求 21:18:49 即全灭（非渐进），全部 `revoked:miss`、disposition=RECOMPUTE：

```
[2026-09-04 21:18:49] [P2A] ts_ms=1788527929863 evt=prefetch_revoke rid=78be5f... terminated=False storage_hit=0 requested=20910 miss_reason=miss storage_generation=0
[2026-09-04 21:18:49] [P2A] ts_ms=1788527929854 evt=prefetch_issued  rid=78be5f... prefetch_length=20910
```

- `storage_hit=0` **在全部 9302 次 revoke 中恒为 0**（`grep -avE 'storage_hit=0 '` = 空），且 `storage_generation`（实为 l3_publish_epoch）随时间 0 → 4456 单调上涨，issued→revoke 间隔最高 477ms —— **不是同毫秒竞争，是系统性 0-hit**。
- `terminated=False` 于全部 revoke（`grep -acF 'terminated=True'` = 0）。
- 写侧照常：`evt=extent_write` **37135** 次（kv=24564, mamba=12571）；GC 反高 5.7×：`evt=extent_recycle` **36984** vs 6454。
- `[P3] evt=ready_stage result=issued state=RESTORING` **1407** 次、`result=declined` 106 次 → RH 系统性把 frontier 请求判为"应 speculative stage"，全落入 RESTORING → 首请求即 REVOKED_MISS。
- 聚合 hit 0.6672 vs 0.7845；L0 exact restore 0.79 vs 0.86；GPU 97.6% 未改善。
- extent 后端配置：`extent=67108864 B slots=1430 max_size=64000000000 min_free=10000000000`（文件≈91.6GB，64GB 上限，eviction_ratio=0.9 → 57.6GB 触发）。mamba 单 key 写 51.5MB（`component=mamba keys_n=1 bytes=51510288`）。

## 源码定位（文件:行 + 最小代码段 + 机制解释）

### 1) 关键路径术语消歧（决定后续理解）

- `evt=prefetch_revoke` 的 `storage_hit` 字段 = `operation.storage_hit_count`（unified_radix_cache.py:3310）。
- `storage_generation` 字段 = `self.tree_core.l3_publish_epoch()`（unified_radix_cache.py:3313），≠ 任何写计数。它在整个 Run B 单调涨到 4456，说明写侧（write ack / restore read-back 触发 `_bump_l3_publish`，unified_tree_core.py:2119-2125）**确实在持续 publish**——「L3 有数据」与「restore 全 miss」必须同时成立的证据。

### 2) restore 全灭的直接代码断点：extent 后端 `batch_exists` 良性返回 0

`storage_hit_count` 只由 `prefetch_thread_func` 填充（cache_controller.py:1344，见下），其值直接来自 extent 后端 `batch_exists`：

```python
# cache_controller.py:1291-1314
def _storage_hit_query(self, operation):
    ...
    for start in range(0, len(page_hashes), STORAGE_BATCH_SIZE):
        hit_page_num = self.storage_backend.batch_exists(batch_hashes, extra_info)
        hash_value.extend(batch_hashes[:hit_page_num])
        storage_query_count += hit_page_num * self.page_size
        if hit_page_num < len(batch_hashes):
            break
    return hash_value, storage_query_count
```

```python
# extent_file_backend.py:392-399
def batch_exists(self, keys, extra_info=None):
    with self._lock:
        for i, key in enumerate(keys):
            if self._allocator.lookup(self._storage_key(key)) is None:
                return i
        return len(keys)
```

`_allocator.lookup`（extent_allocator.py:76-85）在**该 key 已不在 index 或 generation 不匹配**时返回 None：

```python
def lookup(self, key):
    ref = self._index.get(key)
    if ref is None:
        return None
    if ref.generation != self._generations[ref.extent_id]:
        self._index.pop(key, None)   # slot 被复用 → 该 entry 视为缺失
        self._recency.pop(key, None)
        return None
    return ref
```

### 3) 为什么 key 丢失：circular extent allocator + 同步写路径 LRU GC（write<->restore 竞争）

extent 后端是**循环 slot 分配器 + 写路径同步水位 GC**，无后台 evict daemon。每次写批量都先 `_gc_evict()`（同步、部分持有 `_lock`），超 57.6GB 水位即 LRU 逐 slot：

```python
# extent_file_backend.py:826-859（_write_pages）与 863-887（_gc_evict）
def _write_pages(self, keys, values):
    with self._lock:
        self._gc_evict()                      # 瞬时写路径，同步逐 LRU slots
        refs, passed = self._allocator.plan(...)
        ...
        self._allocator.commit(keys, refs, passed)
def _gc_evict(self):
    while True:
        pressure = (self._max_size_bytes > 0 and self._allocator.used_bytes
                    > int(self._max_size_bytes * self._eviction_ratio))   # 0.9
        ...
        if self._allocator.evict_slot_lru() == 0:
            return
```

```python
# extent_allocator.py:174-218（LRU slot drop → generation bump → 旧 index 判缺失）
def evict_slot_lru(self):
    oldest_key = next(iter(self._recency))
    ...
    return self._drop_slot(oldest.extent_id)
def _drop_slot(self, slot):
    ...
    self._generations[slot] += 1              # 复用/逐出 → generation bump
    logger.info("[P3] ts_ms=%d evt=extent_recycle slot=%d generation=%d freed=%d", ...)
```

**机制**：mamba 单 key 51.5MB、KV 页每个 extent 64MB，8-agent 12-turn 负载的写 burst（37135 extent_write）把 64GB / 1430 slot 的水位瞬时顶破 → `_gc_evict` 同步逐出 LRU slots（36984 extent_recycle，freed 从 50~67MB/slot）→ 对应 key 的 `_generations[slot]++` → 之后任何 `batch_exists/lookup` 对**已被覆盖的 slot 上的 key** 判缺失。restore 是**下一轮**（prefetch pending 跨 pass）才查询 L3，此时该 key 十有八九已被环写覆盖 → storage_hit=0 → `revoked:miss → RECOMPUTE`。这解释了 GC 反高 5.7×、extent_write≈extent_recycle、写侧照常而 restore 全灭。

这是**后端容量/替换策略与 restore 工作负载并存时的容量性 miss**，不依赖 RH 路径中的任何日志或 admission 抢占——RH 开启只是把「此刻该 rid 值不值得 restore/等」的调度全量放到了这个已被写 churn 掏空的 L3 上。

### 4) RH 调度层路径（为何每个 frontier rid 都被按 READY 潜质 stage → 首请求即 revoke）

- RH pass 在每 prefill pass 运行 `_ready_horizon_pass`（scheduler.py:3320-3425）。候选集合 `staging_candidates`（ready_horizon.py:345-369）只接受 `_state_funnel`（ready_horizon.py:327-343）：NONE且有 potential，或 WAIT[PREFETCH_BUDGET]/WAIT[DEVICE_QUOTA]+host_hit=0。
- 对每个 `plan.to_issue`：`self._prefetch_kvcache(req)`（scheduler.py:3383），`issued = state is RestoreState.RESTORING`（3384-3385），日志 `result=issued state=RESTORING`（1407 次）。
- `_prefetch_kvcache`（scheduler.py:2943-3012）调 `prefetch_from_storage`（unified_radix_cache.py:2467+），其对 `demand_restore` 只在 rate-limit 判定（`_prefetch_budget_denied`，unified_radix_cache.py:2445-2459）与 M5 分类（`reserve_prefetch` DEMAND/SPECULATIVE）中用。**RH stage 默认 demand_restore=False → SPECULATIVE**。
- 与 Run A（RH OFF）的差异点：**不是 demand_restore**（Run A 的 `_add_request_to_queue`→`_prefetch_kvcache(req)` 同样 demand_restore=False，却 852 success）；**不是 admission 抢占 restore**（RH pass 不减恢复优先级；`partition_ready_first` 只在 `can_run_list` 之前重排，M4）。差异是：(a) RH 把 speculative stage 前置到 admission、成批次、8-agent 负载下持续发起；(b) 连带 inflight_speculative 预算与流水占用，使写侧正常、L3 查询照跑但命中为 0。**根因在 L3 后端容量/GC，不在 RH 的调度判定**；RH 只是把全灭的病灶暴露得彻底（每一轮都把每个 frontier rid 按 READY 潜质 re-issue）。

### 5) revoke 记录为 `revoked:miss` 且 `terminated=False` 的路径确认

9302 次 revoke 的 `terminated=False` 排除 `check_prefetch_progress` 立即路径（unified_radix_cache.py:2725 先 `terminate_prefetch`→revoke，会 terminated=True）与 abort 路径（3163 同）。剩唯一通道 = **异步 hit 查询完成后的 drain 路径** `_drain_and_alloc_storage_hit`（unified_radix_cache.py:3460-3519）：`storage_hit_count < prefetch_threshold`（覆盖 storage_hit=0）→ `revoke_pending_prefetch`（3494）不置 terminate → `terminated=False, miss_reason=miss`。这反过来**证明** hit 查询确实跑完且 backend 确实返回 0（而非查询未达）——与第 3 节结论一致（backend 良性 0-hit）。

```python
# unified_radix_cache.py:3480-3494
if operation.storage_hit_count < self.prefetch_threshold:
    self._account_prefetch_outcome(operation, revoked=True)
    ...
    self._storage_prefetch_missed_rids.add(req_id)
    self.revoke_pending_prefetch(req_id)     # → storage_hit=0, miss_reason=miss, terminated=False
    continue
```

```python
# unified_radix_cache.py:3298-3299（revoke reason 分支）
elif operation.storage_hit_count == 0:
    revoke_reason = "miss"
```

## 候选根因（按可能性排序，每个带代码证据）

### C1（最可能，code-confirmed + log-confirmed）：extent 后端环写 / LRU 水位 GC 在 restore 前覆盖 L3 KV → storage_hit 恒 0
- 证据：extent_write 37135 ≈ extent_recycle 36984（log）；allocator 环写复用逐 slot + generation bump 判缺失（allocator.py:76-85, 174-218）；`_gc_evict` 写路径同步（extent_file_backend.py:837, 863-887）；`_drain...3494` revoke terminated=False；storage_generation→4456 证明 L3 持续 publish（数据写过）而读不到。**伪代码推测（hypothesis）**：mamba 单 key 51.5MB 相对 extent 64MB 的填充效率（约 80%），8-agent 写 burst 使 57.6GB 水位被瞬时顶破后 LRU 循环覆盖；KV 页本身也可能逐出。此根因与「GC 反高 5.7×」「storage_hit 恒 0 且随写 churn 维持」「写侧正常」完全自洽。

### C2（较可能，需复现确认）：RH 的 speculative 前置 staging 加剧写 churn，把 L3 从「可恢复」推向「已被环覆盖」
- 证据：RH 每 pass 对 frontier 批量 `_prefetch_kvcache`（scheduler.py:3381-3415），1407 次 ready_stage issued=RESTORING；speculative 预算（`inflight_speculative_tokens`）与 M1/M2 只是 host 池闸，未约束 L3 backend 容量。RH OFF 时 restore 直接走 admission 前单次 `_add_request_to_queue`，写/读节奏不同。**这是 C1 的放大器而非独立根因**——若 C1 成立，RH 只是把全灭暴露得更彻底。

### C3（code-confirmed 但为必要前置，非本体）：revoked_miss 后 RH 把 rid 永久 NO_L3 负缓存，杜绝了后续自愈探测
- 证据：scheduler.py:3199-3221，REVOKED_MISS + RH 开启 → `_ready_horizon_negatives[rid] = NegativeCacheEntry(NO_L3, ...)`；NO_L3 只订阅 `l3_publish` 上涨（ready_horizon.py:296-299）。由于 4456 次 generation advance 全部是被环覆盖的写，负缓存虽会在每轮 l3_publish 上涨时解除，但解除后 re-probe 依然命中已被覆盖的 slot → **负缓存机制在容量性 miss 下退化为空转**（每次解除都再撞一次 0-hit）。这是「mapping 为什么看起来永久 park」的表象，不是全灭的首因。

## 证据强度分层

- **code-confirmed**：extent 后端 lookup/generation/GC 判缺失逻辑（allocator.py:76-85, 174-218）；`_write_pages` 写路径同步 `_gc_evict`（extent_file_backend.py:837, 863-887）；drain 路径 revoked terminated=False（unified_radix_cache.py:3480-3494, 3298-3299）；RH stage→RESTORING（scheduler.py:3381-3385）；revoked 后 NO_L3 负缓存（scheduler.py:3199-3221）。
- **log-confirmed**：extent_write=37135 / extent_recycle=36984（log）；storage_hit=0 共 9302 全量、storage_generation 0→4456、issued→revoke 间隔最高 477ms（非竞争）；terminated=False 全量；restore_success=2 均早于首次大规模 recycle burst（21:20:04）；「21:19:00-21:20:30 窗口 recycle=259/min vs write=60/min」反向证明写 burst 先撑破水位、recycle 随后成批发生。
- **hypothesis**（需外部专家对 extent 文件/复现确认）：C1 的精确因果「某 key 的 slot 恰在 restore 查询前被 cycle 覆盖」的逐-key 对应；extent 文件实际物理占用率是否达 57.6GB 水位。

## 最可能的修复方向（代码级建议，非实现）

按「先证明再动」：候选方向按影响从小到大。

1. **不带宽/替换坏的错，先加可观测**：extent 后端 `batch_exists` 判定缺失时应区分「key 从未写过」 vs 「index 有但 generation 已 bump（slot 被复用）」——后者计入单独的 `stale_slot_miss` 计数并落一条 `evt=extent_recycle_hit` 日志。当前 `evt=extent_recycle` 只统计写路径 slot 复用，**没有把「复用导致后续读 miss」显式归因**。这是把 C1 从 hypothesis 升到 code-confirmed 的第一步。
2. **capacity 参数上修或替换语义**：`max_size` / `eviction_ratio` / `extent_size` 在当前 load shape 下把 L3 当作「随身写缓存」而非 durable KV。修复方向是在 restore 工作集与 write 工作集间做隔离（分池/分文件/按 pool 单独水位），或对 KV 页与 mamba 大页分别设 extent_size（mamba 51.5MB/key 与 KV 页同一 64MB extent 混排导致填充率崩塌）。
3. **RH 与容量弯的交互**：NO_L3 负缓存（C3）在容量性 miss 下退化为空转——修复方向是让负缓存携带「这是 writing-churn 造成的容量性 miss」语义（例如订阅 host/write 侧 epoch 而非仅 l3_publish），或对持续 recycle 的 rid 延长 park，避免 4456 轮空转放大写 churn。
4. **不首选**：任何「RH 不要 stage」或「跳过 budget」类的界面打补丁——那是 bypass，不是根因（见任务红线：先证明再动）。

## 给外部专家的关键技术上下文

**RH 设计意图 vs 实际路径（快速理解）**：
- Ready Horizon 的**意图**（ready_horizon.py 头注释）：M6 严格 READY 池（READY && 物理驻留全前缀）、M4 READY-first admission、M3 因果负缓存防 spinning、M2 无驱逐 staging。它是一个**host 池维护策略**，本身不改变 L3 后端语义；它决定「哪个 rid 值得现在从 L3 拉」，但**不保证 L3 里还有该 rid**。
- **实际断链点**：本 run 的 L3 后端（P2-IO extent，202609-04 baseline）是环写 + 写路径 LRU GC，容量 64GB 被 8-agent 12-turn 写 burst 实时掏空。RH 把「值得拉的 frontier 请求」大量前置到 admission 前（1407 次 RESTORING），每次命中已经 0-hit 的 slot → 全灭。**日志语言**：`storage_hit`（revoke）读的是 extent backend `batch_exists` 的命中数；`storage_generation` 是 l3_publish_epoch（写/证实事件计数），它上涨说明数据被写在但读不到；`terminated=False` 证明冷走 drain（查询跑完、backend 真返回 0），不是竞争性提前 revoke。三者合起来把「RH 抢占 restore」「query 未达」「同毫秒 revoke」三条直觉假设全部排除，指向唯一自洽根因：**后端容量/替换把 L3 在 restore 前覆盖掉**。
- 复现维度：8-agent、12-turn、mamba 大页（51.5MB/key）、64GB L3 容量、eviction_ratio 0.9、extent 64MB。要隔断变量，最小实验是**仅关 RH（demand_restore 语义下）把容量从 64GB 提到 96GB 观 GC 是否下降**——但 Run A/B 不可重跑，需专家在可控复现里做。

## followups
1. （external expert，决定性）在可控复现上把 `evt=extent_recycle` 与随后的同-key `storage_hit=0` 逐 key 对齐，确认 slot 复用确实命中 restore 目标 key。
2. 补 extent backend 观测：区分从未写 vs slot 复用（见修复方向 1）。
3. 验证 mamba 大页（51.5MB）与 KV 页混排对 64MB extent 填充率的量化影响。

## open_issues
- `_t38c_log` gated on `/tmp/t38c-on`（unified_radix_cache.py:145-156），本 run 未开，故 engine log 无 pc_outcome/drain 明细；结论依赖 `prefetch_revoke`/`restore_disposition` 行级证据 + 源码路径推理，drain 路径归属为 code-confirmed + 排除法，非 t38c 直接证据。
- `extent_write` 与 `extent_recycle` 的 slot 对应只能在具备 `/data/l3/p2io-gate3-rhon/` extent 文件的复现/远程机上做，本分析未读 extent 文件本体（只读日志）。
- 远程 92MB 日志按行级 grep 抽样；未逐行遍历，计数均为 grep -ac 全量。