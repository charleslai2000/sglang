# P2-1 收尾：K=16/32 scale smoke — tester e19 报告

## 1. status

**blocked（启动前置 md5 核对失败）** — 磁盘清理完成（9.4G → 173G 可用），但 **e17 基线引擎文件已被 coder 的 M1/M2 修复覆盖**（unified_tree_core.py / unified_radix_cache.py 于 2026-08-31 06:31:36 部署，恰在实验启动前）——"启动前 md5 核对"前置不满足，按指令停表，请求协调人裁决：恢复 e17 文件或授权用新代码跑 smoke。

## 2. artifacts

- **清理结果**：df /data 9.4G/96% → **173G/8%**（释放 ~164G）；删除 13 个 ns（p2b0-01/02/0a/0b/1c/1d、t38rs3/t38f1/t38sb/t38patch3/t38f2/t38rs2/t38rs），全部 find -delete
- **0c 完好**：15G、**273,040 files**（清理前后一致）✓
- /root/evidence-* 未动 ✓；p2b0-1b 为 4.0K 空壳（不在授权集，保留）
- /data/l3 现存：0c（15G）、1b（4K 空壳）、2a（fresh，0 文件）
- /root/evidence-p2b0-2a/ 已建（空）；引擎未启动（md5 前置失败）

## 3. summary

### 3.1 md5 前置核对结果（失败项）
| 文件 | e17 基线（指令要求） | 当前磁盘 | 状态 |
|---|---|---|---|
| unified_tree_core.py | fb931e5c | **a2721792** | ✗ 已被覆盖（06:31:36 部署） |
| unified_radix_cache.py | d992a972 | **b77e23ac** | ✗ 已被覆盖（06:31:36 部署） |
| scheduler.py | 7305eb0b | 7305eb0b | ✓ 未变 |
| test_storage_regression.py | 3378313d | 95037123 | ✗ 已变（随新修复） |

- 部署时间 2026-08-31 06:31:36——**在实验启动前**（非中途），即协调人"中途收到通知以本指令基线跑完"的情形未触发，但**基线文件已不可用**
- coder 部署 = M1/M2 修复（协调人预告的并行工作）——sanity_check 仍存在（新 tree_core）

### 3.2 环境状态（其余全就绪）
- 磁盘 173G 可用 >> min_free 10G 阈值 ✓
- 0 残留 / GPU 15MiB ✓；/data/l3/p2b0-2a fresh 就绪 ✓

## 4. followups

1. **协调人裁决**（唯一阻塞项）：(a) 恢复 e17 文件（fb931e5c/d992a972——需协调人/coder 回滚或提供副本）后按原设计跑 smoke；或 (b) 授权以当前代码（a2721792/b77e23ac/7305eb0b = M1/M2 修复版）跑 smoke——需确认该版本与 e17 的归因基线兼容（若 M1/M2 改了 restore 行为，五项确认与 e17 对比口径需注明）
2. 裁决后我立即执行：K=16 × 8 turns（128 请求）+ K=32 × 8 turns（256 请求，25 分钟护栏）——fresh ns 2a，五项确认 + 归因随 K 变化表 + frontier 深度对比（8/16/32）+ 判据
3. 磁盘空间足够（173G），K=32 写链无容量风险

## 5. open_issues

- e17 基线被覆盖（coder 06:31:36 部署）——smoke 基线选择待协调人裁决（恢复 e17 vs 用新代码）
- 无其他阻塞
