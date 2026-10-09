# phase2-hicache-design-architect-e11 — 第四轮 evict/OOM 残余形态分析（K=32/K=16 同型复发，输出修复方案待批准）

## status

done — 只读分析完成（未修改任何文件）。K=32（989s）与 K=16（470s）同型 OOM 的崩溃机制精确定位（full_lock=2 来源、mid-write 链撞墙、host 满构成、L3 cap 逐出的放大作用与归属判定）；修复候选 3 个（Z3 推荐 / Y 补充 / X 分析后拒绝）+ 验证设计 + 启动脚本工具缺陷定位。证据全部来自本机代码（file:line）与 3090 远端只读 ssh（/root/engine-p2b0-2b-r2.log / r3.log、/root/evidence-p2b0-2b/）。

## artifacts

- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e11.md`
- 崩溃现场（远端只读，未拷贝）: `/root/engine-p2b0-2b-r2.log`（K=32，8318 行）+ `/root/engine-p2b0-2b-r3.log`（K=16，3255 行）+ `/root/evidence-p2b0-2b/`（counters.md、verdict.json×4、p2a-r2-k32.log、p2a-r3-k16.log、MD5SUMS.pre=候选 A 版 6cbd9452/08a1f1ea）
- 本机代码（候选 A 版）: `python/sglang/srt/mem_cache/unified_radix_cache.py`、`unified_cache/unified_tree_core.py`、`unified_cache/components/full_component.py`、`hicache_storage.py`、`storage/file/lru_file_evictor.py`、`allocation.py`、`managers/cache_controller.py`、`3090-dev/test_storage_regression.py`、`/home/charles/Workspaces/homenet/server/gpu/3090-dev/launch-l3-3090.sh`

## evidence

| # | 事实 | 证据 |
|---|---|---|
| E1 | K=32 r2 OOM @989s：`Available full tokens: 11264 (full_available_size=1033 + full_evictable_size_=10231)`，alloc 2048 失败 RuntimeError → SIGQUIT | engine-p2b0-2b-r2.log:8239, 8242-8267；evidence-p2b0-2b/run-20260831-081221/verdict.json（63/256 failed, elapsed 989.1s） |
| E2 | K=16 r3 OOM @470s 同型：`Available full tokens: 18432 (full_available_size=1030 + full_evictable_size_=17402)` | engine-p2b0-2b-r3.log:3173-3205；run-20260831-083747/verdict.json（64/128 failed, 470.7s） |
| E3 | 崩溃前 walker 撞墙：`write_back: backup failed under host memory pressure but subtree drop declined (node locked); root node 1397/1396 stays device-resident`（08:28:40 / 08:28:44，即 counters 的 backup_failed+drop_declined=2）；r3 为 root node 530 | engine-p2b0-2b-r2.log:8210, 8236；r3.log:3172 |
| E4 | K=32 崩溃 dump 锁链：`[9](0) lock=1 → [19](3) lock=2 → [22](6) lock=2 → [1408](2039)→[1409..1415](2048×7)→[1419](1024) 全 lock=2`，分支 `[1417](3)→[1416](1021)→[1418](2048) lock=1`；链和 = 3+6+2039+14336+1024+3+1021+2048 = **20480**（=10×2048，整 10 chunk 链）；root lock=1 为初始值非持有者 | engine-p2b0-2b-r2.log:8250-8283；unified_tree_core.py:466（root lock_ref=1 初始化） |
| E5 | K=32 dump 其余：evictable 集 `[1393](1)→[1391](2038)→[1392]→[1394]→[1395]→[1396](2048)` full=yes 全 lock=0（和=10231=full_evictable_size_ 精确吻合），深部 `[1397](2048)→[1398]→[1399]→[1403](1024)→[1401](7)` full=no；`[1374]` 子树 20872 tokens 全 full=no（host-only 材料链）；`[1374]`/`[1393]`/`[1408]` 三兄弟共前缀 `[9]→[19]→[22]` | engine-p2b0-2b-r2.log:8284-8300 |
| E6 | K=16 dump 同构：锁链 `[535..541]` lock=1（14336）；evictable `[502]..[530]` 17402 = full_evictable_size_ 精确吻合，深部 `[512..517]` full=no；`[526]` 子树 20447 host-only | engine-p2b0-2b-r3.log:3209-3240 |
| E7 | hollow 有效但撞墙前 92s 已停：末次 `evt=hollow_evict node=1262` @08:27:12；r2 共 74 次/196,447 tokens，r3 13 次/40,931 | p2a-r2-k32.log:4513；counters.md |
| E8 | restore 风暴：r2 prefetch_revoke 245×`revoked:miss`（storage_hit=0）、denied_rate_limit 99、shortfall 92、hybrid_discard 37；restore_recompute 598 = miss 250 + timeout 348 | p2a-r2-k32.log 计数（grep reason= 分布） |
| E9 | L3 miss 证据：r2 `Failed to fetch *.mamba` 38 次（首条 08:12:58，起步 61s）；r3 138 次（首条 08:38:21 = 启动后 46s，速率 7.6× r2） | engine-p2b0-2b-r2.log:1310；r3.log:807 |
| E10 | r3 启动即 88% 满（**共享命名空间**）：`HiCacheFile eviction enabled: cap=20000000000 B ... existing=18585288704 B (333099 entries)` —— r3 复用了 r2 的 ns，逐出 churn 从 t=0 开始；r2 起步 `existing=0 B`（fresh） | engine-p2b0-2b-r3.log:660；r2.log:660 |
| E11 | full_lock 语义：链锁仅 4 处获取——cache_unfinished_req chunk 锁（unified_radix_cache.py:1120）、load_back H→D 锁（:1547）、schedule_policy 准入锁（schedule_policy.py:1030/1132）、非写回 backup 锁（:1449）；`acquire_component_lock` 沿 node→root 全链 +1、root 自身不加；每请求任一时刻恰一把链锁（chunk 路径先 `_dec_req_lock` 再 inc）→ **lock=2 = 两个在途请求共享 [19..1419] 链**（A 止于 [1419]=17408 tokens，B 经 [1419] 续到 [1418]=20480 tokens）；load_back 持有者被排除（load_back 同步执行，其 evict 失败即释放锁，崩溃时刻不可能"在途"） | full_component.py:277-301；unified_tree_core.py:579-596 |
| E12 | drop 拒绝条件：`drop_subtree_no_host` 在叶自身 host_lock_ref>0 或任一后代 lock_ref/host_lock_ref>0 时拒绝；现场后代 host 值被两类锁钉住——(a) 在途 L3 写（`ongoing_backup` 提交时 `inc_host_lock_ref`，ack 才释放），(b) 在途 prefetch anchor（`inc_host_lock_ref(last_host_node_id)`，insert 完成后才释放） | unified_tree_core.py:1319-1328；unified_radix_cache.py:1790-1792→2863-2866、1996-1999→2269 |
| E13 | hollow 拒绝条件：`is_l3_durable = storage_persisted OR storage_restored`，两标志 init False 后**全树无任何清除路径**（grep 验证）；撞墙叶 [1396]/[530] 的 L3 写**从未提交**（它的 D→H backup 就是失败的那次）且从未 restore → False → hollow 拒绝。e14 判定"无 skip-backup 路径不适用"的 miss 清除钩子：现在逐出/写滞后使 miss 真实发生，但**该钩子对撞墙叶无济于事**（标志 False 不是陈旧 True） | unified_tree_core.py:147,153,1995-2002；unified_radix_cache.py:830 |
| E14 | L3 LRU 逐出不通知树：`on_evict` 回调仅 `metadata_cache.remove`（存储侧 5s TTL 正查缓存），不触碰任何树内 durable 标志 → 标志在文件逐出后陈旧 True | hicache_storage.py:432-434；lru_file_evictor.py:343-358 |
| E15 | prefetch 预算已有近似限制：`prefetch_capacity_limit = 0.5 × host`（49152→24576 span-tokens，cache_controller.py:649-656,1256-1257），按**请求 span** 计费、锁步更新、突发可超发（日志同刻 2-3 个 20910 在途）；dedupe 仅按 rid（:1981-1992）——同链多请求各发各的 20910；材料完成后滞留树 host（load_back 或 host 逐出才释放） | cache_controller.py:649-656；unified_radix_cache.py:1981-1992 |
| E16 | host 逐出为**叶级**：H-leaf = evicted + host value + 无子 + 未锁；叶被钉 → 整条 host 链不可逐出（[1374] 子树 20872 仅叶 [1389] 一个出口） | unified_tree_core.py:1818-1822, 352-358 |
| E17 | 启动脚本工具缺陷：native 分支不 export `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR/MAX_SIZE/MIN_FREE_SPACE/ENABLE_METADATA_CACHE`（仅 docker 分支 `-e`，launch-l3-3090.sh L132-139；native 分支 L144-172 只设 JIT env）→ r1-invalid 落到 /tmp/hicache（root fs）→ ENOSPC 36 次（counters r1 行；/tmp/hicache 4.7G 残留 mtime 08:06-08:07） | launch-l3-3090.sh（本机副本同构）；hicache_storage.py:368（STORAGE_DIR env 回退 /tmp/hicache） |

## summary

### 结论（一句话）

第四轮残余 OOM 的根因 = **"写中途链"死锁**：设备池被合法 working set 锁住 ~2/3（K=32 为两在途请求共享的 20480-token 链，full_lock=2；K=16 为单请求 14336），唯一剩余 evictable 空间收敛为一个"深部叶子已被 demote、L3 写已提交未 ack、叶自身写从未开始"的链；host 池被在途 restore 材料（多路 20910-token prefetch）与在途写钉锁饱和 → D→H backup 失败 → drop 被拒（后代 host 锁）→ **hollow 被拒（叶 is_l3_durable=False，e14 谓词覆盖不到"写未提交"形态）** → walker 回收 0 → alloc 2048 失败 → OOM。候选 A（e14）已修好 durable 链形态（74 次 hollow 有效）；残余形态非 K=32 特例（K=16 同构复发）；L3 20G cap 逐出（durability 陈旧）是放大器非根因（r3 共享 ns 全程 churn，r2 大概率未触达 cap）。

### Current Architecture（当前架构——事实层）

1. **锁生命周期（不变，非泄漏）**：每请求任一时刻一把链锁（准入/chunk 交替，chunk 路径先 dec 后 inc），锁沿 last_node→root 全链；`full_lock=2` = 两个在途 prefill 请求共享 [19..1419] 链（E11）——合法 working set，与 e11 定案一致。K=16 为单请求 lock=1——**两把锁不是必要条件，单锁即可触发本形态**。
2. **walker 撞墙分支**（unified_radix_cache.py:809-849）：backup 失败 → `drop_subtree_no_host` → `is_l3_durable` hollow → warning。崩溃时刻三兄弟前缀链下：evictable 集 = [1393] 子树设备层 10231（E5，与 full_evictable_size_ 精确吻合）；[1397..1401] 已被 demote（host，L3 写在途持 host 锁）；[1374] 子树 20872 = 已完成 prefetch 的材料（insert 后滞留树 host，叶 [1389] 被在途 prefetch anchor 锁钉）。
3. **host 满构成**（49152 池）：[1374] 材料 20872（叶锚钉）+ [1397..1401] 7175（写锁钉）+ 锁链 restore 残留 host 副本等 ≈ 满；`evict_host` 是叶级逐出（E16），两条大链的叶都被钉 → 腾不出 2048 → backup 失败。
4. **hollow 的谓词缺口**：e14 谓词 = 写 ack 或 restore 成功（E13）。撞墙叶 [1396]/[530] 恰好两者皆非——backup 失败发生在写提交之前，叶自身从未进写管线。**这不是标志陈旧（陈旧=True 会放行），而是标志从未置位**。e14 裁决"miss 清除钩子不适用"的结论在"陈旧"意义上仍成立，但本轮证明缺口在别处。
5. **L3 cap 逐出的角色**（E14）：逐出文件不通知树 → 陈旧 True 标志 → hollow 放行"文件已删"链 → 后续 restore 探测 miss → recompute 风暴（E8：245 revoked:miss；E9：r3 138 次 miss）。该风暴反过来喂 host 饱和（每次重试 = 20910 材料 + anchor 钉叶）。**r2（fresh ns）大概率未触达 cap**（18.6G/989s 平均写率 < 20G，写率后置，首 miss 08:12:58 为写滞后型）→ 崩溃机制本身与 cap 无关；r3（共享 18.6G ns）cap churn 从 t=0（E10），把"靠 host 及时释放存活"（e10 E11 的 K=16 既往 10 次撞墙后存活）变成 470s 撞死。

### Issue-Forces（结构力冲突）

- **F1（本轮新增）**：hollow 逃生通道对"写中途链"关闭——walk 的 fallback 需要"本节点 L3 副本已存在"，而撞墙节点恰好是"副本将要存在但尚未存在"（写因 backup 失败从未开始）。锁链 20480 合法不可动 + evictable 唯一候选不可动 = 回收 0。
- **F2（继承 e10 F2）**：restore 管线与 evict 管线互锁——restore 等设备配额（DEVICE_QUOTA），其材料占满 host（堵死 backup）且 anchor 钉叶（堵死 host 逐出）；唯一不依赖 host 的出路（hollow）被 F1 关闭。
- **F3（放大）**：20G cap + 共享命名空间 → 陈旧 durable 放行"文件已删"链的 hollow → restore miss 风暴 → 20910 材料反复入 host → host 饱和窗口扩大（r3 470s 撞墙 vs r2 989s）。
- **F4（host 逐出粒度）**：host 逐出仅叶级 + 叶被 6 个锁引用钉住 → 28K+ tokens 不可回收（E16）——"少量锁钉住大块"的结构脆弱性。

### Proposed Architecture（目标——修复方案）

**候选 Z3（推荐）：evict 兜底改为无条件设备层释放（device-drop fallback）**

- 改动：`_evict_components` 的 else 分支（unified_radix_cache.py:842-849）由"warning 后放弃"改为调用既有 `_evict_device_leaf_storage_backed`（= 仅释放设备层、保留节点 + host 子树，机制已存在 L755-770 / unified_tree_core.py:1353-1379）；按 `is_l3_durable` 区分日志（durable → 既有 `evt=hollow_evict`；非 durable → 新 `[P2A] evt=device_drop_no_copy node=%d freed=%d`）。
- 语义：写回模式持久性从"强制"降级为"尽力而为"——与既有 `drop_subtree_no_host`（r2 实际 161 次 drop_without_backup）同一容忍契约（缓存丢失 = 未来 recompute），只是范围收窄为"drop 被锁拒绝时的叶设备层"。
- 安全性论证：(a) walker 只访问 evictable_device_leaves（lock_ref=0，E8/e10 已证）；(b) 到达该分支时 backup 已失败 → 本叶无在途写（写提交于 backup 成功之后，unified_radix_cache.py:811-822），无在途读（lock=0 且 load_back 持锁）；(c) 只释放设备层，host 子树与在途写不受影响（L3 写读 host 值，spec.host_value）；(d) 后代在途写缺 [1396] 前缀页 → L3 链不完整 → 未来 restore 探测 miss → recompute（已容忍路径，无 corruption——L3 内容寻址，缺前缀只造成 miss）。
- 改动面：1 分支 + 1 日志点 + 测试契约翻转（见验证设计）；**不改锁生命周期、不改 walker 候选集、不改 L3 写/ack 路径**。
- 效果：崩溃现场 walker 第一次撞 [1396] 即释放 2048 → alloc 成功 → 锁链请求继续推进 → 解锁 → 恢复。K=16 同构解除。OOM 类（"evict 无候选"）从机制上消除——**只要存在任何 evictable 设备叶，walk 必推进**。

**候选 Y（补充，不单独修）：restore-miss 清除 anchor 的 durable 标志**

- 挂载点：`revoke_pending_prefetch`（unified_radix_cache.py:2632-2684）在 `storage_hit_count==0` 时清除 anchor（last_host_node_id）的 `storage_restored`/`storage_persisted`；部分命中（hit>0）不清（anchor 前缀仍可能完好）。自愈：写 ack 会重新置位（:2875）。
- 价值：死链的 frontier wake / prefetch gate 谓词（`frontier_anchor_ready`/`prefetch_gate_ok` 读 is_l3_durable，:1801-1813, 1837-1850）不再 re-issue 徒劳 prefetch → 削减 E8 风暴的 host 占用与 anchor 钉锁 → host 饱和缓解（F3/F2 的触发端）。
- 风险/粒度：文件级 vs 链级——miss 只证明"查询 span 无文件"，hit==0 时 anchor 自身页必缺（查询覆盖 anchor 前缀键），清除 anchor 安全；**注意 Y 必须与 Z3 同改**：单独清标志会让 hollow 拒绝更多陈旧链（walk 进展变差，撞墙提前）。

**候选 X（分析后拒绝为主修）：restore 并发限制 ≤1**

- 已有近似限制：prefetch_capacity_limit = 0.5 host（24576 span-tokens，E15）——按请求 span 计费、锁步更新、突发可超发；硬性 ≤1 会序列化 restore（r2 已 348 timeout 占 recompute 78%），进一步恶化 recompute 占比；与 P2-0a 实测 8 并发 prefetch 冲突；且不解决"材料滞留 + 锚钉叶"（完成材料仍占 host 到 load/逐出）。可留作后续调优：预算改按实际 host 占用计费 + revoke 立即释放（收紧现有预算，非并发数限制）。
- **候选 Z1（不推荐）**：撞墙时 drain+等待在途写 ack 后重试 drop——只修 4 秒竞态窗口（walker 自身 demote-ack 未落地），而钉锁还含在途 prefetch anchor IO（非 drain 可完成），等待不可控且在调度热路径阻塞。

### Alternatives（对比与为何 Z3 胜出）

| 维度 | Z3（设备层无条件兜底） | Y（miss 清标志） | X（restore ≤1） |
|---|---|---|---|
| 根因匹配 | 直击 F1（逃生通道对写中途链关闭） | 直击 F3 触发端（风暴削减） | 间接（host 腾挪） |
| 单独效果 | **必然解除 OOM**（walk 必推进） | 不解除（撞墙叶标志本就 False） | 大概率解除但降吞吐 |
| 改动面 | 1 分支 + 1 日志 | 1 挂载点 + 谓词联动 | 预算计费改造 + 语义风险 |
| 正确性风险 | 低（缓存丢失 = 既有 drop 契约，r2 已 161 次；无在途读写窗口） | 低（自愈，但单独用反效果） | 中（timeout 风暴恶化 + 8 并发 prefetch 回归） |
| 与 e11/e14 交互 | 先行分支不变，纯追加；M1/M2 写/ack 路径零触碰 | 需 Z3 垫底 | 影响 prefetch 生命周期计数 |
| CHAIN_GAP | 零影响（不触碰写/ack/晋升） | 零影响 | 零影响 |

### Impact（对已验证机制）

- **M1/M2（ack 完整性/晋升追溯）**：Z3 不触碰写路径；device-drop 节点不晋升（无写），与"未写节点不晋升"现状一致；drop 节点的后代在途写不受影响（L3 写读 host 值）。
- **e11 hollow + e14 l3_durable**：durable 链的 hollow 行为原样保留（is_l3_durable 分支先行）；Z3 只是其后的无条件兜底；`test_no_hollow_for_pure_recompute_chain`（L2089）的契约翻转（"永不 hollow" → "backup+drop 双败后设备层兜底"）是**有意的语义变更**，需与 e14 裁决一并确认。
- **归因基线**：新增 `device_drop_no_copy` 计数；recompute 占比在高压窗口上升（与 drop_without_backup 同语义，已是运行期事实）。
- **restore 风暴**（若 Y 一并采纳）：死链重试次数下降，host 占用下降；r3 型共享-ns 场景改善最大。

### 验证设计

1. **torch-free 单测**（3090-dev/test_storage_regression.py，RestoreChainHollowEvictionTests 扩展，镜像 e14 的 RED→GREEN 模式）：
   - Z3 钉：`_HollowWalkTree(persisted=False, durable=∅)` + backup 失败 + drop 拒绝 → 设备层释放（tracker[FULL]==2048）——镜像 test_hollow_evict_breaks_deadlock_on_restored_chain（L2064），durable 集为空
   - 契约翻转：test_no_hollow_for_pure_recompute_chain（L2089）改写为"非 durable 链仅在 backup+drop 双败后设备层兜底；host 子树保留；无压力时（backup 成功）走原路径不触发"
   - 安全钉：叶 lock_ref>0 不被访问（既有 walker 语义回归）；device-drop 后节点保 host 值、在途写不中断
   - Y 钉（若采纳）：hit=0 revoke 清 anchor 标志 → 后续 prefetch_gate_ok=False；hit>0 不清
2. **K=16 重测（回归线收紧：必须过）**：**fresh ns**（修正 r3 共享 ns 的方法学偏差）；同 driver 配方（8 turns × 16）；判据 = 越过旧崩溃点 470s（以 e20 的 1112s 为基线）+ OOM=0 + 签名 0 + 优雅退场 + "stays device-resident" 警告 0 次 + `device_drop_no_copy` 计数落盘
3. **K=32 重测**：fresh ns；越过旧崩溃点 989s（25 分钟护栏）；hollow_evict / device_drop_no_copy / restore_recompute 计数记录；崩溃前 90s 无 hollow 的形态应消失
4. **K=1 回归**：12/12 无行为变化（无压力时新兜底不触发）
5. **方法学修正**：每 run 独立 fresh ns；启动日志记录 `existing=` 行（r3 污染的检测点，engine 日志 L660 形态）；建议 tester 在 verdict 记录 L3 ns 状态
6. **devops 小任务**（附带，标记为 tester/devops）：launch-l3-3090.sh native 分支 export 四个 `SGLANG_HICACHE_FILE_BACKEND_*` env（对齐 docker 分支 L136-139）——r1-invalid 的 ENOSPC 36 次即此缺陷（E17）

## followups

1. 协调人裁决候选 Z3（推荐，含测试契约翻转确认）+ 是否同改 Y；批准后 coder 实现 + 单测，tester 按验证设计跑 K=1/16/32 三级回归（K=16 为必过线）。
2. 观测点：`[P2A] evt=device_drop_no_copy` 新日志 + 计数（与 hollow_evict 分离，供回归判定）；hollow_evict 日志建议加 durable 来源字段（写 ack / restore / 兜底）便于归因。
3. 长期（非本次）：host 池精确占用核算探针（e10 followup 3 仍缺，本次 host 满构成只能重构到 ~28K/49K 的链级，其余不可还原）；storage_existence_cache 对 cache 模式的填充（hollow 谓词直查 L3 页存在性，消除陈旧）——若采纳则与 Y 合流；prefetch 预算改按实际 host 占用计费（X 的温和形态）。

## open_issues

- r2 是否触达 20G cap 不可考（evictor 的 debug 级 "reclaimed" 日志未捕获；写率后置估算下 cap 在崩溃点前后，首 miss 08:12:58 为写滞后型）——不影响修复方向（Z3 与 cap 无关；Y 对 r3 型场景价值最大）。
- K=32 dump 节点 token 和（30711）与池核算 used（21504）差 ~9.2K——dump 时刻（SIGQUIT 后 5s）与 available 计数时刻不同 + key/value 长度差异，结构结论不受影响。
- `is_l3_durable` 陈旧语义（文件删后标志仍 True → hollow 放行 → miss → recompute）：e10 open_issues 已接受；本轮确认其为风暴放大器（F3），非正确性问题。
- 命名空间共享（r3 复用 r2 的 18.6G）属方法学偏差，已列入验证设计修正（fresh ns 每 run）。
