# p2io-tester-e8

- **工作标题：** p2io-tester-e8
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e8.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e8.md`：**
**判定：sha16 分歧由 stale-state restore 导致 = 证据不足，倾向反驳（高度可能为非确定性回归）。**
逐项对照任务要求：
1. prefix token hash：b1c-S1-L0-V1 的 ids 定长 20911（provenance 记录），e7/e5 全部 turn prompt_len=20911 逐 turn 一致；无截断/错 prefix 证据
2. KV key/generation：uses extent allocator 的 key（`node.hash_value`），generation 校验在位
3. durable frontier：storage_restored 标记在 ACK/prefetch-loaded 侧成对维护（unified_tree_core mark_storage_restored）
4. restored KV bytes：extent generation 校验 + 不做事后逐字节持久化哈希（无此项——但不需要：generation 不匹配=miss 丢弃）
5. **Mamba/GDN sidecar generation/hash（重点）**：sidecar 与 KV 同 key、同 generation、同 ACK 原子伺服；prefetch 侧 loaded 判定 + host_value 挂载在同一 commit；LOAD_BACK 同 transfer——**无"KV 新 + Mamba 旧"的构造路径**。架构缺口=**sidecar 无独立 generation/世代号**
6. ttft 关联：e7 a1-t12-restore ttft 9.95s（命中 device 15953 + host 1291 = 66% 命中，fast path）与输出身份无因果关系——f6b66de0 同时是 e7 的 fresh grow 输出
**发现的意义**：这实际上是 evidence 有力度的"非 corruption 证据"——异常值全部落在 fresh-compute 可达集合内，restore blob 未伺服错误字节（否则输出会在流形外）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e8.md`：- 分析对象：e7 证据 `/tmp/p2io-e7/evidence/` + 引擎日志 `/tmp/p2io-e7/engine-p2io-m4t-e7.log`；基线 m4f/m4t/e4/e5 同构证据
- payload 族源：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/qwen35-payloads/`（b1c-S1-L0-V1.payload.json + meta + provenance）
- 驱动 sha16 定义：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/agent_driver.py:230` / `common.py:226`
- restore 路径源码（sidecar 处理）：`python/sglang/srt/mem_cache/unified_radix_cache.py`（backup/prefetch 侧 sidecar transfer）、`unified_cache/components/mamba_component.py:740-840`、`flexible_extent backend extent_file_backend.py:587-665`、`unified_tree_core.py build_load_back_spec`
- 本探针在会话内联脚本直析（禁忌合规：全行级 grep / 局部 Read / 小 Python 解析）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e8.md` → `.memory/phase2-hicache-design/work/p2io-tester-e8.md`; SHA256 `5a2b98d84582cedf6e00abb1873111a4b0cb238aea5e96b82986b408c658fef6`; source state `tracked`
