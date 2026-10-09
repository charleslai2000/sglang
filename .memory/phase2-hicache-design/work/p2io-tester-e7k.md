# p2io-tester-e7k — write key == query key 字节级对拍探针（e20 后继）

- 任务：e7k（3090 真实对拍——最小 deterministic 探针，几秒级，不长压）
- 目标：把 write key == query key 动态证明到字节级，按用户裁决规则选一支
- 运行：2026-09-02（探针 /root/p2io-m4t-e7k-probe.py / -v2.py / -v3.py，已保留可复现）
- 报告：p2io-tester-e7k.md；探针脚本远端保留于 /root/

## 1. status

**done**（逐页 hash 对拍 + 真实 backend write→exists + 种子错位假设验证全部完成；裁决选 **第 3 支主结论 + 第 4 支追加确认**——见 §4）

## 2. artifacts

- 探针脚本（远端保留，可复现）：
  - `/root/p2io-m4t-e7k-probe.py`（v1：4-page hash 对拍，root/mid-chain 种子）
  - `/root/p2io-m4t-e7k-probe-v2.py`（v2：+ 真实 ExtentFileBackend write→immediate batch_exists）
  - `/root/p2io-m4t-e7k-probe-v3.py`（v3：+ 种子错位假设——不同 seed 复现 storage_hit=0）
- 本机副本：`/tmp/p2io-m4t-e7k-probe.py` / `-v2.py` / `-v3.py`
- 代码证据：/root/sglang-b1-continuity 的 native_hash.py / hash_binding.cpp / extent_file_backend.py / cache_controller.py / hiradix_cache.py（见 §3.5）

## 3. evidence（命令 + 真实输出）

### 3.1 逐页 hash 表（CASE A：root seed，page_size=4，16 tokens）

```
token span: [100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115]
  page 0: write_hash=9d373db168e3e6a0 read_hash=9d373db168e3e6a0 SAME
  page 1: write_hash=ba16f22309bf4813 read_hash=ba16f22309bf4813 SAME
  page 2: write_hash=903f67facce6cd22 read_hash=903f67facce6cd22 SAME
  page 3: write_hash=45ff48b8a57cef4d read_hash=45ff48b8a57cef4d SAME
  -> 0 分叉页（4/4 SAME）
```

### 3.2 CASE B：mid-chain seed（write 侧 parent.last_hash = read 侧 anchor.get_last_hash_value，同一 seed）

```
seed = hash(page0) = 9d373db168e3e6a0
  page 0: write_hash=fffe67578a7510f5 read_hash=fffe67578a7510f5 SAME
  page 1: write_hash=1739908a3940b838 read_hash=1739908a3940b838 SAME
  page 2: write_hash=cd2af44845eb0496 read_hash=cd2af44845eb0496 SAME
  page 3: write_hash=52cf242a4f3c6664 read_hash=52cf242a4f3c6664 SAME
  -> 0 分叉页（4/4 SAME）
```

### 3.3 CASE C：真实 backend write→immediate exists（v2）

```
backend init OK config_suffix='_qwen3.5-9b-gptq_0_1'   # 与引擎完全一致
batch_set(W) ok=True
batch_exists(W) -> hit_pages=4 (expected 4)
exists() per page = [True, True, True, True]
canonical storage keys = page_hash + '_qwen3.5-9b-gptq_0_1'
-> write 后立刻 exists 全 PASS（RAM index 立即发布）
```

### 3.4 CASE D：种子错位假设（v3）——不同 seed 复现 storage_hit=0

```
SEED_W (write parent) = aaaaaaaa...aaaaaaaa
SEED_R (read anchor)  = bbbbbbbb...bbbbbbbb
write hashes (seed=SEED_W): 171f7731a473756d db3b49bece73912e 187260b99786fe5b e57da88a4d255915
(a) query SAME seed -> batch_exists=4 HIT
(b) query DIFFERENT seed -> batch_exists=0 MISS at 0
page-0 hash write-seed : 171f7731a473756d
page-0 hash read-seed  : 4cac4d97e138bb31
divergent at page 0? True
-> seed 错位（write 父种子 != read anchor 种子）单变量即可复现 storage_hit=0
```

### 3.5 引擎代码链（证明 seed 来源结构）

- 写侧 `write_backup_storage`（hiradix_cache.py:940-966）：写 `node.hash_value` + `prefix_keys=top.get_prefix_hash_values(top.parent)`；`node.hash_value` 由 `compute_node_hash_values` 以 `parent.hash_value[-1]` 为种子链式生成。
- 读侧 `query_storage_hit_length`（hiradix_cache.py:1501）+ `_storage_hit_query`（cache_controller.py:1291）：`page_hashes = get_hash_str(tokens, operation.last_hash)`；`last_hash = anchor.get_last_hash_value() = last_host_node.hash_value[-1]`。
- `last_host_node`（hiradix_cache.py:1755-1773）：`last_host_node=last_node` 后 while 循环向上走到最近的 backuped 祖先——即**当前请求最深 backuped 匹配节点**。
- `batch_exists`（extent_file_backend.py:392）：纯 RAM `_allocator.lookup(storage_key)`，不依赖 prefix_keys/generation（generation 仅做 slot-recycle ABA 防护，不参与 VALID entry 逻辑键）。
- 原生 hash 扩展：`get_hash_str` → `get_native_hash` → `hicache_hash_cpp.so`（hash_binding.cpp `pages_hashes`，SHA256 链式，与引擎共用同一 .so，字节级真实）。

## 4. summary（核心结论 + 裁决）

### 4.1 逐页 hash 对拍结论（用户裁决规则逐条对照）

| 裁决规则 | 实测 | 结论 |
|---|---|---|
| W0 != R0 → seed/anchor 问题 | **W0==R0**（root 与 mid-chain 种子均全等） | 排除 |
| W0==R0 但后续分叉 → chained hash/page span 问题 | **全页 SAME**（4/4，两种子口径） | 排除 |
| W 全部==R 且 backend canonical key 相等 → hash/key 层无罪 → 转查 RAM index publish / generation visibility / batch_exists metadata | **W==R 且 canonical key 相等**（_qwen3.5-9b-gptq_0_1）+ **write→immediate exists PASS（4/4）** | **hash/key 层无罪，RAM index publish 正常** |
| write→immediate exists PASS 但真实请求查询 FAIL → controller 传入的 prefix/anchor 不一致 | **CASE C PASS，但真实 e7h/e7j storage_hit 恒 0** | **命中：controller 传入的 anchor/prefix 与写链不一致** |

### 4.2 判定（选一支，附证据链）

**主判定（第 3 支 + 第 4 支追加）：hash/key 层无罪；backend RAM index 写入→查询立即一致；真实请求查询 FAIL 的根因是 controller 传入的 seed/anchor 与 write 链不一致。**

证据链闭环：
1. 原生 hash 在**同一 seed** 下 write==read 字节全等（CASE A/B，root 与 mid-chain 两口径）；
2. backend `batch_exists` 是纯 RAM index lookup，write 后立刻 exists 全 PASS（CASE C）→ **RAM index publish 正常、generation 不参与 VALID 键、metadata 可见**；
3. 唯一能复现 storage_hit=0 的是 **seed 错位**（CASE D：不同 seed → page-0 分叉 → batch_exists=0）——与真实 e7h/e7j 的 storage_hit 恒 0 完全同形；
4. 引擎代码：写侧种子 = `parent.hash_value[-1]`（写入节点父的 last hash），读侧种子 = `last_host_node.get_last_hash_value()`（**当前请求**最深 backuped 节点的 last hash）。**两者只在"读时 anchor 恰好 == 写入节点父"时相等**；一旦后续请求匹配到更深/不同 backuped 节点，anchor 的 last hash ≠ 写入父的 last hash → 读链从不同点起算 → page-0 全错位 → storage_hit=0。

### 4.3 这如何解释 e7h/e7j 观察

- e7j 中 `restore_backup` 写入了真实 extent（extent_write 155，kv 2.9GB + mamba 2.6GB），generation 单调 0→40——**写侧确实在落盘**。
- 但读侧每次用当前请求的 `last_host_node` last hash 作种子重算 `get_hash_str(tokens, last_hash)`，得到的 page-0 hash 与写侧存储的 `node.hash_value[0]`（种子=写时父 last hash）**几乎必然不同** → `batch_exists` 第一页就 miss → storage_hit=0。
- host_hit 巨大（20864/20898）而 storage_hit=0：host 命中走 host 树前缀（不需 L3），L3 查询因 seed 错位恒 0——两者不矛盾。

### 4.4 下一步建议（依据裁决）

- **修复方向（若采纳第 4 支）**：controller 传入的 seed/anchor 必须与写链**同一起算点**。两候选：
  - (A) 读侧用与写侧一致的 seed：query 的 `last_hash` 应取**写链的起点**（写入节点父的 last hash），而非 `last_host_node` 的 last hash——即 anchor 应定位到与写 spec 相同的节点/种子；
  - (B) 或写侧把 `prefix_keys`（祖先 hash 链）作为查询的确定性种子基线，读侧用 `prefix_keys[-1]` 作为 `last_hash`，保证写/读从同一祖先哈希起算。
- **验证**：补一个最小 live 探针（在引擎内对同一 token span 打印写侧 parent.last_hash 与读侧 anchor.get_last_hash_value 各一页，确认错位）——但注意 e7j 日志无 hash 埋点（`_t38c` 被 gate off），需临时开 `SGLANG_LOG_LEVEL=debug` 或补一行 hash8 埋点。
- **若走第 3 支（hash 无罪转查 metadata）**：本探针已排除 RAM index publish / generation / batch_exists metadata 异常（CASE C 全 PASS），故不推荐继续查 metadata——主攻 anchor/seed 对齐。

## 5. followups（数量 + 位置 + 建议）

1. **anchor/seed 对齐修复（最高优先，第 4 支）**：hiradix_cache.py:1501 `query_storage_hit_length` / cache_controller.py:1291 `_storage_hit_query` 的 `last_hash` 与 hiradix_cache.py:940 `write_backup_storage` 的写链种子对齐。建议 coder 在最小 live 探针确认后实施（选 §4.4 的 A 或 B）。
2. **补 hash8 埋点**：e19 后 `_t38c` prefetch-enter 日志被 gate off（e7j log 0 条 pc_prefetch_enter）。建议恢复一个精简 `last_hash8` 埋点，让后续 run 可直接对拍写/读 seed，避免每次靠离线探针推断。
3. **live 对拍探针（验证修复）**：修复后跑一个最小 deterministic run，断言同一 4-page span 写→读 storage_hit=4（复用 v3 的 seed 一致性思路做端到端断言）。
4. **B_ep/B_fin**：storage_hit 恢复前无法测（restore_success=0）；随 anchor 修复应可测。

## 6. open_issues（未解决/风险）

- **seed 错位是结构性风险**：`last_host_node` 为"当前请求最深 backuped 节点"，与写链起点（写入节点父）在多层分叉/多请求交错下几乎必然不一致——这是 P2-IO 三层 storage_hit 恒 0 的最可能机制。
- **是否还有第二个独立 bug**：generation 单调前进但查询恒 0 也可能叠加 index/GC 因素；本探针在隔离 backend 上已排除 backend 自身问题，故引擎内 anchor 对齐是主嫌疑，但不能 100% 排除 controller 传入 prefix_keys 的边界问题（未在 live 中直接观测到 hash）。
- 本任务纯探针验证，未改引擎代码、未跑长压；修复属 coder 范围，探针脚本已保留供复现/回归。