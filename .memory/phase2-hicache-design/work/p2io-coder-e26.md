# p2io coder e26 — 最小确定性闭环打穿：BRANCH 4（问题在上游）

status: done（闭环 100% 通过，判定 BRANCH 4；backend 层无 bug）

## 1. status

按用户强制切换"停止 M4T 长测，把 storage_hit=0 压成最小确定性闭环打穿"，完成了 2048-page
node 的最小闭环，并给出四分支判定：

- **闭环 100% 通过**（v1 + v2 双 surface）→ **BRANCH 4：全部 2048 PASS，问题在 UnifiedRadix
  上层 node/prefix 构造**。
- extent backend 的 index 注册、batch_exists 前缀扫描、batch_get 字节回读在跨 1024 batch
  边界下全部正确。
- 新增 2 个跨 1024 batch 边界单测（75 测试全 GREEN），并完成 RED 证明（prefix-scan 回归 →
  `1024 != 2048` 复现 live 症状）。
- 生产代码零改动（实验改动已逐字节还原）。

## 2. artifacts

### 新增单测（test/registered/unit/mem_cache/test_extent_file_backend_unit.py）
- `TestExtentClosedLoop2048.test_v1_2048_cross_batch_boundary_round_trip`（L1370）——
  v1 surface：2048-page node 两批 batch_set_v1(1024) → index 2048/2048 → batch_exists=2048 →
  batch_get_v1 全 2048 字节恒等。
- `TestExtentClosedLoop2048.test_v2_2048_cross_batch_boundary_round_trip`（L1410）——
  v2 surface（live 读路径）：两批 batch_set_v2(1024) → batch_exists_v2=2048 →
  batch_get_v2 全 2048 字节恒等。
- 均跨 STORAGE_BATCH_SIZE=1024 边界，实打实 MHA host pool（fp16, page_size=2, L2/H2/D4）。

### 探针（3090-dev/，非生产代码，保留）
- `p2io_e26_closed_loop.py` — 三份导出（write keys 0-2047 / query keys 0-2047 / index hit
  bitmap）+ 四分支判定 + v1/v2 双 surface 闭环。

### 生产代码
- **零改动**（实验期临时改动已逐字节还原，见 evidence 3.4）。

## 3. evidence（实测，真实输出）

### 3.1 三份导出对照 + 四分支判定（p2io_e26_closed_loop.py）

```
batch_set_v1[0:1024] ok: True (1024)
batch_set_v1[1024:2048] ok: True (1024)
write_keys: 2048 (0..2047)          <- 写 key 全覆盖
query_keys: 2048 (0..2047)          <- 查询 key 全覆盖
index hit bitmap: 2048/2048 present <- index 全命中
batch_exists(query 0..2047) = 2048
batch_get_v1 ok count: 2048/2048, failed: []
byte-mismatch pages: 0 []
VERDICT: BRANCH 4: all 2048 PASS -> problem is upstream (UnifiedRadix node/prefix construction)
CLOSED LOOP PASS: True
v2 batch_set_v2[0:1024] ok: True
v2 batch_set_v2[1024:2048] ok: True
v2 batch_exists_v2(query 0..2047) = 2048
v2 batch_get_v2 ok count: 2048/2048, failed: []
v2 byte-mismatch pages: 0 []
V2 CLOSED LOOP PASS: True
```

### 3.2 四分支对照表

| 分支 | 判据 | 实测 | 结论 |
|------|------|------|------|
| 1 查询生成 bug | query keys 只有 1024 | query_keys=2048 | 排除 |
| 2 第二批 commit bug | query 2048 但 index 前 1024 | index 2048/2048 | 排除 |
| 3 prefix-scan bug | index 2048 但 exists 只返 1024 | batch_exists=2048 | 排除 |
| **4 上游 node/prefix 构造** | 全部 2048 PASS | 全 PASS（v1+v2） | **成立** |

### 3.3 单测门（75 全 GREEN）

```
Ran 75 tests in 0.326s
OK
```
（71 既有 + e25 2 个 trailing + e26 2 个 2048 闭环 = 75）

### 3.4 RED 证明

临时把 `batch_exists` 前缀扫描在 1024 处截断（模拟 BRANCH 3 prefix-scan bug）→
`test_v1_2048_cross_batch_boundary_round_trip` FAILED：
```
AssertionError: 1024 != 2048
```
与 live 症状（storage_hit 卡在 1024/1027）一致——证明单测有真实守卫价值。还原后
`git diff`/字节比对确认 extent_file_backend.py 与实验前一致（`self._allocator.commit(
storage_keys, refs, passed)` 单调用、`batch_exists` 前缀扫描无截断）。

## 4. summary

**最小确定性闭环打穿结论：extent backend 层无 bug，storage_hit=0 的问题在上游。** 用与 live
完全相同的写模式（`_page_backup` 按 STORAGE_BATCH_SIZE=1024 切两批 batch_set_v1）对 2048-page
node 写入，index 全 2048 命中、batch_exists 返回 2048、batch_get 全字节恒等；v2 surface（live
读路径 batch_exists_v2/batch_get_v2）同样全过。三份导出（write/query/index bitmap）逐项对照，
四分支判定落在 BRANCH 4。

这坐实了 e24/e25 的结论：batch_exists_v2 的 TRAILING_PAGES 语义正确（e25 已钉死）、index
注册/提交正确（本闭环）、跨 batch 边界读写正确（本闭环）。live storage_hit=0 的根因在
UnifiedRadix 层 node/prefix 构造——即写侧实际写入的 chain（node.hash_value）与查询侧
`_storage_hit_query` 重算的 chain（或可见 KV 前缀）不一致（node29/node65 KV 前缀卡在
1027/1024，mamba checkpoint 只在 node 尾页），backend 收到的是本就覆盖不全的查询。

## 5. followups

- **上游定位（UnifiedRadix 层）**：为何 2048-page node 写全后查询只见 1024/1027 KV 前缀。
  候选：query chain 的 `get_hash_str` 重算与写入 `build_storage_backup_spec` 的 hash_value
  在 page 1027/1024 处分支；或 node 增长后旧查询链前缀变短。建议 tester 在集成层对
  node65/node29 的 write_seed page0/1 hash vs 查询 keys[:8] 做 64-hex 逐页对照，找首个分歧页。
- 若上游确认需改 checkpoint 注册频率/位置（mamba 侧车），属 mamba_component 写侧，用户已
  裁决反对 (b)，不在此范围。
- 全门：extent 75 测试 GREEN；集成/长测待闭环判定通过后由 tester 排期（用户裁决：判定通过
  前禁跑 8-10 分钟压测）。

## 6. open_issues

- 无生产代码改动（有意的；backend 层证据充分，改动即回归）。
- 上游 UnifiedRadix 的 node/prefix 构造分歧页（1027/1024）未在本轮闭合，为 storage_hit=0
  剩余真因，需上移到 UnifiedRadix 层继续排查。
