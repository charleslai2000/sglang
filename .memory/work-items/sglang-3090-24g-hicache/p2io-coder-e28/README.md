# p2io-coder-e28

- **工作标题：** p2io-coder-e28
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-coder-e28.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-coder-e28.md`：**
确定性层（KV spec→commit→exists 三向恒等、写链==查询链逐页字节等）全过后，live 层 storage_hit=0 的剩余矛盾定位到 **mamba 边界钳制**：live 日志 kv_hit=0 + sidecar 只含 {'kv':N}（mamba 永不在）只能是 mamba PREFETCH transfer 被按 ALL_PAGES 读（placeholder keys + 默认策略）。修复 = placeholder-key transfer 强制 TRAILING 扫描（当前代码可复现该缺陷，fix 后实证消除）。修复前后对比：`ALL_PAGES(placeholder)` kv_hit 0→20550/9，mamba 进入 sidecar；显式 TRAILING(placeholder) 行为不变。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-coder-e28.md`：- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` — `batch_exists_v2`（648-651，唯一定位点）：placeholder-key 守卫。
  - 改动：ALL_PAGES 分支加 `not placeholder_keys` 条件。当 transfer.keys 全为 `"__placeholder__"`（mamba_component/swa_component PREFETCH 构建时真实 keys 未知，只占位）时，即使 hit_policy 被重建丢失而回落到 `PoolTransfer` 默认 ALL_PAGES（hicache_storage.py:112），也强制走 TRAILING 扫描。
  - 理由：mamba/SWA 池只写 node-last checkpoint（mamba N=1，SWA N>1）；TRAILING 扫描按节点边界命中。ALL_PAGES 扫描从页 0 开始逐页查 `_component_key(MAMBA, keys[i])`，mamba 只存末页 → 第一个 KV-only 页即失败 → boundary=0 → kv_hit=0（正是 live 签名）。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — 2 个新测试（`TestExtentV2`，706/749）：…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e28.md` → `.memory/phase2-hicache-design/work/p2io-coder-e28.md`; SHA256 `40ae1c50546d6b3a037a37867b807f87026a2ce6e65f13c8a8988e157968f035`; source state `tracked`
