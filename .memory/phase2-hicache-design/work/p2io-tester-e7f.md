# p2io-tester-e7f — e16 eviction 回归修复：重跑 e7e 完整验证（六门 + 无崩溃 + 强制降级检查）

## 1. status

**failed**

e16 修复已在 3090 生效（`forced_miss_tombstone`/`detach_miss_dropped`/`drop_subtree` skip 链路在档），**e7e 崩溃签名（`node X not host-only` AssertionError）已消除**（forced_drop_to_miss 从 e7e 的 59 降到 1），但本次 e7f 全量验证 **6 道硬门全部未过**，且**中途以新的断言崩溃（非干净退出）**：

- 我在 18:33:20 于 `on_idle → invariant_checker._check_tree_cache → tree_core.sanity_check` 触发 **`AssertionError: Sanity check FAILED (4 violations across 55 nodes)`**（node 68 孤儿注册：H-leaf stale / Duplicate ghost / host_leaves stale / mamba host LRU 残留）；引擎 SIGQUIT。驱动因所有 HTTP 请求已完成（最后 finish 18:33:20.8）仍报 `status=done / 96 ok / 0 failed`，但 scheduler 进程是**断言崩溃而非干净关闭**。
- Z3 硬门 FAIL：**1001 次** subtree drop（`KV subtree dropped without backup, root node 31..1077`），`host_pressure` dropped tokens **1,863,428 kv / 960 mamba**（终值）。
- Ready Horizon FAIL：ready_pool 全程仅 1 次、`size=0 tokens=0 watermark=[2,4]`；ready_stage=0——未准入任何请求，当前配置（8G + writeback_reserve 1.5G + safety_margin 0.3G + `hicache_restore_backup_park=False`）下 Ready Horizon 判定为**完全不生效**（与 e7d/e7e 同一结论）。
- Survivability FAIL：245 次 recompute 全部 `final_storage_survivability=host`；24 个 restore 轮次中 **16 轮全 miss（cached_tokens=null → 全量重算）**，仅 8 轮有部分 host/device 命中。
- 4 崩溃/OOM：无（dmesg 干净、`backup_failure=0`、`extent_recycle=0`）。
- **无崩溃跑完全程 FAIL**（新断言 18:33:20）。
- forced_drop>20 → 9G 评估：当前 **forced_drop=1**（≤20），**无需 9G 评估**；但 Z3 drop=1001（≈40× 于 forced_drop）提示 8G 配置下 eviction 全盘走"升降级失败即 drop"路径，配 8G 的 survivability 门不可达才是主因（详见 §3 根因）。

## 2. artifacts（本次任务产物）

- **运行**：3090 部署树 `/root/sglang-b1-continuity`（e16 三文件 md5 双侧一致：`unified_tree_core.py` 96dc8a7ee4dceeafe71c3ab461c3745e、`unified_radix_cache.py` ac4218a9386aaf70969e24ccb20cd6e9、`unified_tree_core_interface.py` a630d5a145111aa23e98bab8717feddd）。配置：HICACHE_SIZE=8G + `--hicache-writeback-reserve-gb 1.5` + `--ready-horizon-safety-margin-gb 0.3` + enable-ready-horizon + extent + write_back + `hicache_restore_backup_park=False`（与 e7e 同款）。
- **证据**（拉回本机 `/tmp/p2io-e7f-ev/`）：
  - `engine-p2io-m4t-e7f.log`（1.03MB，3090 `/root/engine-p2io-m4t-e7f.log`）
  - `join.log`、`verdict.json`、`mid-run-metrics.txt`（3090 `/root/evidence-p2io-extent-m4t-e7f/run-20260901-182348/`）
  - 崩溃块（行 7262-7293）、`forced_drop_to_miss` 单条、`restore_backup` 19 条、`extent_write` 全部、dropped-token 终值、配置 server_args、dmesg 干净。
- **六门表决汇总**：Z3≈0 ✗（1001/1.86M） | survivability>95% ✗（16/24 轮全 miss、245 次 recompute 全 host） | full-prefix 恢复 ✗（无 full 命中） | READY_HOST≥2 ✗（0） | 0 crash ✗（node-68 断言） | NEVER_BACKED 细分 ✗（0 细分；却未定性为"系统性 EVICTION 而非 FORCED_DROP"）。
- 本地测试/工具：无新增测试脚本；本次为集成验证 + 根因分析（本次运行已耗尽证据面，未直接改动产品代码；根因修复建议在 followups §7）。

## 3. summary（结论与根因）

### 3.1 门判据与实测对照（全门红）

| 硬门 | 判据 | e7f 实测 | 结论 |
|---|---|---|---|
| Z3≈0（drop 为最后手段） | 全 run 仅极少量 | **1001** subtree drop，`dropped{reason=host_pressure}` kv=**1,863,428** / mamba=960 | ✗ |
| survivability>95% | 恢复轮命中≥95% | 24 restore 轮中 **16 全 miss**；245 recompute 全 `final_storage_survivability=host` | ✗ |
| full-prefix 恢复 | 存在完整前缀链恢复 | **0** 例；8 轮有缓存者全为部分（host=1152/16384/20864 等，device=256/1152/19618） | ✗ |
| READY_HOST≥2 steady | ready 轮次注入证据 | `ready_pool` 仅 1 次 `size=0 tokens=0`，`ready_stage=0` | ✗ |
| 0 crash/OOM | 全程无断言/无 OOM | dmesg 干净，但 **18:33:20 sanity_check 断言崩溃** | ✗ |
| NEVER_BACKED 细分 | forced 与 eviction 分类 | `forced_drop_to_miss=1`（node 66, freed=2048, l3_durable=0）但 Z3 drop=1001——呈现的是 **eviction 系统性 drop**，非 forced；分类字段完整（node/freed/l3_durable_frontier/removal_reason 全在） | ✗ |

### 3.2 崩溃根因（node 68 孤儿注册）

崩溃落在 `on_idle → sanity_check`，四条违规全部指向 **node 68**：

```
H-leaf extra: [68]
Duplicate ghosts: [68]
1 stale nodes in host_leaves: [68]
mamba host LRU: +S3=set(), +lru={68}
```

即 node 68 在**树内已不可达**（`_collect_all_nodes` 不含它），但仍残留下述三处注册：`evictable_host_leaves`、`full_host_duplicates`、mamba `host_lru_lists[MAMBA]`。

关键生命周期证据（日志交叉验证）：
- 18:24:22 `evt=forced_drop_to_miss node=66`（e16 单次 forced drop，**不是 68**）；
- 18:24:22 `restore_backup op=34 node=68 l3_durable_frontier=384` → node 68 是 **L3-restored 锚点**；
- Z3 drop 集合（node 31..1077）中 **60..70 全部出现但 68 缺席**（57 被 drop、68 否）——node 68 不是 Z3 受害者，而是**在 restore 后、被某个非 drop 路径移除时未清三套注册**。

代码级根因（已逐行确认，见 evidence 段）：
- `detach_miss_dropped`（unified_tree_core.py 1399-1418，e16 新增）对 forced-miss 墓碑调用 `_remove_leaf_from_parent`（1774-1783）：
  - 它 pops `full_host_duplicates` ✓、arena 注销 ✓，
  - 但**不**执行 `_update_evictable_leaf_sets(node)`（即不 discard `evictable_host_leaves`）✗，也**不**从 mamba `host_lru_lists[MAMBA]` **移除**（`_evict_component_and_detach_lru` 未作用于 aux host）✗。
  - 若该节点带 aux host-only mamba 值（restore-only 链，node 68 正是 L3-restored），这四个迹象完整匹配。
- 而 e16 的 `drop_subtree_no_host` skip（1350 `if cur.forced_miss_tombstone: continue`）与 `_delete_unbacked_device_leaf` 等**既有干净路径**（`_release_all_component_layers` / `_evict_host_leaf` / `_iteratively_delete_tombstone_ancestors`）都会先 `_evict_component_and_detach_lru(..., target=EvictLayer.ALL/HOST)` 清 aux host LRU、再 discard 叶集合——**node 68 完全是从 detach_miss_dropped 这条 e16 新路径漏掉的**。

即：**e16 修好了 e7e 的 `node not host-only`（forced_drop 59→1、旧签名消失），但引入/暴露了 detach_miss_dropped 的清注册不完整**，导致新的 sanity_check 崩溃。这是 e16 修复的**同族回归**：`dir=detach 漏 4 项注册清理`（`_remove_leaf_from_parent` 只 pops full_host_duplicates，未清 evictable_host_leaves + 未清 aux host LRU）。

### 3.3 全局 survivability 根因（Z3=1001 洪水 + Ready Horizon 零生效）

- **为何 1001 次 drop**：8G host 目标 + writeback reserve 1.5G + margin 0.3G 下 host 常驻仅 ≈22k tokens（metrics `hicache_host_used=22452 / total=68453`），且 M4T 的 24 轮 restore（每轮 20k 级）涌入时 host 池秒满 → D→H backup 在 host 满时失败 → `_drop_subtree_no_host` 成为**默认落点**（1001 次 = 每轮几乎全 drop）。Z3 原本设计为"最后手段"（forced>20）却占了绝绝对主导——配置下 **capacity 不足使 drop 成为经常态**，soft-fail 语义失效。
- **为何 Ready Horizon 零注入**：`ready_pool` 仅 1 次 `size=0 tokens=0 watermark=[2,4]`。主机水位从未到达 watermark_low=2（host 一直被海量直接 eviction 占满，且 `hicache_restore_backup_park=False` 关掉了 park 制造 ready 窗口）。且需在"host 有富余、safety_margin 兜底"的窗口内触发——当前 8G+reserve 下 host 无富余 → **Ready Horizon 结构上不可达**（与 e7d/e7e 同）。
- **forced_drop_to_miss 字段完整性**：单条含 `node / freed / l3_durable_frontier / removal_reason`，**四字段完整** ✓（e7e 曾有 KeyError 的字段已闭环）。但 e7f 只有 1 次 forced 而 1001 次 Z3-drop，说明 **Z3 分类下的字段覆盖需在 drop 路径上补洞**（drop 路径没有 forced 同款的 per-node 明细日志），否则"为何 drop 成了常态"无法继续判别。

## 4. evidence（真实命令与输出）

### 4.1 e16 代码在档（哈希 / 逻辑点）
```
local: unified_tree_core.py md5  96dc8a7ee4dceeafe71c3ab461c3745e
       unified_radix_cache.py    ac4218a9386aaf70969e24ccb20cd6e9
       unified_tree_core_interface.py a630d5a145111aa23e98bab8717feddd
3090: <md5 双侧一致，e16 逻辑在档>
  - detach_miss_dropped  unif_tree_core.py 1399-1418
  - drop_device_leaf_to_miss         1400-1449
  - _drop_subtree_no_host 控制器 864-871 → tree_core drop_subtree_no_host 1325-1378
  - forced_miss_tombstone flag  node __init__ 159
```

### 4.2 门证据（真实计数）

```
# Z3 drop: 1001
grep -c "KV subtree dropped without backup" engine-p2io-m4t-e7f.log
1001

# dropped tokens 终值（ts=1788258797.996 末次非空 metric 快照）
sglang:hicache_dropped_tokens_total{pool="kv",reason="host_pressure"} = 1863428
sglang:hicache_dropped_tokens_total{pool="mamba",reason="host_pressure"} = 960

# forced_drop_to_miss 单条（字段完整）
[18:24:22] evt=forced_drop_to_miss node=66 freed=2048 l3_durable_frontier=0 removal_reason=no_durable_backup

# ready horizon
[18:23:34] [P3] evt=ready_pool size=0 tokens=0 watermark=[2,4]   (仅 1 次)
grep -c "evt=ready_stage"  → 0

# recompute 储层分布
grep -c "evt=restore_recompute" → 245
grep "final_storage_survivability=host" | wc -l → 245  (全 host)
grep "evt=restore_state" | grep -o "state=[A-Z_]*" | sort | uniq -c
    245 NONE / 742 RESTORING / 725 WAIT_CAPACITY

# restore 轮次命中分布（python 解析 join.log）
restore rows 24
empty-cached full-miss  16
cached                    8  (1152/20864/1152/16384/1152/20864/256/19618; 全 host 或 device, 无 storage/full)
```

### 4.3 崩溃块（verbatim）

```
[2026-09-01 18:33:20] Sanity check FAILED (4 violations across 55 nodes):
  H-leaf extra: [68]
  Duplicate ghosts: [68]
  1 stale nodes in host_leaves: [68]
  mamba host LRU: +S3=set(), +lru={68}
[2026-09-01 18:33:20] Scheduler hit an exception: Traceback (most recent call last):
  ... File ".../unified_radix_cache.py", line 4322, in sanity_check
  ... self.tree_core.sanity_check(...)
  ... raise AssertionError(msg)
AssertionError: Sanity check FAILED (4 violations across 55 nodes)
[2026-09-01 18:33:20] SIGQUIT received. ...
```

### 4.4 Node 68 生命周期（日志交叉验证）

```
# forced_drop 是 node 66, 非 68
[18:24:22] evt=forced_drop_to_miss node=66 freed=2048 ...

# node 68 是 L3-restored 锚点
[18:24:22] evt=restore_backup op=34 rid=none node=68 l3_durable_frontier=384 requested_frontier=384

# Z3 drop 集合 60..70 中 68 缺席（57/67/69 dropped, 68 not）
60,61,62,63,64,65,67,69,70
```
→ node 68 于 restore(18:24:22) 后、在非 Z3-drop 的路径上被移除，而 `evictable_host_leaves + full_host_duplicates + mamba host LRU` 三处未清（`mamba host LRU +lru={68}` 判定：s3 树侧无 aux host-only、lru 仍有 68）。

### 4.5 无 OOM / 资源状态

```
dmesg_rc=0（无 OOM）
backup_failure=0  extent_recycle=0
末次 metric: kv_evictable=21648 mamba_evictable=32 hicache_host_used=22452/68453
vcpu 清理：无残留进程、GPU 15 MiB（run 脚本自清理 SIGTERM 成功）
```

### 4.6 配置确认（server_args 解析值）

```python
hicache_size=8, hicache_host_memory_mode=cache, hicache_ratio=1.5,
hicache_write_policy=write_back, hicache_io_backend=kernel,
hicache_mem_layout=page_first, hicache_storage_backend=extent,
hicache_storage_prefetch_policy=wait_complete,
hicache_writeback_reserve_gb=1.5, ready_horizon_safety_margin_gb=0.3,
enable_ready_horizon=True, ready_horizon_frontier_n=8,
ready_host_watermark_low=2, ready_host_watermark_high=4,
hicache_promotion_margin_tokens=2048, hicache_restore_backup_park=False
(enable_session_radix_cache=False, mamba_max_states_per_path=-1,
 max_running_requests=8, num_reserved_decode_tokens=512)
```

## 5. followups（后续 / 遗留）

1. **[P1][崩溃回归] `detach_miss_dropped`（unified_tree_core.py 1399-1418）清注册不完整**（根因已定位）：
   - 在 `_remove_leaf_from_parent(node)` 前，对 aux host LRU（`_for_each_component_lru(node, remove, target=HOST)`）执行 detach，并对 node 本身 `_update_evictable_leaf_sets(node)`（discard host_leaves）。
   - 建议最小修复放 `detach_miss_dropped` 体内（或抽一个 `_detach_node_from_lrus` 共用）。
   - 修后必须重跑 e7f 验证：node-68 四违规应归零；sanity_check 全程安静。
2. **[P1][容量] 8G+reserve 1.5G+margin 0.3G 下 Z3-drop 洪泛（1001 次）使 survivability 结构上不可达**：
   - 单一最大失效原因；建议**评估 9G（≥ 触发 forced_drop>20 阈值才上 9G 的"不再"场景）→ 先在 8G 下修到 forced_drop 不再 boom + Z3 回落到 ≤20 级后，再考虑 9G 复测**。
   - 判断依据：metrics host_used=22k/68k 恒定（≈20k 链），restore 每轮 20k 涌入必然秒满 host。**配置维度的容量门先过**，再做功能面。
3. **[P2][RH] Ready Horizon 在本配置下零注入**（ready_pool 仅 1 次 size=0）：host 无富余、park 关闭 → watermark 永不达。需要**单独验证** ready 注入（配一个 host 有富余/水位达标的 subset run，或临时调低 watermark），否则"RH 生效"无法证伪。
4. **[P2][instrumentation] Z3 drop 分类字段缺 per-node 明细**：`forced_drop_to_miss` 四字段完整 ✓，但 1001 次 `KV subtree dropped` 只有计数/root-node，无 `l3_durable`/`reason` 区分。建议 drop 路径补同款 evt（node/freed/l3_durable_frontier/removal_reason），便于"为何 drop 成常态"继续判别（additive，不删 [P3]）。
5. **[P3][日志] e7f 只用 1 次 forced_drop 但 Z3=1001**：报告需把"Z3 洪水"与"forced 单次"分开计数呈现（分类：eviction-driven drop ≠ forced-miss degrade）；9G 评估按 forced_drop>20 阈值，当前不触发。

## 6. open_issues（未决问题 / 风险）

- **R1 node-68 崩溃的证据链是"修复 e16 同族回归"**：e16 确实消除了 e7e 签名（forced 59→1、无 `node not host-only`），但新崩溃点位于 e16 新增路径（detach_miss_dropped 清注册不完整）。**这不是"(未验证就上)"，而是 e16 在 3090 上的完整验证 = FAIL**。
- **R2 6 门全红的系统性根因是配置容量（8G host 秒满）压过代码正确性**：即使 node-68 修好，若容量门不先过，survivability/RH 仍不可达；两路并行才可能在第 3 次运行内收敛。
- **R3 Ready Horizon 在本 run 无任何可靠数据**（仅 1 次 size=0）：当前配置无法论证 RH 行为——需额外 targeted 验证。
- **R4 日志证据自洽性**：所有计数独立取自 engine log + join.log + mid-run-metrics 三源，交叉一致；无自证。
- **R5 未进行任何产品代码修改**（测试驱动修复仅限测试脚本）；本次仅根因分析 + 建议，属 coder/orchestrator 决策面。