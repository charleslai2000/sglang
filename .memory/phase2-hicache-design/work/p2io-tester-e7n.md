# p2io-tester-e7n.md — query span / anchor 选择分析（e27 纯日志提取）

- task: e7n / e27 剩余唯一嫌疑（查询端 anchor/span 选择，hit 被 span 封顶）的日志事实提取
- 纯日志分析，无新实验、无代码改动。数据源：`/tmp/p2io-e7m-ev/t38c-probe.log`（e7m 同 e7l 同构，pc_storage_query 已全 64-hex keys）。
- 日期 2026-09-02

## 1. status

**done** — 提取全部 5 项事实，判定 e27 假设（hit 被 span 封顶）**不成立**；0-hit 根因与 e7m 一致 = allocator index 注册路径缺陷，span 无辜。

## 2. artifacts

- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/p2io-tester-e7n.md`
- 数据源：`/tmp/p2io-e7m-ev/t38c-probe.log`（2524 行：pc_write_seed 56 / pc_prefetch_enter 1020 / pc_storage_query 340）+ `/tmp/p2io-e7m-ev/engine-p2io-m4t-e7m.log`
- 分析脚本：临时本地 Python（读上述 log），无远端改动；远端已清理（GPU 15 MiB 归零）。

## 3. evidence

### 3.1 query keys 数组长度分布

```
logged keys array length: 一律 8（340/340）—— instrumentation 截断 hash_value[:8]（hybrid_cache_controller.py:625）
真实 span = query_suffix_len（= len(page_hashes)，page_size=1 即 token 数）：
  分布：3502 x4, 4526 x16, 4957 x12, 5388 x13, 10241 x3, 10595 x3, 11427 x17,
        11532 x23, 11858 x8, 12289 x5, 17242 x9, 17404 x1, 17596 x2, 17724 x1,
        18027 x1, 18428 x33, 18433 x7, 18859 x14, 20910 x89, 25434 x13, 25943 x12,
        26105 x2, 27129 x26, 27560 x11, 27811 x19
  min=3502, max=27811
不是 1024/1027 集中——真实 span 覆盖 3502~27811，全部 > 1024，最长 27811。
```

### 3.2 首 key 语义（keys[0] = 写链哪一页）

```
写侧 compute_node_hash_values 产整链，pc_write_seed 记 page0/page1（64-hex）。
读侧 _storage_hit_query: page_hashes = get_hash_str(tokens_to_fetch, last_hash)
  → 以 anchor.last_hash 为种子、对 new_input_tokens 逐 token 哈希，keys[0] = 链第 0 页。
5 个 matched 数组 keys[0] 与写节点 page0 全 64-hex 相等 → keys[0] = 写链 page0（链头），非中途页。
11 个 unmatched 数组 keys[0] 不在 56 观测写节点的 page0 集合（= 从未写过的链 或 写节点第 3+ 页，写侧只记 p0/p1，无法全量归因）。
```

### 3.3 与写链覆盖对照（node29/node65 写 2048 页）

```
node29（n_pages=2048）matched 数组（45 查询）：
  keys[0] == 写链 page0 (8b454ffe...)
  keys[1] == 写链 page1 (be4d2472...)
  keys[2..7] = 链连续（page2..7 的哈希，同一次 get_hash_str 产出）
  query_suffix_len ∈ {4526, 11427, 18428, 27129}（全部 > 2048）

node65（n_pages=2048）matched 数组（44 查询）：
  keys[0] == 写链 page0 (717e38f3...)
  keys[1] == 写链 page1 (b5898dbc...)
  query_suffix_len ∈ {4526, 11427, 18428, 27129}（全部 > 2048）

=> 查询 span 既不是"全链 0-2047"也不是"前 1024"也不是"suffix 1024-2047"——
   查询链从 page0 起、长度 = 该次 new_input_tokens 的 token 数（4526~27129），
   可远超写节点自身 2048 页（查询内容跨写节点 + 后续未写部分）。
```

### 3.4 matched_len / anchor 来源（scheduler 传参如何决定 span）

```
scheduler.py:2998-3011:
  matched_len = len(req.prefix_indices) + req.host_hit_length
  match_end   = req._compute_max_prefix_len(len(req.full_untruncated_fill_ids))
  new_input_tokens = req.full_untruncated_fill_ids[matched_len:match_end]
  prefetch_from_storage(req.rid, last_host_node, new_input_tokens,
                        tree_cache.get_last_hash_value(last_host_node), ...)
读侧 _storage_hit_query:
  page_hashes = get_hash_str(tokens_to_fetch=new_input_tokens, last_hash=anchor.last_hash)
  → 链长 = match_end - matched_len = gate.suffix_len

gate vs query 对拍（node65 matched rids）：
  gate_pass=True 且当 pass 同步时: query_suffix_len == gate.suffix_len（11427/11427, 4526/4526, 27129/27129）
  gate_pass=False（旧 gate 事件）: query_suffix_len > gate.suffix_len（18428 vs 11424, 27129 vs 18937）——
    因 query 发生在后续 pass 的重新求值，链长按当时 matched_len/match_end 重算。
=> span 完全由 scheduler 的 matched_len:match_end 切片决定，后端不做截断。
```

### 3.5 span 判定 + 代表样本（node29/node65 完整 keys 对比）

**判定：查询 span 天然为完整 new-input suffix（3502~27811 页），非 1024 截断，也非 backend 截断。** backend `batch_exists` 从 keys[0] 起逐 key 查 `_allocator.lookup`，首个 miss 即短路返回 0（cache_controller.py:1304-1310 + extent_file_backend.py:392-397；STORAGE_BATCH_SIZE=1024，但 batch0 = 页 0..1023，keys[0] 必查）。

代表样本（node29 matched array，45 查询同一数组）：

```
写 node29:  p0=8b454ffe71901ba0430b3f5776829dacb834315c2e997365cf5253b54fdc1f51
            p1=be4d2472b286ec9dd715d5e05f0636f0c428fe83ff13c14c3485ae46917b3d4c
query keys[0]=8b454ffe71901ba0430b3f5776829dacb834315c2e997365cf5253b54fdc1f51  <- =写链 page0
query keys[1]=be4d2472b286ec9dd715d5e05f0636f0c428fe83ff13c14c3485ae46917b3d4c  <- =写链 page1
query keys[2]=7a270466ace966152919dc60816c1a3512e7ea6e791ae3ecbebb7c6898072434
query keys[3]=b39349e8eef712d9892251a2b8256d910d29444b0dc0bfc09acb420c3d48e1e0
query keys[4]=b14b73b1a8fe0fb0d4952a75f9f645b250af1b739d3fd854360924db76ec0e08
query keys[5]=792c151322f71a9dac872884e8250ca3cd9aca294a7be8b5a7435cf89d306540
query keys[6]=1089d0ac7dbea07d3da9734eca523b8130390d9ddf8fec6734e8ae7370e8ed91
query keys[7]=cf0f21fc3be696012db425c3c028b52025ec55a9dbfbf54a2bfcc1a9f353082f
suffix_len 分布：{4526:7, 11427:7, 18428:17, 27129:14}，全部 > 写节点 2048 页
```

```
写 node65:  p0=717e38f383cb21ac02d6af41244f23ce4f1a7e4d33a7f0d028ba2648efd023d1
            p1=b5898dbcf36ffd10823b0f055efb6bf9f0b7e1af154ede44a7415bbc724bb93c
query keys[0]=717e38f383cb21ac02d6af41244f23ce4f1a7e4d33a7f0d028ba2648efd023d1  <- =写链 page0
query keys[1]=b5898dbcf36ffd10823b0f055efb6bf9f0b7e1af154ede44a7415bbc724bb93c  <- =写链 page1
query keys[2]=48c8a0418997fea2b4772a0182d0b40df6c0cbaa9e5c099ee4610db937087025
query keys[3]=cbbf071d9f44ef220fd0fee40090cedbb1adf1ef1b834588f3df897e93bf41d6
query keys[4]=247111a778384d4698c70b3aaa3a41ca0ca640a8bd6cc648fe870e7132764b3c
query keys[5]=1c2b41a82c1289f4d02833e7d4eccda96ad9c263db889627ec9af04a3778ed74
query keys[6]=72db6ae1c3cdd66654703f1460f6f0bde65f52470cbc33fce88c6b683ec11840
query keys[7]=544457b5c8341904ef6cd0115be81e417995ef8198dbe5e8b26d24cc08ced135
suffix_len 分布：{4526:9, 11427:7, 18428:16, 27129:12}，全部 > 写节点 2048 页
```

### 3.6 0-hit 与 span 的关系（决定性）

```
matched 数组（keys[0] = 已提交写链 page0）：260/340 查询，storage_hit_count 全部 = 0
backend batch_exists 从 keys[0] 起查，首个 miss 短路 → 0
keys[0] 字节全等且写侧已提交（e7m 已证 64-hex 全等 + 93389 页落盘 + 0 recycle），但 lookup 返回 None
=> hit=0 与 span 无关（span 再长也是 0；若 span 短也不会 1+），根因 = allocator index 注册路径缺陷
```

## 4. summary

纯日志提取完成，e27 假设（hit 被 span 封顶）**被证伪**：

1. **长度分布**：真实 span（query_suffix_len）3502~27811，全部 >1024，最长达 27811；logged keys 恒 8 仅因 instrumentation 截断，不代表后端只查 8 页。
2. **首 key 语义**：keys[0] = 查询链 page0（链头），非中途页——5 个 matched 数组与写节点 page0 全 64-hex 相等。
3. **写链覆盖**：node29/node65（写 2048 页）的查询从 page0 起、span 4526~27129 页（远超写节点自身），既非"全链 0-2047"也非"suffix 1024-2047"也非"前 1024"——查询内容 = 该次 new_input_tokens 全量。
4. **matched_len/anchor 来源**：span = `full_untruncated_fill_ids[matched_len:match_end]`（scheduler.py:2998-3011），完全由 scheduler 传参决定；后端 `batch_exists` 不截断（batch0 从页 0 起、首 miss 短路）。
5. **结论**：查询 span 天然完整（scheduler 传参 = 全 suffix），后端不做截断。**0-hit 不由 span 封顶造成**——matched chain 的 keys[0]（页 0）字节全等且已提交仍 lookup miss，根因回到 e7m 的 allocator index 注册路径缺陷。

**修复指向**：不在 scheduler 的 matched_len/span 构造（传参正确），也不在 backend 截断（后端无截断）。修复指向 = e7m followup 1 的进程内 allocator 探针（同线程 batch_set_v1 → batch_exists 对拍，区分"注册 key ≠ 查询 key" vs "跨实例/线程可见性"）。若按 e27 原文要求二选一：**非 scheduler 传参截断、非 backend 截断 → 属 allocator 注册路径（e7m 分支），应回 extent/allocator 层排查注册 key 的生成（build_storage_backup_spec → spec.hash_value 与 batch_set_v1 实际 commit 的 storage_keys 一致性）。**

## 5. followups

1. **进程内 allocator 探针**（唯一修复入口）：对 node65 的 page0 64-hex key 同线程 batch_set_v1→batch_exists 立即对拍。若 miss → 注册 key ≠ 查询 key（查 build_storage_backup_spec 产出的 spec.hash_value 与 batch_set_v1 的 storage_keys 差异，extent_file_backend.py:508 vs unified_tree_core.py:2037）；若 hit → 跨实例/线程可见性（查 controller/backend 单例与线程边界）。
2. **补写侧全链日志**（消解 array#5-15 归因歧义）：pc_write_seed 记录完整 spec.hash_value（或每 64 页采样），使 unmatched 数组的 keys[0] 可归因到"写链中途页"还是"未写链"。位置：unified_radix_cache.py:2205。
3. **matched_len 与 gate_pass 时序**：DIFF 案例（query_suffix_len > gate.suffix_len）源于 query 在后续 pass 重算，非 bug；无需处理，但建议在 pc_storage_query 增加 issue_pass 计数以便对照（可选）。
4. 次级：shutdown sanity check FAILED（81 nodes/4 violations，同 e7l/e7m 现象），host 层一致性隐患，建议 coder 查。

## 6. open_issues

- array#5-15（80/340 查询）的 keys[0] 未在写节点 p0 集合中：可能是从未写入的链（真 miss）或写链第 3+ 页（写侧仅记 p0/p1 无法归因）。不影响本裁决（matched 5 数组已独立坐实 allocator 缺陷），但补全写链日志后方可全量闭合。
- 远端无任何改动；证据仅存本机 `/tmp/p2io-e7m-ev/`。
