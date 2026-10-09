# p2io-tester-e7d

- **工作标题：** p2io-tester-e7d
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7d.md`：**
done — **NEVER_BACKED（96% 的 recompute rid）主导；机制 = host 内存压力下 write-back 子树无备份丢弃（Z3），非 extent recycle / key 不可达**。现有日志足以定案主因，但"未写 vs 写过再丢"的百分比需补埋点才能细分。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e7d.md`：**
**裁决：L3 survivability 严重不达标（当前负载估计 19-62% 区间 << 95% 目标），主因 = host 内存压力导致的 write-back 无备份丢弃（Z3），非 key/查询正确性，非 extent recycle（虽不可见但非首因）。**
证据链闭环：
1. 78 个 recompute rid 中 75 个（96%）NEVER_BACKED（storage_hit=0），只有 0 个 FULL_PRESENT_NOT_MATCHED——排除"写了但查不到"
2. 59 次 Z3 drop（整链无备份丢弃）正是"没写"的直接来源，且 e7b 是 e5 的 2×（29→59），与本轮 full-chain 覆盖崩坏吻合
3. 宿主池长期近满（promotion_transfer 显示 full_free<2000、full_evictable≈40000）→ D→H backup 失败 → 整链 drop
4. 26 个 NEVER rid 是 ≥20910 token 的整链请求——正是 READY 池该服务的 full-chain，全被宿主流失
**与本任务链的关系**：这解释了 e7c"NO_L3_FULL 主导"的根因——不是 READY 池策略问题，是 **L3 里没有完整链是因为 write-back 宿主压 drop**。修复方向在 write-back/宿主 eviction 的 L3 持久化先行，而非 READY 池水位。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e7d.md`：- 数据源：`/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（run-20260901-115548）+ e5/e7 引擎日志对照
- 事件代码溯源：`unified_radix_cache.py:905-935`（write_back Z3 drop 发射点）、`extent_allocator.py`（ring recycle 无日志）、`extent_file_backend.py`（仅创建/清理日志）
- 注意：Ready Horizon [P3] 埋点（ready_pool/ready_stage）受新增持久约束保护——本分析未删改任何埋点；**补埋点清单全部为新增事件/追加字段，向后兼容**（已遵守约束）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7d.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7d.md`; SHA256 `27f8cfb5caa6a68042ab6fcada78bd891c03c9e995f413f12ed434b2ea5c5796`; source state `tracked`
