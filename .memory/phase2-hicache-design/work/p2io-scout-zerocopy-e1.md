# p2io-scout-zerocopy-e1 — zero-copy storage path 可用性核查（只读）

## 1. status

**done** — 三件事全部核查完毕，证据均为本分支工作树实际代码（行号以当前工作树为准）+ 任务目录内的实测数据日志。

## 2. artifacts（读过的文件）

- python/sglang/srt/managers/cache_controller.py（1422 行，全文定位 + 局部读）
- python/sglang/srt/mem_cache/hicache_storage.py（ABC/v1/v2 签名 + STORAGE_BATCH_SIZE）
- python/sglang/srt/mem_cache/storage/backend_factory.py（257 行，全文）
- python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py（669 行，方法级定位 + 局部读）
- python/sglang/srt/mem_cache/storage/extent/extent_allocator.py、__init__.py
- python/sglang/srt/mem_cache/storage/sim_storage.py（v1 参考实现）
- python/sglang/srt/mem_cache/storage/nixl/hicache_nixl.py（v1/v2 zero-copy 参考，450-760）
- python/sglang/srt/mem_cache/storage/umbp/umbp_store.py（file-based v1 zero-copy 参考，1075-1159）
- python/sglang/srt/mem_cache/pool_host/base.py、mha.py、mamba.py、group.py
- python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py（110-260、590-740）
- python/sglang/srt/mem_cache/memory_pool_host.py（get_page_buffer_meta 所有者）
- python/sglang/srt/server_args.py（2790-2809、2776-2789）
- .memory/phase2-hicache-design/plan-p2io.md、ledger.md、fetched-hicache-upstream.md
- .memory/phase2-hicache-design/work/p2io-tester-e3.md（8.31s 拆解数据日志）、p2io-coder-e4.md、p2io-scout-backend-e1.md
- /home/charles/Workspaces/homenet/server/gpu/3090-dev/launch-l3-3090.sh（120-121 行）
- git diff（工作树未提交改动：hicache_storage.py 8 行 + extent_file_backend.py 134 行 + 新测试 328 行）

## 3. evidence（file:line）

### 3.1 事一：Extent/引擎当前走哪条路径

- 选择逻辑唯一在 cache_controller.py:663-675：默认 `page_get_func=_generic_page_get`（:664-665）；零拷贝名单 `["hf3fs","mooncake","eic","nixl","simm","mori"]`（:668-669）**或** `storage_backend_type=="dynamic" and bool(extra_config.get("interface_v1",0))`（:671-672）→ 才切 `_page_get_zero_copy`/`_page_set_zero_copy`（:674-675）。**"extent" 不在名单 → Extent 恒走 generic**。
- `storage_backend_type = storage_backend`（cache_controller.py:619）——launch 用名（"extent" 或 "dynamic"）原样保留；"dynamic" 时真实后端从 extra_config 读 backend_name/module_path/class_name（backend_factory.py:99-103、122-127）。
- 零拷贝函数全部存在：`_page_get_zero_copy`（cache_controller.py:1076-1090，内部调 `storage_backend.batch_get_v1(hash_values, host_indices, extra_info)` :1079）；`_page_set_zero_copy`（:1347-1350，`batch_set_v1`）。
- generic 两函数存在：`_generic_page_get`（:1093-1116：逐 page `get_dummy_flat_data_page` :1096-1098 → `batch_get` :1099 → Python for 每页 + `set_from_flat_data_page` :1111-1114）；`_generic_page_set`（:1340-1345：逐 key `get_data_page` + `batch_set`）。
- 调用链：prefetch_io_aux_thread（:1214-1234）→ `_page_transfer`（:1118-1162，按 STORAGE_BATCH_SIZE 分批 :1128，host_indices 切片 :1136-1138）→ `_page_transfer_kv_batch`（:1164-1212）→ `self.page_get_func(...)`（:1180）+ 侧车 `batch_get_v2`（:1195）。写侧 backup_thread → `_page_backup`（:1353-1373）→ `self.page_set_func(...)`（:1364）。命中查询 `_storage_hit_query`（:1261-1284，v1 `batch_exists` :1276）；hybrid 覆盖版（hybrid_cache_controller.py:596-632，带 sidecar 时 `batch_exists_v2` :606）。
- Extent 引擎接入链：scheduler.py:4885 attach → unified_radix_cache.py:3308 / hiradix_cache.py:365 → cache_controller.py:593-640（factory :637，注册 :640）→ backend_factory.py:201-205 注册 "extent" → :161-162 builtin 分支。Hybrid：hybrid_cache_controller.py:171-187（super().attach + 逐 entry `register_mem_host_pool_v2` :186-187）。
- **结论：Extent（无论 "extent" 还是不带 interface_v1 的 "dynamic"）在引擎中实际走到 `_generic_page_get`/`_generic_page_set`。** 佐证：plan-p2io.md:9 明写"零拷贝名单不含新名 → 新后端走 generic 路径，controller 零改动"。

### 3.2 事二：batch_get_v1/batch_set_v1 接口可用性

- HiCacheStorage ABC **已有签名**（非 abstractmethod，默认 `pass`）：`batch_get_v1` hicache_storage.py:226-236、`batch_set_v1` :238-248。v2 三件套签名 :204-224（默认 NotImplementedError）。
- **ExtentFileBackend 无 v1 实现**：extent/ 目录 grep `def batch_get_v1|def batch_set_v1` 零命中；方法全集（extent_file_backend.py:283-669）= get/set/exists/batch_get/batch_set/batch_exists + v2 三件套，无 v1。
- **HiCacheFile 也无 v1 覆盖**（hicache_storage.py 内 v1 只出现在 :226/:238 ABC 默认）。**SimHiCacheStorage 有**（sim_storage.py:127-150，空操作桩）。其余实现：eic_storage.py:744/770、nixl hicache_nixl.py:818/847、hf3fs storage_hf3fs.py:882/909、mooncake 1051/1080、simm 316/341、umbp 1075/1144。
- v1 zero-copy 契约（本分支已有，无需移植）：nixl `_get_location_and_size_list_from_meta`（hicache_nixl.py:675-690）= `ptr_list, element_size_list = self.mem_pool_host.get_page_buffer_meta(host_indices)`；`_batch_preprocess`（:698-744）按 `page_num = len(host_indices)//page_size` 展开（:710）。file 型先例：umbp `batch_get_into_ptr(key_strs, buffer_ptrs, sizes)`（umbp_store.py:1104）。
- interface_v1 声明位置：全仓仅 cache_controller.py:672 一处读取（`storage_config.extra_config.get("interface_v1", 0)`），无后端侧声明文件；是 controller 对 "dynamic" 类型的 opt-in 开关。
- **风险点**：ABC v1 默认 `pass` → 返回 None；`_page_get_zero_copy` 内 `if not results[i]`（:1084）对 None 直接 TypeError → **interface_v1=1 而 backend 无 v1 实现 = 运行时崩溃，不是静默回退**。
- **结论：Extent 的 batch_get_v1/batch_set_v1 缺失，需新增（"需移植"量为 0——controller 侧零拷贝机制、ABC 签名、pool 侧 get_page_buffer_meta 契约本分支全部已在，只需在 Extent 类内自实现约 60-100 行，模板 = nixl/umbp 的 v1 + extent 现有 _read_pages/_write_pages）。**

### 3.3 事三：hybrid Host pool 映射语义

- HostKVCache ABC：pool_host/base.py:113；flat 页三 API：get_data_page（:300）、get_dummy_flat_data_page（:307）、set_from_flat_data_page（:315）。子类：MHATokenToKVPoolHost（mha.py:69）、MHATokenToKOnlyPoolHost（:695）、MLATokenToKVPoolHost（mla.py:51）、MambaPoolHost（mamba.py:41）、DSAIndexerPoolHost（dsa.py:49）、DeepSeekV4PagedHostPool（memory_pool_host.py:174）、DeepSeekV4StateHostPool（:572）。
- Qwen3.5 hybrid：HostPoolGroup（group.py:28）+ PoolEntry（:13），anchor_entry = KV 池（:43）；hybrid controller `self.storage_host_pool = mem_pool_host.anchor_entry.host_pool`（hybrid_cache_controller.py:157）——**v1 host_indices 只映射 anchor KV 池**；mamba 侧车走 v2（register_mem_host_pool_v2，hybrid_cache_controller.py:186-187；读 hybrid_cache_controller.py:696、写 :731）。
- host_indices 布局：controller 切片 `operation.host_indices[i*page_size : (i+len(batch_hashes))*page_size]`（cache_controller.py:1136-1138）→ 每 key 占 page_size 个 slot；backend 侧 `page_num = len(host_indices)//page_size`（nixl:710）；`get_page_buffer_meta` 断言 `len(indices) % page_size == 0`（mamba.py:540、mha.py:612）。
- set_from_flat_data_page 语义（generic 逐页拷贝的目标）：MHA 池一次大 slice 赋值 reshape 到 (2, layer_num, page_size, head_num, head_dim)（mha.py:526-558）；Mamba 池逐组件（temporal+conv）flatten→view→copy_（mamba.py:520-532）。get_dummy_flat_data_page（MHA）= torch.zeros((2,L,page,hn,hd)).flatten()（mha.py:518-524）——128 页/批 ≈ 4MB zeros，1024 页/批 ≈ 32MB/批。
- **zero-copy 契约（v1 直接写目标 buffer）**：`get_page_buffer_meta` 各池已实现——MHA mha.py:608-668（page_first 下每页 2 指针 k/v、element_size=整页字节；layer_first 下每层 2 指针）；Mamba mamba.py:534-594（每页 temporal+conv 组件指针，**仅 page_first/page_first_direct 布局** :541-544）；DSA dsa.py:457、MLA mla.py:583、DeepSeekV4 系 memory_pool_host.py:167/541/925。默认布局 = "page_first"（server_args.py:2789），与 MHA/Mamba zero-copy 兼容。
- **v2 与 v1 的关系（本分支）**：v2 三件套（batch_exists_v2/batch_get_v2/batch_set_v2，ABC hicache_storage.py:204-224）是侧车池语义（PoolTransfer hicache_storage.py:98-113、PoolName :62-84、PoolHitPolicy :87-95、PoolTransferResult :125-146）。**v2 并非统一"直接写 buffer"形态**：extent 的 batch_get_v2 仍是 dummy 页 + set_from_flat_data_page 逐 key（extent_file_backend.py:413-452）；nixl 的 v2 才是指针直写（_get_hybrid_zero_copy_buffers，hicache_nixl.py:488-522）。可复用的 v1 基础 = 池侧 get_page_buffer_meta 契约 + extent 现有 _read_pages/_write_pages 聚合 IO + _component_key（extent_file_backend.py:276-279，侧车组件 key 已按 "key.<pool>" 存 extent）。
- **结论：v1 zero-copy 时 backend 用 get_page_buffer_meta(host_indices) 解析目标缓冲（KV 池每页 k/v 两块连续区，preadv/pwritev 一个 syscall 可覆盖整批）；Mamba 侧车不在 v1 覆盖内（v2 保持 extent 现有 flat-page 形式，除非另行升级为指针直写）。**

### 3.4 8.31s 是否在测 legacy generic 路径 —— 是（数据日志证实）

- p2io-tester-e3.md §10.2/10.4（实测数据日志）：8.31s 整链 cold restore = queue wait 48ms（0.6%）+ **设备 pread 516ms（6%）** + **引擎侧 per-batch 开销 ≈7.7s（93%，~44ms/批 × 175 批，STORAGE_BATCH_SIZE=128 时代）** + finalize ≈0ms。
- 该测量时 extent 后端 + page_get_func=_generic_page_get（extent 不在零拷贝名单）→ **8.31s 测的确实是 legacy generic 路径**（dummy 页分配 + 逐页 set_from_flat_data_page 散射 + 批循环），设备 IO 仅 516ms（1.3-1.8GB/s 达标，与裸盘标定 10.1 一致）。
- 工作树未提交改动已把 STORAGE_BATCH_SIZE 128→1024（hicache_storage.py:27，注释明写"175 批×44ms=7.7s…8x 更少更大批切 ~8x"）——这是 generic 路径的廉价部分缓解；**前提假设"每批 44ms 为固定开销"未被逐项插桩证实**（dummy 页分配量随批变大而变大，1024 页/批 = 32MB zeros/批）。zero-copy 候选同时消除 dummy 页分配 + 逐页散射循环，对"固定 vs 每页"两种成分都有效，是更稳的修复方向。

## 4. summary（ranked findings）

### Critical

1. **Extent 当前走 legacy generic 路径（确认）**：cache_controller.py:663-675 选择逻辑，"extent" 不在零拷贝名单；prefetch 读链 = _page_transfer → _page_transfer_kv_batch → _generic_page_get（逐页 dummy + set_from_flat_data_page）。写链 = _generic_page_set。
2. **controller 侧零拷贝机制本分支已全部存在（确认，无需移植）**：_page_get_zero_copy（:1076-1090，batch_get_v1）、_page_set_zero_copy（:1347-1350，batch_set_v1）、interface_v1 开关（:671-672，"dynamic" 专属）、动态后端加载（backend_factory.py:99-103）。
3. **Extent 缺 batch_get_v1/batch_set_v1（确认缺失，需新增）**：ABC 签名已在（hicache_storage.py:226-248，默认 pass）；extent 类内无 v1。启用 interface_v1=1 而无 v1 实现 = 运行时 TypeError（_page_get_zero_copy :1084），非静默回退。

### High

4. **zero-copy 落地最小改动面**：
   - backend 侧（主工作量，~60-100 行）：ExtentFileBackend 实现 batch_get_v1/batch_set_v1 = `mem_pool_host.get_page_buffer_meta(host_indices)` 解析目标指针（默认 page_first 布局兼容，server_args.py:2789）+ 复用现有 _read_pages/_write_pages 聚合（或 preadv/pwritev 直写目标缓冲）+ 逐 key 成功列表 + generation 复检语义。模板：umbp_store.py:1075-1111（batch_get_into_ptr）、nixl hicache_nixl.py:675-744。
   - controller 侧：二选一——(a) 零改动：launch 走 "dynamic" + extra_config{backend_name:"extent", module_path, class_name, interface_v1:1}（backend_factory.py:122-127 必需字段 + cache_controller.py:671-672 开关）；(b) 一行改动：把 "extent" 加进 cache_controller.py:668-669 名单（对一切 extent 启动生效，需回归）。
   - 从 main 移植量 = 0：本分支已含 main 同款 zero-copy 机制（分支基线 main b644771e）。
5. **hybrid 语义边界（确认）**：v1 host_indices 只覆盖 anchor KV 池（hybrid_cache_controller.py:157）；mamba 侧车恒走 v2（extent v2 现为 dummy 页形式，extent_file_backend.py:413-452）——Qwen3.5 场景下 zero-copy 只消掉 KV 侧逐页开销，侧车 v2 的逐 key 散射仍在（需另行决定是否把 batch_get_v2 也升为指针直写，用 MambaPoolHost.get_page_buffer_meta mamba.py:534-594）。
6. **8.31s = legacy generic 路径实测（确认）**：7.7s/93% 为引擎侧批循环开销（tester e3 §10.4），设备仅 516ms；zero-copy 是结构性修复（消 dummy 分配 + 逐页散射 + 批循环），STORAGE_BATCH_SIZE 1024（工作树未提交，hicache_storage.py:27）是部分缓解且其"固定开销"假设未验证。

### Medium

7. v1 零拷贝契约的池侧实现全部在位（get_page_buffer_meta：MHA mha.py:608-668 / Mamba mamba.py:534-594 / MLA mla.py:583 / DSA dsa.py:457 / DeepSeekV4 系 memory_pool_host.py:167/541/925）；HostKVCache ABC 无该方法的基类默认（各池自行实现，nixl 用 hasattr 探测 hicache_nixl.py:456-458）。
8. 现有 extent 单测（74→87 例，uncommitted 328 行新测试）无 v1 zero-copy 覆盖、无 v1写→v2查 跨路径用例的历史缺口已修（v1 全入口 _storage_key 统一，extent_file_backend.py:268-279）；v1 zero-copy 落地需补：非空 config_suffix + 直写路径 round-trip、page_first/layer_first 双布局、k/v 双 iovec 直写、mamba 侧车 v2 不变回归。

## 5. followups

1. 若采纳 zero-copy 候选：Extent 实现 batch_get_v1/batch_set_v1（模板 nixl/umbp），controller 侧选 (a) dynamic+interface_v1（零改动）或 (b) 名单加 "extent"（1 行，cache_controller.py:668-669）。
2. 8.31s 的 44ms/批成分（固定 vs 每页）未插桩分离——zero-copy 落地后重测 640MB 整链 cold restore 作裁决；同时记录 1024/批下 dummy 页分配量变化的影响。
3. 侧车 v2 是否升指针直写（MambaPoolHost.get_page_buffer_meta 已在）：取决于 v1 落地后 mamba 侧车是否成为新瓶颈——不在第一刀。
4. 3090 launch 切换点：launch-l3-3090.sh:120-121 现为 `--hicache-storage-backend file`（extent 实验用独立 /root/p2io-extent-run.sh，L3_BACKEND=extent）；切 dynamic+interface_v1 需改 extra_config JSON。

## 6. open_issues

- 44ms/批 的固定/每页成分归属无插桩证据（tester e3 §10.4 归因为推断："host 页分配、GIL/调度竞争、批循环"）；STORAGE_BATCH_SIZE=1024 的"~8x 收益"假设成立与否待实测。
- Qwen3.5-9b-gptq 的 host 池布局实测值（anchor 池 = MHATokenToKVPoolHost？layout=page_first 默认生效？）未在 3090 端直接确认（server_args 默认 page_first，MHA 池 page_first 分支在位）；zero-copy 落地前建议用引擎日志/单测锁定实际 layout。
- interface_v1 是否会影响 4c/既有 file 后端运行：名单式选择是每 attach 独立判定，"extent" 不进名单则 file/extent 现状不变——仅 dynamic+interface_v1 或名单改动会影响。
