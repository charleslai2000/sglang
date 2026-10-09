# p2io-tester-e7l.md — t38c live seed 字节对比（e21 裁决点）

- task: e7l / t38c live seed byte-comparison
- tester epoch 报告；日期 2026-09-02
- 3090: `root@175.155.64.171:24052`；部署 `/root/sglang-b1-continuity`（UnifiedRadixCache live 路径）

## 1. status

**done** — 已完成 M4T-e7l live run、逐 matched rid/span 字节对比、裁决、窄探针与清理。
**裁决：seed 无罪（byte-consistent 成立）→ B 分支（backend key space / allocator lookup 边界）坐实。**

关键数字：
- 写侧 62 个 pc_write_seed 事件，累计 n_pages=97859，全部落入 `evt=extent_write`（97859 kv keys 实际落盘，零丢失、零 refuse、零 extent_recycle）。
- 读侧 395 个 pc_storage_query，**storage_hit_count 全部 = 0，kv_hit_pages 全部 = 0**。
- 5 个 distinct query key-array 的 array[0]（首 key）与某个写链 page0 8-hex 完全一致（matched chain 字节连续），且这些 array 的 anchor seed 与写侧 seed8 完全一致——seed 无罪。
- 其中 node65 案例最硬：write ts=1788325967.794，匹配 array4 首 key=node65 page0（717e38f3），首个 query ts=1788325968.315（写后 0.5s），45 次全部 hit=0。

## 2. artifacts

- 本地证据目录：`/tmp/p2io-e7l-ev/`（已拉回本机）
  - `t38c-probe.log`（1050441 B，2860 行：pc_write_seed 62 / pc_prefetch_enter 1148 / pc_outcome 1239 / pc_storage_query 395 / pc_stats_snapshot 16）
  - `engine-p2io-m4t-e7l.log`（3213375 B）
  - `evidence-p2io-extent-m4t-e7l/run-20260902-131213/`（driver evidence）
- 远端已清理：证据目录、run 脚本/日志/status/sampler/engine log、t38c gate、lock、extent 存储（find -delete 全清）；GPU 归零 15 MiB；进程树干净。
- 远端启动脚本：`/tmp/p2io-m4t-e7l-run.sh`（本机）/ 曾部署 `/root/p2io-m4t-e7l-run.sh`（已清）。M4T 配置同 e7j：HICACHE_SIZE=12G + `--hicache-writeback-reserve-gb 0.75` + `--ready-horizon-safety-margin-gb 0.3` + enable-ready-horizon + extent + write_back + T15 off + 8 agents / 96 req / 24 turns / K=8。仅新增 `touch /tmp/t38c-on`（日志型埋点 gate）。

## 3. evidence

### 3.1 执行

```
nohup bash /root/p2io-m4t-e7l-run.sh &
13:10:11 run begin / t38c probe enabled
13:12:12 engine healthy (scheduler pid 232883)
13:19:53 driver finished rc=0
13:20:15 engine SIGTERMed, GPU 15 MiB, t38c disabled
M4T_E7L_STAGE_COMPLETE rc=0
```

### 3.2 事件计数

```
$ wc -l t38c-probe.log            # 2860
$ grep -c pc_write_seed           # 62
$ grep -c pc_prefetch_enter       # 1148（gate 574）
$ grep -c pc_storage_query        # 395
$ grep -c pc_outcome              # 1239
$ grep -c pc_stats_snapshot       # 16
```

### 3.3 写侧 seed（pc_write_seed：node_id → seed8 → page0 → n）

样例（62 个中的代表性节点）：
```
node=19  seed8=''        page0=f9ec16cd n=3      # root 子节点，无父 seed（'' 合法）
node=18  seed8=cb3d0866  page0=e4af379a n=61
node=23  seed8=cb3d0866  page0=3b1261d4 n=6
node=29  seed8=0b4304e2  page0=8b454ffe n=2048
node=56  seed8=cccc87fd  page0=3729b5aa n=1458
node=58  seed8=47f6ac45  page0=fc764235 n=1889
node=65  seed8=3689cb01  page0=717e38f3 n=2048   # 裁决关键样本
```
seed8=`fbd8c9a9` 在 7 个兄弟节点重复出现（共享同一父 last_hash）——符合"写链以 parent.last_hash 为种子"的语义。

### 3.4 读侧 anchor（pc_prefetch_enter phase=gate 的 anchor.last_hash8）

```
574 个 gate 事件，非空 last_hash8 507 个，distinct 152 个
gate_pass=true 且 matched_len>0 的事件 355 个，distinct anchor 19 个
其中与写侧 seed8 集合重合（seed-consistent）的 anchor 覆盖事件 132/355
```

### 3.5 逐 matched 字节对比（核心裁决）

对每个 passed anchor 定位对应写节点，再对比该写节点 page0 是否恰好为某个 query array 首 key（matched chain 的字节连续性）：

```
anchor=3689cb01 -> 写节点 65, page0=717e38f3, n=2048
   query array 首 key = 717e38f383cb21ac == page0 全等（matched chain 字节连续）
anchor=0b4304e2  -> 写节点 29, page0=8b454ffe
   query array 首 key = 8b454ffe71901ba0 == page0 全等
anchor=cccc87fd  -> 写节点 56, page0=3729b5aa
   query array 首 key = 3729b5aacb2da4c9 == page0 全等
anchor=47f6ac45  -> 写节点 58, page0=fc764235
   query array 首 key = fc7642351f3db916 == page0 全等
```
=> 19 个 distinct passed-array 中 5 个首 key 等于某写节点 page0，且其 anchor seed == 写侧 seed8。**字节一致。**

### 3.6 决定性时间证据（node65 案例）

```
写节点 65: pc_write_seed ts=1788325967.794
匹配 array4 首 key=717e38f383cb21ac (=node65 page0 717e38f3)
首个匹配 query ts=1788325968.315  (写后 0.52s)
45 个匹配 query，storage_hit_count 全 = 0，kv_hit_pages 全 = 0
```

### 3.7 全局 hit 结果

```
$ total storage queries: 395
$ storage_hit>0: 0
$ kv_hit_pages>0: 0
```

### 3.8 后端写入完整性（排除 write-drop）

```
$ ExtentFileBackend: file=/data/l3/p2io-extent-e7l/hicache.data_qwen3.5-9b-gptq_0_1
    extent=67108864 B slots=1024 max_size=20000000000 min_free=10000000000
$ ls -la hicache.data...            # 68719476736 B（68G 文件，5.8G 实际占用）
$ grep -c evt=extent_write          # 170 条批次事件
$ kv keys 累计写入 = 97859  (== pc_write_seed 的 sum n_pages=97859，零丢失)
$ grep -c evt=extent_recycle        # 0（allocator 从未 drop slot）
$ 写失败/refuse 日志：无
$ node65 不在 "dropped without backup" 集合（count=0，写已落盘）
```

### 3.9 key transform 两侧一致（排除 suffix 不对称）

```
写侧 batch_set_v1: storage_keys = [self._storage_key(k) for k in keys]  # k=hash, suffix=config_suffix
读侧 batch_exists_v2: present(key)= self._allocator.lookup(self._storage_key(key))  # 同 transform
_storage_key(key) = key + config_suffix  (双侧同一函数)
config_suffix = '_qwen3.5-9b-gptq_0_1'
hicache_storage_pass_prefix_keys = False  # write 与 read 均为 None，排除 prefix_keys 边界
```

### 3.10 prefix_keys 窄探针（B 分支收窄）

`pass_prefix_keys=False`（unified_radix_cache.py:366/581 硬编码），写读两侧 `prefix_keys=None`；query key-array 固定 8 页、首 key 与写链 page0 字节连续（非 truncation 所致——写 2048 页、读链 8 页首 key 精确对齐 page0）。=> **prefix_keys 边界排除，B 分支收窄到 allocator lookup / key 注册。**

## 4. summary

M4T-e7l live run（12G/0.75G/0.3G，UnifiedRadixCache live 路径，8 agents）完成，driver rc=0，GPU 归零，t38c 埋点全程开启。

**裁决结论（e21 裁决点）：seed 无罪（byte-consistent 成立）。** 逐 matched rid/span 字节对比显示：写链 page0 与读链 query array 首 key 字节全等（5 个独立 matched chain），且写侧 seed8 == 读侧 anchor.last_hash8（132/355 passed 事件）。写 97859 页全部落盘（extent_write 计数 == pc_write_seed sum）、零 refuse、零 extent_recycle、node65 写后 0.5s 即被查仍 miss。**因此不是 seed 错位。**

**B 分支坐实（backend key space / allocator lookup 边界）。** 具体收窄：
- 排除了 prefix_keys 边界（pass_prefix_keys=False，写读均 None，非 truncation）。
- 排除了 suffix 不对称（双侧同一 `_storage_key` transform）。
- 排除了 write-drop（全部落盘，零损失，node65 未 drop）。
- 排除了 allocator GC/eviction（0 extent_recycle；node65 写 0.5s 后即查）。
- 剩余失败面：**写入向 allocator 注册的 key 与读侧 `batch_exists_v2` 查询的 key 在 index 中不命中**——即写虽落盘（pwrite+commit 到 `_index`），但读侧 lookup 的同 key 找不到。极可能写侧实际 commit 的 storage_key 与读侧构造的 storage_key 在 index 中不一致（例如写走 `_page_backup`→`batch_set_v1`（零拷贝 path），而存在某处用不同 hash/extra_key 注册；或读侧 `get_hash_str` 生成的 16-hex 与写侧 `compute_node_hash_values` 生成的 16-hex 后 8 位/完整 64 位在部分场景不同——虽然首 8 hex 与 seed8 一致，但 instrumentation 只记录了 8-hex，完整 64 位是否逐字节一致未被本探针覆盖，属下一步需在字节级坐实的点）。

**次级观察（非本裁决点但需上报）：** 全程 host memory pressure 严重——749 条 "KV subtree dropped without backup"（节点 72-885 大片）；shutdown 时 sanity check FAILED（4 violations：H-leaf extra/duplicate ghost/stale leaf/mamba host LRU，均集中在 node 104）触发 SIGQUIT。这些是 host 层/内存压力问题，与 L3 key-space 是本裁决独立、但可能混淆后续 hit-rate 分析，列为 followup。

## 5. followups

1. **在字节级坐实 B 分支具体缺陷点**：当前 instrumentation 只记录 8-hex（seed/page0/anchor）。下一步应记录写侧与读侧**完整 64-hex hash** 逐字节对拍（特别 node65: write page0 full vs query key[0] full），确认是否 64 位全等而 lookup 仍 miss（=> allocator index 注册缺陷），或后 8 位/后缀分歧（=> hash 字节分歧）。位置：`unified_radix_cache.py:2205` pc_write_seed 改记全 hash；`scheduler.py:2973` gate 记全 anchor hash。建议 tester 下一任务。
2. **检查 `_page_backup` 实际走哪个 page_set_func**：cache_controller.py:380 `page_set_func = _generic_page_set`（→ `batch_set` → `_write_pages`，commit `_storage_key(hash)`）；但 :691 有 `_page_set_zero_copy`（→ `batch_set_v1`，同样 `_storage_key`）。两者 key 变换一致，但值得确认 live 实际绑定哪一个并核对 commit 的 key 与 `_storage_key` 完全一致（尤其 extra_key / page_aligned 后的 hash）。位置：`cache_controller.py:380/691/1381`。
3. **host memory pressure（749 subtree drop）是独立问题**：建议 orchestrator 评估是否将 host 层 drop 与 L3 key-space 分列跟踪；当前高 drop 会压制 storage_hit 可测性（很多链根本没写进 L3），但 node65 案例证明"写了也 miss"，故 key-space 缺陷独立成立。位置：scheduler.py write_back 路径。
4. **shutdown sanity check FAILED（node 104，4 violations）**：独立于本裁决，但属 live 路径一致性隐患，建议 coder 查 node104 的 H-leaf/ghost/stale 状态。位置：`unified_radix_cache.py:4349 sanity_check` / `unified_tree_core.py:2752`。

## 6. open_issues

- **未覆盖：完整 64-hex 逐字节对拍**。本探针的 write_seed8/page0_hash8/anchor.last_hash8 均为 8-hex 截断；seed 与首 key 8-hex 全等已坐实，但"完整 hash 字节"是否全等未被直接测量（8-hex 一致 + matched chain 连续强烈暗示全等，但 B 分支的具体缺陷点（allocator 注册 vs hash 分歧）需 64-hex 探针最终裁决）。这是下一个任务的明确入口。
- 远端运行资源已全部清理（证据仅存本机 `/tmp/p2io-e7l-ev/`）。
