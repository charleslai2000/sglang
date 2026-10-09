# phase2-hicache-design-architect-e10 — K=32 evict 锁链死锁分析（第三轮，输出修复方案待批准）

## status

done — 只读分析完成（未修改任何文件）；K=32 复发根因定位 + evict 语义确认 + 修复方案（3 候选 + 推荐 A + 风险 + 验证设计）落盘。证据全部来自本机代码（file:line）与 3090 远端只读 ssh（/root/engine-p2b0-2a.log 崩溃现场 + 1i/2a 对比）。

## artifacts

- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e10.md`
- 崩溃现场（远端只读，未拷贝）: `/root/engine-p2b0-2a.log`（K=32，8859 行）+ `/root/evidence-p2b0-2a/`（run-20260831-070916）
- 对比现场: `/root/engine-p2b0-1i.log`（K=8 e17 终判健康 run）
- 本地代码（M1/M2 版 md5: unified_tree_core.py a2721792 / unified_radix_cache.py b77e23ac / scheduler.py 7305eb0b，与 tester-e19/e20 记录一致）

## evidence

| # | 事实 | 证据 |
|---|---|---|
| E1 | 崩溃分配: `Available full tokens: 16384 (full_available_size=10 + full_evictable_size_=16374)`，alloc 2048 失败 | engine-p2b0-2a.log:8774, 8804 |
| E2 | walker 失败: `write_back: backup failed ... but subtree drop declined (node locked); root node 1600 stays device-resident until host space frees` ×3（07:14:35-36，崩溃前 2s） | engine-p2b0-2a.log:8766, 8769, 8771 |
| E3 | 崩溃 dump 树: 锁链 [9](0)→[19](3)→[22](6)→[1502](1)→[1607](2038)→[1608..1614](2048×7) 全部 full_lock=1，sum=16384；[1600] 16374 full_lock=0 full=yes mamba=yes，子 [1606](1028)→[1603](1020)→[1604](2048) 全 full=no；[1585..1601] 链 14 节点全 full=no | engine-p2b0-2a.log:8809-8842 |
| E4 | [1600] 子树来源: 2e0e007d restore 07:13:52 `completed=20480 matched=10 loaded=20470`（= [1600]+子链 16374+1028+1020+2048=20470 精确吻合）——崩溃前 43 秒从 L3 读出的链 | engine-p2b0-2a.log:8554-8562 |
| E5 | 在途 prefetch 压 host + 锚定 victim: 8b2fb128 prefetch_issued 20910 @07:14:34，io_finished 16384 @07:14:37（崩溃后）；fd99588b frontier_wait node=1600 @07:14:31；之前 2e0e007d 27811 @07:13:27 亦曾压 host（07:13:52 才完成） | engine-p2b0-2a.log:8724-8742, 8746, 8760-8762, 8842 |
| E6 | 锁粒度: cache_unfinished_req 每 chunk `_dec_req_lock(req)` + `inc_lock_ref(new_last_node)`（新链=匹配前缀+已存 chunk 全链）；锁到请求结束才放（cache_finished_req `_dec_req_lock`） | unified_radix_cache.py:1099-1113, 995 |
| E7 | 锁语义: FULL 路径锁沿 node→root 全部祖先（`acquire_component_lock` 循环 discard evictable_device_leaves），dec 时 lock_ref→0 才回叶集 | full_component.py:277-301, 303-339 |
| E8 | walker 候选集 = `evictable_device_leaves`（`_is_device_leaf`: lock_ref==0 且无设备子层）；锁链节点因 lock_ref≥1 永不成候选 | full_component.py:190-224; unified_tree_core.py:1785-1801 |
| E9 | drop 拒绝: `drop_subtree_no_host` 在 `any(cd.host_lock_ref > 0 ...)`（根）或后代 lock_ref/host_lock_ref>0 时拒绝；在途 prefetch 的 anchor 锁（`inc_host_lock_ref(last_host_node_id)` @ prefetch_from_storage:1981）→ [1600] host_lock_ref≥1 | unified_tree_core.py:1294-1337; unified_radix_cache.py:1978-1982 |
| E10 | e11 hollow 前提: `elif self.tree_core.is_storage_persisted(node_id)`；标志只在 L3 写回 ack drain 置位（`advance_storage_persisted`/`_promote_persisted_subtree`），无任何其他置位点；restore 路径（`_handle_prefetch_result` → `insert_host`）从不标记 | unified_radix_cache.py:823-832; unified_tree_core.py:1964-2018, 2203-2244（insert_host 1900 段） |
| E11 | 定量对比: "stays device-resident" 警告 K=8 e17（666s 健康）= **0 次**；K=16（1112s 健康）= 10 次（靠 host 及时释放存活）；K=32（387s 崩溃）= 10 次（441×5, 579, 606, 1600×3，末 3 次在崩溃前 2s） | 远端 grep 1i/2a 日志 |
| E12 | M1/M2 范围: 部分写 ack 完整性 + 晋升追溯化，不触碰 evict/lock 路径（coder-e13 报告）——非本次复发原因 | coder-e13-01.md |
| E13 | split 标志丢失（同族问题）: `_split_node` 不传播 storage_persisted/acked/written（仅 write_through_pending_id/load_back_pending_id/组件锁），分裂后父节点持久性标志落后于 L3 副本现实 | unified_tree_core.py:1093-1133 |
| E14 | e11 对 K=8 有效的机制: e15 受害者 [167] 链是引擎 ack 过的 persisted 链（hollow 前提成立 → e16/e17 中 hollow 确实触发，e16 node 511 即 hollow 残留态） | coder-e11-01.md; tester-e16.md:48-52 |

## summary

### 结论（一句话）

K=32 OOM = **e11 hollow 驱逐的前提（`is_storage_persisted` = 本引擎 L3 写回 ack 标志）不覆盖"从 L3 restore 回来、本引擎从未写过/ack 过"的链**：崩溃 dump 中唯一 evictable 设备叶 [1600](16374) 恰是 43 秒前从 L3 restore 的链（E4），L3 副本真实存在但标志为 False → backup 失败（host 被在途 prefetch 占满，E5）+ drop 被拒（在途 prefetch anchor host 锁，E9）+ hollow 拒绝（E10）→ 回收 0 → 2048 分配失败 → RuntimeError → SIGQUIT。M1/M2 与 evict 路径无关（E12），非复发原因；e11 只覆盖"引擎 ack 过"的链，故 K=8 有效（E14）、K=32 复发。

### Current Architecture（当前架构——事实层）

1. **锁生命周期（chunked prefill）**：准入时锁匹配前缀（schedule_policy），每 chunk 在 `cache_unfinished_req` 内 dec 旧链 + inc 新链（E6），FULL 组件路径锁沿 last_node→root 全部祖先（E7）；锁集合单调累积、持有到 `cache_finished_req`。**锁到请求结束，不是 chunk 结束**——chunk 完成后请求仍要在后续 chunk 与 decode 中读这些 KV，释放即正确性事故。崩溃锁链 [9]→…→[1614] sum=16384 = 1 个在途请求 8×2048 chunk + 10-token 共享前缀，lock_ref=1 全链，**合法 working set，非泄漏**（与 e11 定案一致）。
2. **walker 语义**：候选集 = `evictable_device_leaves`（设备叶 + lock_ref==0，E8）。锁链节点根本不在候选集——不是"跳过 locked 子树"，而是**永不成候选**（`inc_lock_ref` 时即 discard，E7）。dump 证实 walker 找到了唯一候选 [1600]（16374），失败在 backup/drop/hollow 三段而非叶发现。
3. **e11 fallback 链**（`_evict_components` 循环）：D→H backup 失败 → `drop_subtree_no_host` → `is_storage_persisted` → hollow → 全败则 warning 后跳过。`storage_persisted` 仅由 L3 写回 ack drain 置位（E10），restore 路径不标记。
4. **K=8 vs K=32 路径差异**：e15 受害者 [167] 链是引擎 ack 过的链（hollow 前提成立，E14）；K=32 受害者 [1600] 是 43 秒前 restore 的链（标志 False）。并发形态差异放大触发概率：K=32 爆发入队（pending 776K）→ 背靠背 20-28K-token prefetch（2e0e007d 27811 + 8b2fb128 20910）压满 49152 host 池 + anchor 锁钉住 victim；K=8 e17 节奏平缓，该路径 0 次出现，K=16 出现 10 次但 host 每次及时释放（E11）——**该路径是潜在死锁，K=16 靠运气躲过，K=32 击中**。

### Issue-Forces（结构力冲突）

- **F1：持久性标志落后于 L3 副本现实**。hollow 的安全前提是"本节点 KV 在 L3 有持久副本"，但代码用"本引擎写过且 ack"作代理——restore 链（L3 刚读出，副本必然存在）被排除 → 唯一的合法逃生通道（e11 hollow）在 restore 链上关闭。
- **F2：restore 管线与 evict 管线互相死锁**。restore 需要设备空间（等 DEVICE_QUOTA），同时其 prefetch 材料占满 host（堵死 evict 的 backup 出路）且 anchor 锁钉住 victim（堵死 drop 出路）；唯一不依赖 host 的出路（hollow）被 F1 关闭。
- **F3：单候选脆弱性**。深度 32 下 evictable 空间收敛为单个 16374-token 节点（[1600]），该节点全败 = 回收 0 = 立即 OOM；K=16 的 10 次同形命中只是未收敛到单候选。

### Proposed Architecture（目标——修复方案）

**候选 A（推荐）：L3 持久性谓词覆盖 restore 链（+split 标志传播）**

- 语义修正：hollow 安全前提 = "本节点 KV 在 L3 有持久副本"，统一谓词 `is_l3_durable(node) = is_storage_persisted(node) or is_storage_restored(node)`。
- 标记点：`_handle_prefetch_result`（unified_radix_cache.py:2204-2212）insert_host 成功后标记 `insert_result.inserted_host_node`（fetched 余段单节点，insert_host 语义保证整余段一个节点）；短 fall（shortfall）只标记 completed_tokens 前缀范围（该范围文件真实存在，E4 形态）；hybrid_discard 不标记。
- 三处谓词统一替换（与 e11 gate 一致性模式同构）：hollow fallback（:823-832）、`prefetch_gate_ok`（:1792-1802）、`_wake_frontier_waiters` 守卫（:2426）。
- 同族附带：`_split_node` 传播 storage 标志（E13，分裂父节点的页是原子节点页前缀，子集 L3-backed，继承安全）。
- 改动面：unified_tree_core.py（1 字段 + 1 标记点 + split 传播）+ unified_radix_cache.py（2-3 处谓词）；**不改锁生命周期、不改 walker、不改 L3 写入**。
- 效果：崩溃现场 walker 第一次命中 [1600] 即 hollow 释放 16374 设备 token → alloc 成功；fd99588b 型 frontier spin（E5）随 gate 扩展一并解除（restore 链 anchor 可发 prefetch）。

**候选 B（备选/互补，不建议本轮同改）：evict 侧撤销阻塞性 prefetch**

- 机制：walker 遇 backup 失败 + drop 被拒 + 不 hollowable 且存在阻塞 anchor 时，`terminate_prefetch` 撤销在途 prefetch（现场 07:14:31/39 有 revoke 机制证据）→ 释放 host 材料 + anchor 锁 → 重试 backup。
- 价值：覆盖 A 够不到的"纯 recompute 设备链（无任何 L3 副本）"形态——该形态 hollow 确实不安全，只能靠腾 host。
- 风险：restore→recompute/重排吞吐损失；持续压力下反复撤销 = livelock；中断在途 IO 的语义需核实；调度/恢复策略面大。

**候选 C（拒绝）：调度准入耦合** —— "evictable 被不可 backup 叶主导时暂停 prefill"。崩溃现场的 prefill 请求是合法 working set（锁 16384 必须驻留），暂停只拖垮吞吐不解决根因；冻结参数区敏感。

**候选 D（拒绝）：节点部分拆分 demote** —— 按 2048 切分 [1600] 只备份一段。match/validator 是节点粒度层语义，改动面大且治标（host 不足时任意碎片备份同样失败）。

### Alternatives（对比与为何 A 胜出）

| 维度 | A（标志/谓词） | B（撤销 prefetch） | C/D |
|---|---|---|---|
| 根因匹配 | 直击 F1（逃生通道关闭） | 直击 F2（host 出路） | 掩盖 |
| 改动面 | 1 字段 + 2-3 谓词点 | 调度/恢复策略 + revoke 语义 | 大/策略区 |
| 正确性风险 | 低（标志=副本现实的还原；GC 陈旧与 ack 标志同型，miss 降级 recompute 是已容忍语义） | 中（IO 中断、livelock、吞吐） | — |
| 与 e11/e17 交互 | 同构扩展（gate 一致性模式），hollow 节点形态已被 fb931e5c sanity 接受 | 改变 restore 结果分布（recompute 占比上升，破坏归因基线） | — |
| CHAIN_GAP / F1 / F2 | 不触碰 L3 写入 / ack 路径，零影响 | 影响 prefetch 生命周期计数 | — |

### Impact（对已验证机制）

- **M1/M2**：restore 标记与写回 ack 路径完全独立；M1"部分写 ack 不晋升"保持原样（restore 读取无"部分文件"状态——completed_tokens 前缀即有效范围）。
- **e11 hollow + sanity（fb931e5c）**：restore 链 hollow 产生与 ack-标志 hollow 完全相同的节点形态（设备层空、节点/宿主子树留），sanity 已接受。
- **prefetch_gate_ok / frontier wake**：扩展后 restore 链 anchor 可发 prefetch —— 这正是 fd99588b（frontier_wait node=1600 永久等待、60s 超时 recompute）的修复，与 e11 gate 一致性目标一致。
- **归因基线**：不影响 restore_served/recompute 计数语义（只把本会 recompute/死锁的 restore 变成 hollow+后续 restore）。

### 验证设计

1. **torch-free 单测**（test_storage_regression.py 扩展，镜像 e11 的 RED→GREEN 模式）：
   - restore 标记钉：stub finalize → insert_host → `is_l3_durable` 为真；短 fall 只标记 completed 前缀；hybrid_discard 不标记
   - hollow 回归钉：restore 链叶（backup 失败 + drop 被拒）→ hollow 释放设备层（镜像 StorageBackedHollowEvictionTests，但前提为 restore 标志）
   - 安全钉：纯 recompute 设备链（无 L3 副本）仍不 hollow
   - split 传播钉：persisted 节点 split → 新父继承；gate 一致性钉：restored anchor `prefetch_gate_ok=True` + frontier wake 路径
2. **K=32 复测**：fresh ns 2b（不与 2a 混合），同 driver 配方（8 turns × 32，25 分钟护栏）；判据 = 越过旧崩溃点 387s 无 OOM + 签名 0 + 优雅退场 + 0 残留；观测 = 崩溃前窗口（原 1600×3 警告处）应变为 hollow 事件而非 warning（**建议 coder 在 fallback 命中 hollow 时加一条 info 级日志——现 hollow 不打印，e16 只能靠 sanity 间接证实**）。
3. **K=16 回归**：上次 10 次 walker-wall（E11）应消失或 hollow 化；**K=1 回归**：restore 路径无行为变化（12/12）。
4. 若未来采纳 B：K=32 统计 revoke 次数与 restore→recompute 转化率，确认无 livelock。

## followups

1. 协调人裁决候选 A（推荐）或 A+B 组合；批准后 coder 实现 + 上述单测，tester 跑 K=1/16/32 三级回归。
2. 观测补丁：hollow fallback 命中处 info 日志（验证与未来回归的观测点，同 e11 的 `[P2A]` 探针风格）。
3. 长期（非本次）：storage_existence_cache 的缓存模式填充（buffer 模式已有 pipeline.py:596/734）——让 hollow 谓词直接查 L3 页存在性，消除 GC 陈旧问题；以及 host 池占用核算探针（崩溃时 49152 的在途材料/树 host 值精确构成，本次日志不可全还原）。

## open_issues

- host 池精确占用核算（07:14:35 时 49152 host 的构成：8b2fb128 20910 在途 + 树 host 值 vs evict_host 可回收量）日志不可全还原——不影响修复方向（A 完全不依赖 host），如需精确化属 followups 3。
- `is_storage_persisted` 与 L3 GC 的陈旧语义（文件删后标志仍真 → hollow 后 restore miss → recompute）：与现有 ack 标志同型，本次接受（L3 是缓存，miss 降级为 recompute 是已容忍语义）。
- K=32 崩溃导致 209 failed + 1 orphan（tester-e20）为崩溃截断后果，修复后复测应消失。
