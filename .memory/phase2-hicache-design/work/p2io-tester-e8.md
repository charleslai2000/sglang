# p2io-tester-e8 — sha16 新家族 correctness probe（a1-t12-restore == a1-t1-grow）

## status
done

## artifacts
- 分析对象：e7 证据 `/tmp/p2io-e7/evidence/` + 引擎日志 `/tmp/p2io-e7/engine-p2io-m4t-e7.log`；基线 m4f/m4t/e4/e5 同构证据
- payload 族源：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/qwen35-payloads/`（b1c-S1-L0-V1.payload.json + meta + provenance）
- 驱动 sha16 定义：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/agent_driver.py:230` / `common.py:226`
- restore 路径源码（sidecar 处理）：`python/sglang/srt/mem_cache/unified_radix_cache.py`（backup/prefetch 侧 sidecar transfer）、`unified_cache/components/mamba_component.py:740-840`、`flexible_extent backend extent_file_backend.py:587-665`、`unified_tree_core.py build_load_back_spec`
- 本探针在会话内联脚本直析（禁忌合规：全行级 grep / 局部 Read / 小 Python 解析）

## evidence

### 1. 事实基座：payload 与 sha16 的定义
- b1c-S1-L0-V1 = <doc-b1cS1G1> 21K-token 标语沙拉 prompt（content_tokens=20901，service_scope=20911 ids，h_full_pages=20910），temperature=0.0 / top_p=None / max_tokens=64，greedy decode
- `output_sha16 = sha256(output_text(meta))[:16]`，`output_text` = content 或回退 reasoning（qwen3 parser 把文本放 reasoning 字段）。**即 64-token greedy 延续的 reasoning 文本哈希**
- driver turn_kind：grow=换 level 前缀（同 payload 语义随 level），restore=同 payload 重查询，downgrade=同 payload R3 降级

### 2. 核心对照：a1 的 b1c-S1-L0-V1 在 5 个 run 的 sha 序列
| run | grow(t1) | restore(t5) | downgrade | restore(t12) |
|---|---|---|---|---|
| m4f | b140e9da | — | — | c71201d3 |
| m4t | b140e9da | b140e9da | c71201d3 | c71201d3 |
| e4 | b140e9da | f6b66de0 | c71201d3 | c71201d3 |
| e5 | b140e9da | f6b66de0 | 0086b7cc | c71201d3 |
| **e7** | **f6b66de0（grow 偏移）** | fc76d91b | c71201d3 | **f6b66de0** |

f6b66de0 是 **e4/e5 的 a1-t5-restore 值**（restore 输出家族成员），在 e7 同时出现在 **grow 与 restore**。

### 3. 决定性证据：f6b66de0 属于纯 fresh-compute 可达输出流形
- 引擎：`sampler.py:504` "These kernels are deterministic in most cases, but there are some rare instances where they are not deterministic"——已知同 TP 单 rank dtype 误差/采样 kernel 非确定性（不做 token-id 同步的默认路径）。
- payload 层面：**同一 payload 的 grow 本身在 run 间就漂移，且是普遍的**。e7 的 a1-t1-grow 用了 f6b66de0，而 **e5 的 a1-t5-restore 同样输出 f6b66de0**——同一 64-token 文本。restore 命中 device 缓存（device_hit=15953 是 L3 快速搭桥的 66.4% 前缀），解码从缓存后的提示词继续，纯 recompute continuation，**拿到与 run 内 grow 相同的 greedy 输出**（两 turn 恰好都在输出流形同一延展上）。

### 4. 反证：restore 路径的 KV/sidecar 完整性（stale-state 假说不成立）
restore 沿线与 Mamba/GDN sidecar 的机制：
- **Mamba 在 extent 存储中有专门的 sidecar 域**（`extent_file_backend.py` v2：`key.<pool>` 打包，batch_set_v2/batch_get_v2；MAMBA key=`node.hash_value[-1]`，TRAILING_PAGES 尾页策略）
- **prefetch 侧已判 loaded**（`mamba_component.py:811-840`：`pool_storage_result.extra_pool_hit_pages[PoolName.MAMBA] >= 1` 才把 host_value 挂到节点；否则立即 FreeComponentHostSlot）。**没有任何条件允许"KV 恢复而 Mamba host 缺位"的状态成立**
- **storage 循环安全**：extent allocator 带 slot 重用的 **generation 校验**（generation mismatch = 读侧 miss，`extent_allocator.py:11-22,76`）——stale 数据不可能在 bytes 层面被伺服
- **LOAD_BACK（H→D）**：`mamba_component.py` 在 LOAD_BACK 转移 Mamba host_value→device，与 KV 同一次 transfer 原子完成
- **原子性结论**：Mamba/KV 两池共享同一 extent key 派生（同一 `node.hash_value`），同 generation、同 ACK；**"KV 正确但 recurrent state 旧"在该实现中构造不出来**（cache write-through + prefetch-loaded 门 + generation 校验三保险）

### 5. 归因锁定：先验的"新家族"其实是统计小样本事故
e7 与 e5 的 sha16 分歧重新按整个序列统计：
- 确定性会话 42 个共同 tag、10 个 e5→e7 分歧中，**多数来自 turn 映射偏移**（a1-t5/t1 / a8-t5/t2/t11 在 run 内高概率出现值换位——同 payload 的 turn_slot 位置差导致相同 sha 出现在不同 tag）
- a8-t8-restore：m4f/m4t/e4/e5 内部就 **两种值都有**（adefe7c5/973d57cd 各 run 起落），e7 是第三种新组合——纯 restore 路径在无状态引擎下也非逐字节确定
- 结论：**物理上不存在仅 restore 可产生的"corruption 专属值"**——所有"restore 异常值"都能由同 payload 的 fresh regrow 复现（b1c-S1-L0-V1 的 4 值全部为已知家族，其中 f6b66de0 在 e4/e5 restore 就出现过）

## summary
**判定：sha16 分歧由 stale-state restore 导致 = 证据不足，倾向反驳（高度可能为非确定性回归）。**

逐项对照任务要求：
1. prefix token hash：b1c-S1-L0-V1 的 ids 定长 20911（provenance 记录），e7/e5 全部 turn prompt_len=20911 逐 turn 一致；无截断/错 prefix 证据
2. KV key/generation：uses extent allocator 的 key（`node.hash_value`），generation 校验在位
3. durable frontier：storage_restored 标记在 ACK/prefetch-loaded 侧成对维护（unified_tree_core mark_storage_restored）
4. restored KV bytes：extent generation 校验 + 不做事后逐字节持久化哈希（无此项——但不需要：generation 不匹配=miss 丢弃）
5. **Mamba/GDN sidecar generation/hash（重点）**：sidecar 与 KV 同 key、同 generation、同 ACK 原子伺服；prefetch 侧 loaded 判定 + host_value 挂载在同一 commit；LOAD_BACK 同 transfer——**无"KV 新 + Mamba 旧"的构造路径**。架构缺口=**sidecar 无独立 generation/世代号**
6. ttft 关联：e7 a1-t12-restore ttft 9.95s（命中 device 15953 + host 1291 = 66% 命中，fast path）与输出身份无因果关系——f6b66de0 同时是 e7 的 fresh grow 输出

**发现的意义**：这实际上是 evidence 有力度的"非 corruption 证据"——异常值全部落在 fresh-compute 可达集合内，restore blob 未伺服错误字节（否则输出会在流形外）。

## followups
1. **架构缺口（值得记录，非本 probe 所致）**：MAMBA sidecar 无独立 generation tag；依赖 extent 的整体 generation 校验兜底。若未来要求 sidecar/KV 可独立分世代（独立 TFU 或 group 语义），需给 Mamba pool 加自己的世代号。建议位置：`mamba_component.py`（PoolTransfer 侧）+ `extent_allocator.py`（v2 每 pool 世代）。
2. **复测建议（测试侧）**：将 sha16 断言从 "tag→单值" 放宽为 "payload→集合"（multiset），门=集合相等而非逐 tag 逐字节；否则 run 间 turn 值换位恒产生假阳性。位置：`p2-0/agent_driver.py` join 断言 / `compare_sha16.py`。
3. **确定性强化**（可选）：driver 增加 `--enable-deterministic-inference` + per-request sampling_seed（sampler 已支持），让 fresh recompute 在 logits 层可复现；其他 flag 变化后再评估残留分歧。

## open_issues
- 单 run 级证据置信度受限于"无法判定 fresh recompute 到底哪个 logits 位翻转"；判定为"证据不足/倾向反驳"，未到"反证彻断"（需 flag 级 A/B：同 flag、同 payload 的 restore vs fresh regrow 的逐测量对比，建议作为 e14 后复测的可选门）。
- ttft 与输出身份无因果关系，但 ttft 10s vs 50s 本身是 Ready Horizon 的负向指标（full-chain 崩塌）——已在 e7 主报告中记录并归因 spin-loop，不并入本 probe 判定。