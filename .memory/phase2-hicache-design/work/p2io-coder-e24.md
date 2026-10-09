# p2io coder e24 — 三嫌疑核查 + storage_generation 0→40 答案 + 根因收敛

status: done (本轮核查结论闭合；修复定位到 extent 后端之外，待协调人定夺范围)

## 1. status

本轮按协调人指示"停广撒网，按三嫌疑 + 决定性探针执行"，完成了：

- 三嫌疑逐一核查（generation / commit publish / allocator 实例）——全部在确定性单测层排除；
- commit 自证探针 6/6 全过；
- storage_generation 0→40（实测 0→44）的来源定位——不是 allocator 的 recycle generation；
- 真正的 live 根因机制通过确定性复现锁定（mamba TRAILING_PAGES 尾 key 注册/可见性分歧）。

结论：协调人的三嫌疑在 extent 后端层**不成立**（probe 全部通过），而 live storage_hit=0 的根因
在 **mamba 侧车 TRAILING_PAGES(1) 尾 key 的写侧注册与读侧检查不一致**——这落在组件/读侧
key 物化层，**不是 extent 后端的 index 注册/可见性 bug**。修复点超出"extent 后端核心逻辑改动
限 index 注册/可见性修复"的授权范围，故本轮未改核心逻辑，仅以探针 + 确定性复现 + 单测断言
坐实。修复决策交给协调人。

## 2. artifacts

本轮未修改任何 `crates/`/`python/` 生产代码（在授权范围内无可修复点）。新增探针脚本
（`3090-dev/`，均为本地确定性复现，非生产代码）：

- `p2io_e24_commit_probe.py` — 协调人 10 行自证探针（reserve→write→commit→各时序 HIT 检查）。
- `p2io_e24_mamba_probe.py` — mamba 侧车跨线程可见性（2048/2048 HIT）。
- `p2io_e24_growth_probe.py` — node 增长后 mamba 尾 key 丢失 → 1024 clamp。
- `p2io_e24_repro4.py` — node57 形状（1458 写，尾 key 注册）：1458/1458 HIT。
- `p2io_e24_repro5.py` — node 长于 present 前缀时：kv_hit=0，extra {'kv':1024}（**匹配 live 签名**）。

以上脚本在 summary 前已创建；本轮全部重跑复核，输出见 evidence。

## 3. evidence（实测，真实输出）

### 3.1 commit 自证探针（决定性）—— 6/6 全过

```
1. immediate same-thread: 8
2. after 100ms: 8
3. another thread: 8
4. after unrelated writes: 8
5. after new-extent fill: 8
6. after GC eviction (recycle): 0
   allocator generations: [1, 1, 1, 1, 1, 1]
   index size: 2
```

即时/跨线程/无关写/新 extent 全部 8/8 HIT；唯一 MISS 在 GC recycle 该 extent 后，
generations=[1,1,1,1,1,1]（ABA 保护生效）。**嫌疑 1（generation 语义）、嫌疑 2（commit 未
publish）、嫌疑 3（allocator 实例/线程）在确定性单测层全部排除。**

### 3.2 mamba 跨线程探针 —— 2048/2048 HIT

```
KV present (v2 no sidecar): 2048
mamba last-page key registered: True
generations: [0, 0, 0]
CROSS-THREAD mamba-sidecar query: (2048, {'kv': 2048, 'mamba': 2048})
AFTER unrelated writes (cross-thread): (2048, {'kv': 2048, 'mamba': 2048})
```

备份线程写 → 预取线程读，跨线程可见性 OK；无关写后仍 2048/2048。实例/线程嫌疑再排除。

### 3.3 storage_generation 0→44 的来源（engine 日志直查）

`storage_generation` **不是** allocator 的 recycle generation。出处：
`unified_radix_cache.py:3306` 打印 `self.tree_core.l3_publish_epoch()`；
`unified_tree_core.py:2119-2130` `_bump_l3_publish()`（写 ack 促进 persisted / restore
read-back 确认 L3 存在时 +1）。engine 日志直方图：

```
     13 storage_generation=0
      1 storage_generation=11
      1 storage_generation=19
      1 storage_generation=28
      7 storage_generation=31
      1 storage_generation=38
    316 storage_generation=44
```

而 allocator 的 `_generations`（per-slot，仅 `_drop_slot` recycle 时 +1）在 live 全程 **0 次
recycle**（`extent_recycle` 在 t38c-probe.log 与 engine 日志均 0 次）→ 恒 0。故
"没有 recycle 却 0→40/44" 的疑问答案：**那个字段是 L3 publish epoch（写 ack/restore 的次数
单调计数器），与 slot/extent recycle 的 ABA generation 完全无关**。协调人假设的
"generation 语义写错导致 0→40" 在代码里**不存在**对应机制。

### 3.4 live 根因签名（340 条 pc_storage_query 直查）

```
258 条 sidecar_hits 非空，全部 {"kv": N>0}（N=1024/1027/1458/1889/9）
但全部 storage_hit_count=0  —— KV 前缀 present，却被 clamp 到 0
```

- node29（rid 5759ea5f）：写 2048 页，mamba extent_write **恒 keys_n=1**（52 次 mamba 写全部
  keys_n=1）；查询 kv_hit 始终 1024→1027，**从未到 2048**。
- node57（rid d48b8c91）：写 1458 页（write_seed n_pages=1458），查询 kv_hit=1458，
  sidecar {'kv':1458}，storage_hit=0。
- KV 注册总量 93389 == 各 write_seed n_pages 之和 93389（无聚合级 KV 丢失）；
  105 次 kv extent_write，keys_n 多为 1024 批。

### 3.5 确定性复现（根因机制，非猜测）

growth_probe（node 1024→2048 增长，mamba 尾 key 仍停在 page1023）：

```
phase1: mamba key registered for page1023: 4b5574d981341983
  query 1024-chain: 1024
phase2: node grew to 2048. mamba key still only page1023.
  KV present: 2048
  page2047 mamba key registered: False
  mamba-sidecar kv_hit: 1024 extra: {'kv': 2048, 'mamba': 1024}
```

repro5（node 2048 写 + 尾 key 只注册 page2047；query 只见前 1024 present）：

```
KV present prefix: 1024
last present page hash == node last page hash: False
RESULT kv_hit_pages: 0 extra: {'kv': 1024}      <-- 与 live 签名逐字一致
```

repro4（node57 形状，尾 key 正确注册）：1458/1458 HIT。

## 4. summary（结论与机制）

**机制**：mamba `BACKUP_STORAGE` 写侧只注册 `keys=[node.hash_value[-1]]`（node 写入时刻的
**最后 1 个** page hash）到 `.mamba` 组件 key（mamba_component.py:752-763）。读侧 PREFETCH
用 `keys=["__placeholder__"]`（mamba_component.py:765-774），`batch_exists_v2` 的
TRAILING_PAGES(1) 分支检查"查询链最后 present 页"的 `.mamba` key 是否存在
（extent_file_backend.py:648-657）。两者只在"查询的最后 present 页 == 写入时 node 的最后页"
时对齐；任何 node 增长 / 查询前缀短于 node 尾 / 多批 KV 注册切分 → 该 `.mamba` 尾 key 未注册
→ mamba boundary=0（或钳到最长的匹配前缀）→ `final_pages=min(kv_pages, boundary)` 把
storage_hit 压到 0，尽管 KV 全部 present。`_sync_trailing_keys`
（hybrid_cache_controller.py:834-868）在 `_storage_hit_query` **之后**才重排 sidecar keys，故
`batch_exists_v2` 查询时 keys 仍是占位符。

**三嫌疑结论**：
1. generation 语义写错（~50%）——**排除**。commit probe step4/5（无关写/新 extent）仍 8/8；
   allocator `_generations` 仅 recycle 时 +1，live 0 次 recycle 恒 0；无 0→44 的代码机制
   （0→44 是 l3_publish_epoch，与 recycle 无关）。
2. commit 没真正 publish index（~35%）——**排除**。commit 后即时/100ms/跨线程/无关写全部 HIT。
3. 不是同一 allocator 实例（~10%）——**排除**。attach 单实例 + 跨线程探针 2048/2048。

**修复范围**：真正根因在 mamba 侧车读侧 TRAILING_PAGES 尾 key 的物化/注册对齐，位于
`mamba_component.py` / `hybrid_cache_controller.py` 组件/读路径层，**不是 extent 后端的
index 注册/可见性 bug**（extent 后端的 fold/clamp 语义正确，且被 `test_v2_prefix_semantics`
钉死为设计契约）。因此不在"extent 后端核心逻辑改动限 index 注册/可见性修复"授权内——本轮
未改生产代码。

## 5. followups

- **修复点候选（交协调人定夺，均在 extent 后端之外）**：
  - (a) 读侧：让 mamba PREFETCH 在 `batch_exists_v2` 前把 TRAILING_PAGES 尾 key 物化为
    "最后 present 的 KV 页"（而非占位符）——即把 `_sync_trailing_keys` 提前到 `_storage_hit_query`
    之前，或 mamba 侧车 keys 语义改为"最长 present 前缀的最后 1 页"。
  - (b) 写侧：`BACKUP_STORAGE` 为 mamba 注册每页组件 key 或保证 node 增长后重写尾 key，
    使查询的最后 present 页总能命中（但会增加 mamba 写放大）。
  - 推荐 (a)：改动最小、符合设计 C5"keys 对齐到实际命中窗口"。
- 全门验证：修复落地后需跑 extent 单测（现 71 全过）+ tester 的集成层（`batch_exists_v2`/
  `_sync_trailing_keys` 时序）确认 storage_hit 不再被误钳。
- live KV 1024 上限（node29 写 2048 但查询只 1024/1027）疑为 radix 前缀/查询链分支所致
  （KV 总量 93389 无丢失），本轮未单独闭合，建议 tester 在集成层复核。

## 6. open_issues

- 根因已确定性复现并坐实，但**修复未落地**（超出授权范围）。需协调人裁决修复点 (a)/(b)。
- `test_v2_prefix_semantics` 钉死的 fold/clamp 契约与 live 需求（KV present 不被误钳）存在
  张力：若选 (a) 读侧物化，clamp 契约不变（extent 层照旧按 sidecar key 对齐钳制），
  冲突点在组件层而非 extent 层——不影响该单测。
- 探针脚本保留在 `3090-dev/`（非生产代码），未删。
