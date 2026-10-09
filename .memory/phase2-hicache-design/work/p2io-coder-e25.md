# p2io coder e25 — TRAILING_PAGES 语义核查：规格已被现行代码实现

status: done（语义核查 + 回归测试落地；无生产逻辑改动——经判定当前代码已实现用户规格）

## 1. status

按用户裁决"修复 `batch_exists_v2()` 正确实现 TRAILING_PAGES 语义（对齐 upstream HiCacheFile）"，
先对现行 on-disk 代码做了严格的实证核查。**核查结论：当前 `batch_exists_v2` 已精确实现用户
规格，无需（也不应）做逻辑改动**——改动反而会引入回归。本轮交付：

1. 用户三 case 回归测试 + live 形状测试（已落地 `test_extent_file_backend_unit.py`，73 测试
   GREEN）；
2. RED 证明：临时把 reverse-scan 改成"只查最后 present 页"（协调人描述的'当前'行为）→ 新测试
   RED（`0 != 16`），证明测试有真实守卫价值；
3. 详尽分歧核查：192 种配置下 on-disk 实现与用户规格零分歧；
4. live 形状探针：storage_hit > 0 达成。

## 2. artifacts

### 新增测试（test/registered/unit/mem_cache/test_extent_file_backend_unit.py）
- `TestExtentV2.test_v2_trailing_pages_reverse_scan_narrow_cases`（L611）——用户三 case：
  checkpoint @15/@31；query 0..20 → kv_hit=16；query 0..31 → 32；query 0..10 → 0。
  守卫"反向扫描最近 checkpoint"，防止回退到"只查最后 present 页"（那种实现会把 0..20 错钳成 0）。
- `TestExtentV2.test_v2_trailing_pages_live_shape_storage_hit_positive`（L655）——live 形状
  （node65）：2048 KV 全 present + 尾 checkpoint，长链查询 storage_hit>0。

### 探针（3090-dev/，非生产代码，保留）
- `p2io_e25_narrow_cases.py` — 用户三 case 直测（16/32/0 全过）。
- `p2io_e25_live_shape.py` — live 形状（2048>0 全过）。
- `p2io_e25_divergence.py` — 192 配置穷举分歧核查（零分歧）。

### 生产代码改动
- **零逻辑改动**。`extent_file_backend.py` 与实验前逐字节一致（reverse-scan 已是 committed code，
  2026-08-31 e281df3635 引入，非本工作区未提交改动）。

## 3. evidence（实测，真实输出）

### 3.1 现行 on-disk 实现 == 用户规格（逐行对照）

用户规格（mamba trailing=1）：
```
kv_pages = longest_kv_prefix(keys)
boundary = 0
for prefix_len = kv_pages ... 1:
    if mamba_key(keys[prefix_len - 1]) exists: boundary = prefix_len; break
final_pages = min(kv_pages, boundary)
```

on-disk（extent_file_backend.py:648-657）：
```python
trailing = max(1, len(transfer.keys) if transfer.keys else 1)   # mamba: 1
boundary = 0
for prefix_len in range(kv_pages, 0, -1):                        # 反向扫描 ✓
    if all(present(self._component_key(name, keys[i]))
           for i in range(max(0, prefix_len - trailing), prefix_len)):  # trailing=1 -> keys[prefix_len-1] ✓
        boundary = prefix_len
        break
...
final_pages = min(final_pages, boundary)                         # min(kv_pages, boundary) ✓
```
与 upstream `HiCacheFile.batch_exists_v2`（hicache_storage.py:643-655）逐行同构；与
`sim_storage` 同构。**当前代码是用户规格的通用化（trailing=N 覆盖 SWA），mamba 情形等价。**

### 3.2 用户三 case 直测（p2io_e25_narrow_cases.py）
```
query 0..20 -> (16, {'kv': 21, 'mamba': 16})   期望 kv_hit=16 ✓
query 0..31 -> (32, {'kv': 32, 'mamba': 32})   期望 kv_hit=32 ✓
query 0..10 -> (0,  {'kv': 11})                 期望 kv_hit=0  ✓（无 ≤10 checkpoint → 0）
```

### 3.3 穷举分歧核查（p2io_e25_divergence.py，8×8×3=192 配置）
```
NO MISMATCHES across 192 configurations.
on-disk batch_exists_v2 == user's TRAILING_PAGES spec in all cases.
```
覆盖：kv_len ∈ {0,1,10,16,20,32,40} × checkpoint 集 ∈ {∅,{15},{31},{15,31},{0},{39},{1},{40}}
× query 长 ∈ {kv_len, kv_len+3, 40}。全部与从规格实现的 oracle 一致。

### 3.4 live 形状（p2io_e25_live_shape.py）
```
kv_pages(prefix present)= 2048
storage_hit(final_pages)= 2048
mamba boundary= 2048
=> live shape storage_hit > 0: True
```
2048 KV 全 present + 尾 checkpoint → storage_hit=2048>0（满足用户 live 验收）。

### 3.5 RED 证明（守卫价值）
临时把 reverse-scan 改成"只查最后 present 页"（`prefix_len = kv_pages` 单次检查）→
`test_v2_trailing_pages_reverse_scan_narrow_cases` FAILED：
```
AssertionError: 0 != 16
```
证明若未来回退到协调人描述的错误行为，新测试会 RED。恢复后 73 测试全 GREEN。

### 3.6 git 状态
- reverse-scan 逻辑 = HEAD（e281df3635, 2026-08-31），`git diff HEAD` 该逻辑零改动。
- extent_file_backend.py 工作区 diff 全为前期 epoch 未提交工作（docstring/IO helper/指标），
  非本轮。

## 4. summary

**核心发现：用户裁决要求修复的语义，现行 `batch_exists_v2` 已经实现。** 三 case 期望值
（16/32/0）、live 形状（>0）、upstream 对齐全部实测通过。没有可做的生产逻辑修复——强行改
反而是回归。因此本轮把用户规格钉成回归测试（GREEN，且有 RED 证明的守卫价值），并如实汇报
"无需改动"，不伪造 no-op diff。

**live storage_hit=0 的真因（对齐 e24 结论）**：不在 `batch_exists_v2` 的 TRAILING_PAGES
语义（那是对的），而在**写侧 mamba checkpoint 注册/可见性**与 KV 前缀覆盖率：
- mamba `BACKUP_STORAGE` 只注册 `node.hash_value[-1]`（写入时刻 node 最后 1 页）的 `.mamba`
  key（mamba_component.py:752-763）；
- 读侧 PREFETCH 用 `keys=["__placeholder__"]`（mamba_component.py:765-774），`batch_exists_v2`
  从 `kv_pages` 反向找"KV 前缀内最近的已持久化 checkpoint"——这是用户裁决的正确语义；
- node65/node29 的 KV longest-prefix 实测停在 1027/1024（`sidecar_hits {"kv": 1027}`），
  `final_pages = min(kv_pages, boundary)` 被 kv_pages 顶死；且链上 checkpoint（node 尾页
  2047）不在 present 前缀内 → boundary=0 → storage_hit=0。**这正符合用户规格**——当 KV 前缀
  内没有已持久化 checkpoint，clamp 到 0 是对的。真因是 KV 前缀本身停在 1027（或 checkpoint
  位置不在 present 前缀内），不是 TRAILING_PAGES 语义错。

用户"反对 (b)"的论证正确且与现行语义一致：不把 checkpoint 复制绑定到每 page key，只持久化
真实存在的 checkpoint，查询找前缀内最近 checkpoint。**现行 reverse-scan 正是这个语义。**

## 5. followups

- **live KV 前缀停在 1027 的成因**（node65/node29）是剩余真因候选：KV 写 2048 但 longest-
  prefix 只到 1027（KV 总量 93389==Σn_pages 无聚合丢失）。需在写侧/注册路径核查 node65 的
  1028 页为何 absent（radix 前缀共享 / 分支 / 批量切分），建议 tester 集成层复核。
- 若确认需"让 checkpoint 更常命中"（增大 checkpoint 注册频率），属写侧 mamba_component 改动，
  用户已裁决反对 (b)，不在本轮范围。
- 全门：extent 73 测试 GREEN（71 既有 + 2 新增）。集成/性能层由 tester 排期。

## 6. open_issues

- 无生产代码改动——这是有意的：实证表明规格已实现，改动即回归。协调人若仍要求改
  `batch_exists_v2`，需指出具体分歧 case（现有 192 配置穷举无分歧）。
- live KV 1027 上限的写侧根因未闭合（见 followups），是 storage_hit=0 的剩余真因。
