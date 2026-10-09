# p2io-tester-e7d — L3 state survivability 审计（chain lifecycle，run-20260901-115548 纯日志）

## status
done — **NEVER_BACKED（96% 的 recompute rid）主导；机制 = host 内存压力下 write-back 子树无备份丢弃（Z3），非 extent recycle / key 不可达**。现有日志足以定案主因，但"未写 vs 写过再丢"的百分比需补埋点才能细分。

## artifacts
- 数据源：`/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（run-20260901-115548）+ e5/e7 引擎日志对照
- 事件代码溯源：`unified_radix_cache.py:905-935`（write_back Z3 drop 发射点）、`extent_allocator.py`（ring recycle 无日志）、`extent_file_backend.py`（仅创建/清理日志）
- 注意：Ready Horizon [P3] 埋点（ready_pool/ready_stage）受新增持久约束保护——本分析未删改任何埋点；**补埋点清单全部为新增事件/追加字段，向后兼容**（已遵守约束）

## evidence

### Step 1：字段摸底表
| 想重建的字段 | 可见性 | 证据 |
|---|---|---|
| requested_frontier（prefetch_issued.length） | ✅ 可重建 | `prefetch_issued rid=X prefetch_length=N`（481 次） |
| backup_scheduled/acked_frontier | ❌ 缺 | **无任何 backup_* / persist_acked P2A 事件**（事件清单 20 类无 backup） |
| HOST 移除 l3_durable_frontier + removal_reason | ❌ 缺 | 移除事件仅 `hollow_evict node=N freed=N`、`forced_drop_to_miss node=N freed=N`（无 frontier/reason） |
| storage_hit_frontier | ✅ 可重建 | `prefetch_revoke ... storage_hit=N requested=N` |
| miss_reason / generation | ❌ 缺 | revoke 行只有 storage_hit/requested，无 miss_reason、无 generation |
| Z3 dropped-without-backup | ✅ 可重建 | **引擎行（非 P2A）** `write_back: KV subtree dropped without backup due to host memory pressure, root node N`（59 次） |
| extent recycle / generation 失效 | ❌ 缺 | `extent_allocator.py:201 _generations[slot]+=1` 递增但**零日志发射**；backend 仅创建/清理日志 |

### Step 2：78 个 recompute rid 分类
```
NEVER_BACKED (storage_hit==0):           75  (96.2%)
PARTIAL_BACKED (0<hit<requested):         1
FULL_THEN_LOST (hit>=requested):          2
FULL_PRESENT_NOT_MATCHED:                 0
```
- NEVER rids 请求长度 p50=13484 / p90=34812 / max=43513；其中 **26 个请求 ≥20910（整链）**
- 结论：recompute 几乎全部是"L3 压根没有这些链的数据"，不是"有数据但查不到"（FULL_PRESENT_NOT_MATCHED=0 排除 key/sidecar/lookup correctness），也不是"曾完整后被 Y 清除"（FULL_THEN_LOST 仅 2）

### Step 3：三嫌疑
1. **Z3 / dropped-without-backup：主嫌疑成立**。59 次 drop（59 个 distinct root node，序贯 840-859/1024-1026 等批量），全在 11:56-12:04（steady/drain，8-agent 宿主压高峰）。e7b=59 vs e5=29 vs e7=54——本轮 write-back 损失是 e5 的 2×。源码：`unified_radix_cache.py:920-928`——`_evict_device_leaf` 时 D→H backup `written==0`（宿主满）→ `_drop_subtree_no_host` 成功 → **整链无备份丢弃**。这是 NEVER_BACKED 的确定性机制（drop 的是含长链前缀的子树）。
2. **extent ring recycle / generation 失效：不可见**。allocator 有 generation 递增但**无事件**；无法从日志确认 recycle 是否覆盖了已写长链。代码路径存在（slot 复用失效），但本轮 NEVER=75 已由 Z3 主导解释，recycle 最多是次要，需埋点确认。
3. **write-back Host eviction vs L3 frontier 时序：部分可重建，结论指向 host 先满**。`promotion_transfer/reserve` 显示 `full_free` 常 <2000（如 11:56:24 full_free=1760）而 `full_evictable=39640`——宿主池长期接近满，D→H backup 频繁失败，随即 Z3 drop。

### Step 4：survivability KPI（当前负载）
```
L3 完整命中率（storage_hit==requested / issued）= 10/93 = 10.8%
路径级 survivability（issued → 达 READY）= 58/93 = 62.4%
L3 断言存活（非 NEVER）= 18/93 = 19.4%（下界：至少 80% 的 issued rid 在查询时 L3 无数据）
recompute 率 = 78/93 = 83.9%
```
**诚实标注**：NEVER_BACKED=75 是"查询时 L3 无数据"的**上界**（storage_hit=0 只证明没查到，不能区分"没写"与"写了但被 recycle/失效"）。Z3 drop=59 提供了直接"没写"证据（整链 drop 不进 L3），但 75-59=16 的差额在现有日志**不可归因**（可能未写/可能写过被 recycle/可能写时 partial）。真实 survivability 在 [19.4%, 62.4%] 区间，**无法精确定点**——低于 95% 目标明确，但距目标多远取决于未可视的写/回收分界。

## summary
**裁决：L3 survivability 严重不达标（当前负载估计 19-62% 区间 << 95% 目标），主因 = host 内存压力导致的 write-back 无备份丢弃（Z3），非 key/查询正确性，非 extent recycle（虽不可见但非首因）。**

证据链闭环：
1. 78 个 recompute rid 中 75 个（96%）NEVER_BACKED（storage_hit=0），只有 0 个 FULL_PRESENT_NOT_MATCHED——排除"写了但查不到"
2. 59 次 Z3 drop（整链无备份丢弃）正是"没写"的直接来源，且 e7b 是 e5 的 2×（29→59），与本轮 full-chain 覆盖崩坏吻合
3. 宿主池长期近满（promotion_transfer 显示 full_free<2000、full_evictable≈40000）→ D→H backup 失败 → 整链 drop
4. 26 个 NEVER rid 是 ≥20910 token 的整链请求——正是 READY 池该服务的 full-chain，全被宿主流失

**与本任务链的关系**：这解释了 e7c"NO_L3_FULL 主导"的根因——不是 READY 池策略问题，是 **L3 里没有完整链是因为 write-back 宿主压 drop**。修复方向在 write-back/宿主 eviction 的 L3 持久化先行，而非 READY 池水位。

## followups — 补埋点清单（全新增，向后兼容，遵守持久约束）
主因已由 Z3 行定案，但"未写 vs 写过再丢"需以下埋点才能精确定量 survivability：

1. **新增事件 `evt=extent_write`**（extent_file_backend.py batch_set_v2 成功处）：字段 `node, component(POOL), keys_n, bytes`——记录每次 L3 写，判断"写过没有"
2. **新增事件 `evt=extent_recycle` / `evt=extent_generation_invalidate`**（extent_allocator.py:201 generation 递增处）：字段 `slot`——记录 ring recycle 覆盖
3. **新增事件 `evt=restore_backup`**（unified_radix_cache.py backup/持久化 ACK 处）：字段 `rid, node, l3_durable_frontier, requested_frontier`——记录"已建立 durable frontier"
4. **`prefetch_revoke` 追加字段** `miss_reason=(never_written|recycled|generation_mismatch|empty)` + `storage_generation`（追加，不替换现有 storage_hit/requested）——区分 miss 类别
5. **`hollow_evict`/`forced_drop` 追加字段** `l3_durable_frontier, removal_reason`（追加）——记录 host 移除时 L3 是否已 durable
6. **`restore_recompute` 追加字段** `final_storage_survivability=(full|partial|none)`（追加）

最小重跑方案：加 1/2/3 三个新事件即可解"未写 vs 写过丢"的 75 分界；4/5/6 用于精确分类。因禁止删除现有埋点，全部为新增事件 + 追加字段，无需改现有格式。

## open_issues
- survivability 精确值（75 NEVER 中 59 确认 Z3 未写 vs 剩 16 更因 recycle/partial）需上述埋点重跑
- 宿主池近满的具体水位阈值（何时触发 write-back 失败）无日志直接可见，需 promotion_transfer 类埋点进一步确认
- extent 64MiB×1024=20G 池相对 96 请求 × 20-43K token 链（约 2-4G/链 × 8 = 宿主 full）——池容量与写入策略的匹配是下一步引擎侧课题
