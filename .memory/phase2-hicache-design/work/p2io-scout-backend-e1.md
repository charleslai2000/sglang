# P2-IO-1 scout report: HiCacheFile L3 backend 现状侦察（backend 改动面）

- 任务: 查清 sglang 现有 L3 存储后端（HiCacheFile）的实现结构、接口抽象与调用路径
- 仓库: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/（分支 3090-24g-hicache）
- epoch: e1；只读侦察，未修改任何代码
- 日期: 2026-08-31

## 1. status

done

## 2. artifacts（已读文件）

| 文件 | 用途 |
|---|---|
| python/sglang/srt/mem_cache/hicache_storage.py（727 行，全文） | 接口 ABC + HiCacheFile 实现 |
| python/sglang/srt/mem_cache/storage/backend_factory.py（全文） | 后端注册/工厂 |
| python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py（全文） | 磁盘容量/LRU 驱逐 |
| python/sglang/srt/managers/cache_controller.py（481-1118, 754-862, 990-1116, 1076-1422 段读） | 存储线程与 IO 调用链 |
| python/sglang/srt/mem_cache/unified_radix_cache.py（1725-1855, 2197-2380, 2445-2580, 2990-3300, 3668-3740 段读） | prefetch/restore/backup 调度层 |
| python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py（2000-2095） | storage_persisted/restored 标志 |
| python/sglang/srt/managers/scheduler.py（2866-2979, 3753, 4885-4912 段读） | scheduler 侧 restore 触发 |
| python/sglang/srt/managers/scheduler_components/hicache_restore.py（全文，289 行） | P2-1 M1b restore 状态机（纯逻辑） |
| python/sglang/srt/environ.py（689-699 段） | 文件后端 env 变量定义 |
| python/sglang/srt/server_args.py（2790-2834 段） | --hicache-storage-backend 参数 |
| /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md（全文分三段读） | P2-IO-1 ExtentFileBackend 设计 |
| /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-promotion-admission.md（标题轮廓） | P2-1c H→D 预算（无 P2-IO-1 内容） |
| test/registered/unit/mem_cache/test_hicache_file_lru_unit.py、test/registered/hicache/test_hicache_spec_file_storage.py（grep） | 直接引用 HiCacheFile 的测试 |
| python/sglang/srt/mem_cache/storage/umbp/umbp_store.py（grep） | io_uring 唯一"代码"提及（外部 mori 库） |

## 3. evidence（按侦察要点）

### 3.1 L3 backend 抽象接口（要点 1）

`HiCacheStorage(ABC)` — `python/sglang/srt/mem_cache/hicache_storage.py:152-328`。粒度 = **page 级 key**（一存储 key = 一个 page = page_size token 的 hash）；批量接口收 keys 列表，不合并 IO。

接口签名清单（当前工作树，行号已核）：

| 方法 | 签名 | 位置 | 语义 |
|---|---|---|---|
| register_mem_pool_host | (mem_pool_host: HostKVCache) | :159 | 注册主 host 池 |
| register_mem_host_pool_v2 | (host_pool, host_pool_name) | :162 | 注册侧车池（mamba/swa/indexer） |
| batch_exists_v2 | (keys: List[str], pool_transfers, extra_info) -> PoolTransferResult | :167-198 | 最长前缀命中 + 每池 hit_policy（ALL_PAGES/TRAILING_PAGES） |
| batch_get_v2 | (transfers: List[PoolTransfer], extra_info) -> dict[str, List[bool]] | :200-209 | 读入 host 池，per-entry 成功列表 |
| batch_set_v2 | (transfers, extra_info) -> dict[str, List[bool]] | :211-220 | 从 host 池写存储 |
| batch_get_v1 | (keys, host_indices: torch.Tensor, extra_info) -> List[bool] | :222-232 | 零拷贝读（backend 直接写 host_indices 指向的池内存） |
| batch_set_v1 | (keys, host_indices, extra_info) -> List[bool] | :234-244 | 零拷贝写 |
| get（abstract） | (key, target_location, target_sizes) -> torch.Tensor \| None | :246-257 | 单 key 读 |
| batch_get（abstract） | (keys, target_locations, target_sizes) -> List[Tensor\|None] | :260-271 | v1 批量读（dummy page 目标） |
| set（abstract） | (key, value, target_location, target_sizes) -> bool | :273-285 | 单 key 写 |
| batch_set（abstract） | (keys, values, target_locations, target_sizes) -> bool | :288-300 | v1 批量写 |
| exists（abstract） | (key) -> bool | :302-308 | 存在性 |
| batch_exists | (keys, extra_info) -> int | :311-322 | **默认实现 = 逐 key 调 exists**（连续命中数）；子类可覆盖 |
| clear / get_stats | () | :324/:327 | 清空/统计 |

关键数据类：`HiCacheStorageConfig`（:26-40，构造入参）、`PoolTransfer`（:94-109，name/host_indices/device_indices/keys/hit_policy/nodes_to_load/indices_from_pool）、`PoolTransferResult`（:121-142）、`HiCacheStorageExtraInfo`（:43-46）、`PoolName`（:58-80）、`PoolHitPolicy`（:83-91）。

**注意**：v1 三件套（batch_get/batch_set/batch_exists）是 unified 路径（HiCacheController）KV 主路径实际使用的接口；v2 三件套在 unified 路径只用于侧车池（batch_get_v2 cache_controller.py:1195、batch_set_v2 hybrid_cache_controller.py:731），在 HybridCacheController 路径才是全部。设计文档 §2.2 "v1 可 NotImplemented" 与现状代码事实冲突（见 open_issues O1）。

### 3.2 HiCacheFile 具体实现（要点 2）

`HiCacheFile(HiCacheStorage)` — hicache_storage.py:363-727。

- **组织方式：一 key 一文件**：`{file_path}/{suffixed_key}.bin`（`_get_component_path` :445-450）；key = page_hash + config_suffix（model/tp/pp/cp 隔离，:380-390）；侧车组件 key = `{key}.{component_name}`（`_get_component_key` :440-443）。单目录平铺，文件数 = O(pages)。
- **读路径（逐 page syscall 的确切位置）**：
  - `get()` :465-487：`open(tensor_path, "rb", buffering=0)`（:475）+ `f.readinto(buf)`（:477）→ **每 key 一次 open(2) + read(2) + close(2)**。buffering=0 只是绕过 Python 缓冲，走页缓存，**无 O_DIRECT**。
  - `batch_get()` :489-500：list comprehension 逐 key 调 `self.get()` —— **v1 批量读 = 纯 Python 循环，每 key 3 个 syscall**。
  - `_read_page()` :657-664：单页读入 dummy page 再 `set_from_flat_data_page` 拷入 host 池。
  - `_batch_io_v2()` :674-698：list comprehension `op_fn(transfer.name, key, host_pool, host_indices[i*page_size].item())` —— **v2 批量读/写 = 同样的逐 key 循环**（:694-697）。
- **写路径**：
  - `set()` :502-549：`self.exists(key)`（:513，metadata cache 未命中时 os.path.exists = stat(2)）→ `_evictor.reserve`（:523）→ tmp 文件 `value...numpy().tofile(tmp_path)`（:531，open+write）→ `os.replace(tmp_path, tensor_path)`（:532，rename(2)）→ `_evictor.commit`（:533）。**全程无 fsync**（全仓 grep fsync/O_DIRECT/O_SYNC 于该两文件 = 0 命中）；写失败回滚 :537-549。
  - `batch_set()` :551-561：for 循环逐 key `self.set()`。
  - `_write_page()` :666-672：取 host 池 flat page 调 `self.set()`。
- **exists**：:563-572，metadata cache 内存命中或 stat。
- **唯一聚合点**：`batch_exists_v2`（:604-652）— metadata cache 打开时纯内存（`_collect_existing_component_keys` :574-602 单次 os.scandir 或 dict 查询）；但**只有 HybridCacheController 路径调用它**（hybrid_cache_controller.py:606）；unified 路径 `_storage_hit_query` 用的是 v1 `batch_exists`（cache_controller.py:1276）= 基类逐 key exists 循环。
- **LRUFileEvictor**（storage/file/lru_file_evictor.py，全文 393 行）：`reserve`（:165-222，容量检查 + 逐 victim os.remove）→ `commit`（:224）/`abort`（:231）；`touch`（:241-259，已跟踪 key 为内存 LRU 移动，未跟踪才 os.path.getsize）；`_fs_stats` os.statvfs（:268-276）；启动 `_scan_existing_files` 逐文件 os.stat（:298-321）。驱逐/水位逻辑全部在 evictor，HiCacheFile 保持"薄 raw-bytes store"（模块 docstring :4-22）。

**20K page restore 3-16s 的病理定位**：读侧 = `_generic_page_get`（cache_controller.py:1093-1116）→ `backend.batch_get` → `HiCacheFile.batch_get`（hicache_storage.py:489-500）逐 key `get()`（:475-478 open+readinto+close）——**20,911 pages = 20,911 × (open+read+close) ≈ 63K syscalls，单 IO 线程串行**（prefetch_io_aux_thread，见 3.3）。与设计文档标定一致（p2-io-design.md:178-180：0.5-0.8ms/page）。

### 3.3 批量聚合点与线程模型（要点 3）

- **调用方侧聚合存在**：`STORAGE_BATCH_SIZE = 128`（hicache_storage.py:23）在 controller 侧分批：备份 `_page_backup`（cache_controller.py:1353-1373，循环 128 keys/批）；恢复 `_page_transfer`（:1118-1162）；命中查询 `_storage_hit_query`（:1261-1284）。**但 HiCacheFile 内部每个"批"仍是逐 key syscall —— 聚合只到"调用次数"层，不到"IO 合并"层**。
- **线程模型**：
  - 备份（写）：scheduler 调 `write_storage`（:1323-1337）→ `backup_queue` → **backup_thread**（:1375-1393）→ `_page_backup` → `page_set_func` = `_generic_page_set`（:1340-1345）→ `backend.batch_set`（v1）。写 IO 全在 backup_thread。
  - 恢复（读）：scheduler `_prefetch_kvcache`（scheduler.py:2866）→ `prefetch_from_storage`（unified_radix_cache.py:2197，纯提交）→ `cache_controller.prefetch`（:2355）→ `prefetch_queue` → **prefetch_thread**（:1286-1321，`_storage_hit_query` 命中查询）→ **prefetch_io_aux_thread**（:1214-1239，`_page_transfer` 实际读）→ ack 回 `ack_prefetch_queue`。
  - **scheduler 线程只做：提交（入队）+ 排空 ack**。排空点 = `check_hicache_events`（unified_radix_cache.py:3668，scheduler.py:3753 每 pass 调用）→ `_drain_storage_control_queues_impl`（:2987）→ `_drain_ack_prefetch`（:3128）/`_drain_backup`（:3156）/`_drain_and_alloc_storage_hit`/`_drain_release` —— 全部是队列/树/内存操作，**无 backend 文件 IO**。`_drain_queue`（:2998-3016）按 TP 同步后的 n 阻塞取，但每 pass 有限额。
  - **结论：restore 不阻塞 scheduler 的文件 IO**；scheduler 侧成本只有 ack 排空（树插入 `_handle_prefetch_result` :2445、内存释放、`mark_storage_restored` :2554）。
- **H→D**：`init_load_back`（unified_radix_cache.py:3592）→ `load_back`（:1725，含 P2-1c 预算门 :1735-1762/:1820-1860）→ `_load_back_transfers`（:1791）→ `cache_controller.load`（cache_controller.py:910-922）→ `start_loading`（:992-1027）→ `l2_transfer_engine.submit_host_to_device`（异步引擎，ack 走 `ack_load_queue`）——同步提交、异步 ack，同样不阻塞 scheduler 于拷贝。

### 3.4 storage_persisted / storage_restored 与 continuity invariant（要点 4）

标志定义在节点上：unified_tree_core.py:142-153（`storage_written`/`storage_acked`/`storage_persisted`/`storage_restored`）。

- **写 ACK → durable**：`_drain_backup`（unified_radix_cache.py:3156-3210）——backup ack 且 `completed_tokens >= len(host_indices)` 时调 `tree_core.advance_storage_persisted(node_id)`（:3176；实现 unified_tree_core.py:2050-2068，子树提升 :2070-2085）→ 置 `storage_persisted=True` → 唤醒 frontier waiter（:3184-3185）。部分写 ack → `clear_storage_written`（:3201，重写）。
- **恢复 finalize → durable**：`_handle_prefetch_result`（unified_radix_cache.py:2445-2580）→ 插入 host 树后 `tree_core.mark_storage_restored(inserted_node)`（:2554；实现 unified_tree_core.py:2022-2027）→ `storage_restored=True`。
- **统一谓词**：`is_l3_durable`（unified_tree_core.py:2041-2048）= persisted or restored；查询反证 stale 时 `clear_storage_durable`（:2029-2039，e15 语义）。
- **backend 对这些标志零感知**：durability 完全由调用侧 ACK 语义承载（batch_set/batch_set_v2 返回 True = 页已落盘）。**这就是后端可替换性的根基**——新后端只需保证"返回成功 = 数据已持久"，continuity invariant 全部在树层，不动。

### 3.5 配置入口（要点 5）

env 定义（environ.py）：`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR`（:691）/`MAX_SIZE`（:693）/`EVICTION_RATIO`（:694）/`MIN_FREE_SPACE`（:695）/`ENABLE_METADATA_CACHE`（:697）/`METADATA_TTL`（:699）。

流入链：server_args `--hicache-storage-backend`（server_args.py:2790-2809，choices 含 "file"）+ `--hicache-storage-backend-extra-config`（:2818-2822）→ scheduler attach（scheduler.py:4885-4912）→ `tree_cache.attach_storage_backend`（unified_radix_cache.py:3308）→ `cache_controller.attach_storage_backend`（cache_controller.py:593-706）→ `_generate_storage_config`（:754-815，构造 HiCacheStorageConfig，extra_config = 解析后的 JSON dict）→ `StorageBackendFactory.create_backend`（:637-639）→ `_create_builtin_backend` "file" 分支 `backend_class(storage_config)`（backend_factory.py:161-162；注册 :197-199）。

后端内消费：HiCacheFile `__init__` 读 STORAGE_DIR（hicache_storage.py:368）、ENABLE_METADATA_CACHE（:402）、METADATA_TTL（:412）；LRUFileEvictor `_load_config` 读 MAX_SIZE/MIN_FREE_SPACE/EVICTION_RATIO（lru_file_evictor.py:127-148），**extra_config 优先于 env**（:129-131）。extra_config 里还支持 `enable_metadata_cache`/`metadata_ttl`/`max_size`/`min_free_space`/`eviction_ratio` 键（hicache_storage.py:398-414、lru_file_evictor.py:129-142）。

### 3.6 io_uring / liburing（要点 6）

全仓搜索（py/cpp/h/hpp/c/cu/cuh/rs/toml/md/txt/inc/cmake/bzl）关键字 io_uring/liburing/iouring：**sglang 自身代码与依赖声明（environ.py、pyproject.toml、rust/Cargo.toml）零命中**。仅 3 处外部提及：

- storage/flexkv/README.md:40 —— 外部 FlexKV connector 的 apt 依赖 `liburing-dev`（不随本仓构建）；
- storage/nixl/README.md:7,401,509-517 —— 外部 nixl 库能力说明（use_uring 配置项在 nixl 侧）；
- storage/umbp/umbp_store.py:337-345 —— `ssd_io_backend` extra_config 透传给外部 `mori.umbp` 包的 `UMBPIoBackend.IoUring`（import 自 mori，非本仓代码，umbp_store.py:31-46 惰性导入）。

结论：ExtentFileBackend 若要用 io_uring，需要新增依赖（python 绑定或小型 C 扩展），仓库内无既有基础设施可复用。

### 3.7 设计文档（要点 7）

**p2-io-design.md**（/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md，500 行）：

- Part 1（P2-IO-0，:76-171）：page-size sweep 设计（{1,16,32,64}），H0-H3 假说；ps=1 现状 20,911 page/链 = 164 批、ps=64 = ~327 page = 3 批（:94-96）。
- Part 2（P2-IO-1 ExtentFileBackend，:172-302）设计要点：
  - **接口挂载**（:186-204）：继承 HiCacheStorage，实现 v2 三件套（签名核对 :188-197）；挂载走 StorageBackendFactory 动态后端（`--hicache-storage-backend-extra-config` JSON `{backend_name, module_path, class_name}`，backend_factory.py:114-141）——"引擎核心零改动"是选 v2 + 动态后端的理由（:198-201）。
  - **数据布局**（:205-229）：`hicache.data` 单文件，预分配 1-2TB sparse（XFS/ext4；v1 普通文件，后续 O_DIRECT）；RAM 索引 `dict[storage_key → ExtentRef{extent_id, offset, length, generation}]`；storage_key = page_hash（+ 组件后缀）。
  - **extent 聚合规则**（:216-224）：batch_set_v2 内连续 keys 聚合成一个 extent，双限 `min(MAX_PAGES_PER_EXTENT, MAX_BYTES_PER_EXTENT)` 先到为准；**必须按字节双限**（协调人 8MB 估算与实测 ~31KB/token 不符，:219-221）；一次 IO = 一个 extent 一次 read/write；读侧按 extent 分组 → 区间一次读入 → 页切片 copy 到 host_indices；写侧拼 buffer 一次写。
  - **allocator / generation / GC**（:240-252）：append / round-robin extent allocator；每 extent 单调 generation，索引登记，reuse 后失配 = miss；lazy GC 无 WAL/无 daemon，写侧按字节水位（沿用 max_size 20G/min_free 10G）同步回收；崩溃遗留孤儿 extent 由 round-robin 覆盖；不做数据库/B-tree/WAL/持久索引。
  - **continuity invariant 原样保留**（:254-262）：ACK 推进点唯一 = `_drain_backup` advance_storage_persisted（设计引 old 行号 2537-2560，当前工作树实际 :3156-3210/:3176）；ACK 对象从"一页文件写成功"变"一个 extent 中一批连续页写成功"；batch_set_v2 的 transfer 整体成功才 True，部分失败返回 per-key False → 不推进 frontier、整体重写（幂等）；drain/ACK/F2 exactly-once/M2 frontier waiter 全部不动。
  - **验收标准**（:283-291）：restore 20911-token 链 p50 ≤ 0.6s；单链 open/read ≤ 32；元数据 O(extents)；~600-800 行后端 + torch-free 单测，无新依赖；v2 + continuity + M2 + TP/CP 后缀语义原样保留；崩溃 = 全冷、frontier 不损坏。
  - **开放问题**（:293-301）：B1 extent 上限 8-64MB 字节双限（sweep 后标定）；B2 O_DIRECT 时机（v1 普通文件）；B3 单文件 vs per-pool 多文件（v1 单文件）；B4 重启索引重建（v1 全冷，v2 可选文件头目录段）；B5 与 ps=64 HiCacheFile 的取舍裁决点。
  - Part 3（P2-IO-2，:305-461）：restore-vs-recompute 经济模型（T_restore vs T_recompute 闭式公式、break-even 页数阈值、D1/D2/D3 决策点、SLO-aware 截断）。头号数字：ps=1 现状全链 restore 经济上从不划算（每 token 0.5-0.8ms > recompute 0.294ms，:357-361）；ps=64/extent 下阈值 ~320 token。
- 证据引用索引 :477-500。

**p2-promotion-admission.md**（399 行）：**无 ExtentFileBackend/extent 内容**（grep 零命中）——它是 P2-1c H→D promotion 容量预约设计（预算公式 §3.1 :131-171、检查点 §3.2、reservation 生命周期 §3.3、与 M1b 关系 §3.5），被 load_back 预算门引用（unified_radix_cache.py:1735-1762/:1820-1860）。

## 4. summary（ranked findings）

**Critical（替换 HiCacheFile 必读）**：

1. 接口面：`HiCacheStorage` ABC（hicache_storage.py:152-328）+ `HiCacheStorageConfig`/`PoolTransfer`/`PoolTransferResult`/`PoolHitPolicy`（同文件）。v2 三件套是设计文档指定的新后端实现目标；但 unified 路径 KV 主 IO 走 v1（batch_get/batch_set/batch_exists），v2 只在侧车/混合路径被调 —— 新后端必须同时提供 v1 薄封装，或改 controller 的 page_get_func 选择（cache_controller.py:664-675）。
2. 病理位置：`HiCacheFile.get()`（hicache_storage.py:465-487 open+readinto+close 每 key）经 `batch_get`（:489-500）逐 key 循环；写侧 `set()`（:502-549）stat+open+write+rename 逐 key。聚合只到 STORAGE_BATCH_SIZE=128 的调用分批（cache_controller.py:1128/:1356/:1273），后端内部无 IO 合并。
3. 线程/阻塞：L3 读在 prefetch_io_aux_thread、写在 backup_thread、命中查询在 prefetch_thread；scheduler 只提交 + 排空 ack（check_hicache_events，unified_radix_cache.py:3668）；**restore 不阻塞 scheduler 文件 IO**。
4. durability：写 ACK → `advance_storage_persisted`（unified_radix_cache.py:3176）；restore → `mark_storage_restored`（:2554）；谓词 `is_l3_durable`（unified_tree_core.py:2041）。后端零感知 —— ACK 语义即契约。
5. 设计文档：p2-io-design.md Part 2（:172-302）已给出 extent 布局/双限聚合/allocator/generation/GC/验收标准/B1-B5 开放问题，实现可直接照此。

**High**：

6. 配置流：env（environ.py:691-699）→ server_args → scheduler attach（scheduler.py:4885）→ attach_storage_backend（cache_controller.py:593）→ `_generate_storage_config`（:754）→ factory（backend_factory.py:161-162）→ `HiCacheFile(storage_config)`。
7. LRUFileEvictor（lru_file_evictor.py）为 per-file 语义专属（逐 victim os.remove、os.statvfs 水位），extent 后端将替换为 allocator + RAM recency（设计 §2.5）；`MetadataCache`（hicache_storage.py:331-360，TTL dict + 锁）可复用为索引雏形。
8. 测试面：test_hicache_file_lru_unit.py 直接构造 HiCacheFile（:30-31/:113/:267/:470）；test_hicache_spec_file_storage.py:26 断言 expected_storage_backend="HiCacheFile"。
9. io_uring：仓内零依赖零代码，新后端需新增依赖。

**Medium**：

10. sim_storage.py 是接口全实现（v1+v2）的参考后端（8.5KB）；nixl 后端有 STORAGE_BATCH_SIZE 聚合 + 预分配 bounce buffer 先例（hicache_nixl.py:555-595, 725-727）。
11. P2-1 M1b restore 状态机（scheduler_components/hicache_restore.py）与后端无关（纯调度层），替换后端不影响。

## 5. followups

1. **O1 裁决**（设计文档 §2.2 "v1 可 NotImplemented" vs 代码事实）：unified 路径 `_generic_page_get/_generic_page_set`（cache_controller.py:664-665 选择）与 `_storage_hit_query`（:1276 batch_exists v1）要求 v1 接口可用。新后端方案三选一：(a) v1 实现为 v2 的薄封装（HiCacheFile 同款，改动面最小）；(b) 新后端加入零拷贝名单（cache_controller.py:667-675）并实现 batch_get_v1/batch_set_v1；(c) 改 controller 走 v2（超出"引擎零改动"承诺）。需 architect/orchestrator 定夺。
2. **验证 3.1 的"侧车用 v2 / 主 KV 用 v1"双轨**在 HybridCacheController 路径下的完整映射（hybrid_cache_controller.py:606/:696/:731 是 v2 全用），确认 3090 启动（unified 路径）实际 IO 面 = v1 主轨 + v2 侧车。
3. **extent 字节标定依赖**：设计 B1 需 M1 每 page 字节实测（p2-io-design.md:471 T3）与 NVMe 带宽核验（T4）；launch-l3-3090.sh 链 ~640MB/20G 配额（设计引用 :84/:475，脚本在 3090-dev/ 下未在仓库中，需另行确认路径）。
4. **改动面最小化选项核实**：新后端保留 "file" 注册名 vs 新名 + launch 脚本切换（--hicache-storage-backend）——保留 "file" 名则 server_args 零改、测试断言 HiCacheFile 的 2 个文件仍需更新。
5. 设计文档行号 vs 工作树漂移（_drain_backup 设计引 2537-2560，实际 3156-3210）：后续实现引用以本次报告行号为准。

## 6. open_issues

- O1：v1/v2 双轨实现策略未定（见 followup 1）——设计文档与代码事实冲突点，影响新后端方法集。
- O2：`batch_exists_v2` 在 unified 路径未被使用（仅 hybrid 路径 hybrid_cache_controller.py:606）——若 ExtentFileBackend 只优化 v2，unified 路径的命中查询（v1 batch_exists 逐 key stat）仍是 per-key syscall；是否把 `_storage_hit_query` 切到 v2 需裁决（引擎改动 vs 保持零改动）。
- O3：无 fsync 的持久化语义现状（掉电 = cache miss，设计接受）；ExtentFileBackend 的"ACK = 落盘"如何定义（extent 写进页缓存即 ACK？需要 msync/fdatasync 时机）未在设计定稿。
- O4：3090-dev/ 下 launch-l3-3090.sh 未在仓库中（git status 未见），其确切 storage 配置（backend=file、max_size 20G/min_free 10G）来自设计文档引用，未能直接核验。
- O5：HiCacheFile 是否保留（对照基线/回退）未定；保留则 `clear()` 与 evictor 生命周期（detach 时 backend.close() 存在但 HiCacheFile 未实现 close，cache_controller.py:697-698 用 hasattr 防御）不受影响。
