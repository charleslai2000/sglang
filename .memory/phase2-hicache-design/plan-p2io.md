# Plan: p2-io-extent-backend

## Goal

P2-IO 第一刀：实现 `ExtentFileBackend(HiCacheStorage)`，替换 HiCacheFile 作为 L3 主后端，把 20,911-page 链 restore 从 11-12s（每 key open+read+close ≈ 63K syscall 串行）压到 <1s（每 extent 一次大块 read）。单预分配大文件 + RAM dict[key→ExtentRef{extent_id, offset, length, generation}] + append/circular allocator + generation 失效 + 水位 lazy GC + crash 整盘作废（无 metadata persistence）+ 写 ACK 后才 publish。**必须完整实现 v1（get/set/batch_get/batch_set/exists + batch_exists 覆盖）**：主 KV 路径走 v1 batch 接口（controller 侧 STORAGE_BATCH_SIZE=128 分批），batch 入口内按 extent 邻近聚合 → 一次大块同步 read（无 liburing）。v2 三件套照做（侧车池语义）。backend_factory 注册 + environ.py 新 env。引擎核心（scheduler/unified_radix_cache/cache_controller/tree_core）零改动。目标 ~600-800 行、无新 pip 依赖。验收：本机单测全绿；3090 上 640MB restore 11-12s → <1s；open-read 系统调用 ≤32/state；p50 ≤0.6s。

已核实的事实基线（scout e1 + 本次核对，行号以当前工作树为准）：

- 接口：`HiCacheStorage` ABC（hicache_storage.py:152-328）；v1 抽象方法 get/set/batch_get/batch_set/exists + batch_exists 基类默认逐 key（:311-322）；v1 主路径调用点：`_generic_page_get`→`backend.batch_get(hashes, dummy_pages)`（cache_controller.py:1093-1116）、`_generic_page_set`→`backend.batch_set(hashes, data)`（:1340-1345）、`_storage_hit_query`→`backend.batch_exists`（:1261-1284）；零拷贝名单（hf3fs/mooncake/eic/nixl/simm/mori/dynamic+interface_v1，:667-675）**不含新名 → 新后端走 generic 路径，controller 零改动**。
- v2 调用点：unified 路径侧车读 `batch_get_v2`（cache_controller.py:1195）；hybrid 路径 batch_get_v2/set_v2（hybrid_cache_controller.py:696/:731）、batch_exists_v2（:606）。
- durability 契约：后端零感知，ACK 即契约（_drain_backup→advance_storage_persisted，unified_radix_cache.py:3156-3210；restore→mark_storage_restored :2554）。
- 配置流：env（environ.py:691-699）→ server_args（--hicache-storage-backend choices :2790-2809）→ scheduler attach（scheduler.py:4885）→ cache_controller.attach（:593）→ `_generate_storage_config`（:754）→ factory（backend_factory.py:161-162/:197-199）。
- 池 API：`get_data_page(index, flat=True)` / `get_dummy_flat_data_page()` / `set_from_flat_data_page(index, data_page)`（pool_host/base.py:300-317）。
- 3090 launch：launch-l3-3090.sh（180 行，/home/charles/Workspaces/homenet/server/gpu/3090-dev/）现用 `--hicache-storage-backend file` + extra_config `{"max_size":"20G","min_free_space":"10G"}`（:120-121）+ env SGLANG_HICACHE_FILE_BACKEND_*（:145-148, :173-176）；链 ~640MB/20G 配额。

## Subtasks

| id | goal | affected files | depends_on | parallel | agent | context_budget | acceptance |
|---|---|---|---|---|---|---|---|
| 01 | environ.py 新增 extent 后端 env 族（SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR/MAX_SIZE/MIN_FREE_SPACE/EXTENT_SIZE/FILE_SIZE/DIRECT_IO + 选择器 SGLANG_L3_BACKEND），命名与现有 SGLANG_HICACHE_FILE_BACKEND_* 风格一致，挂在 "HiCache storage backends" 段注释下 | python/sglang/srt/environ.py | — | true | coder | S (≤40K) | `grep -n -E "SGLANG_HICACHE_EXTENT_BACKEND_|SGLANG_L3_BACKEND" python/sglang/srt/environ.py` 恰 7 行（6 配置 + 1 选择器）；`python3 -c "from sglang.srt.environ import envs; assert envs.SGLANG_L3_BACKEND.get() is None; assert envs.SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE.get() is None"` 退出 0；DIRECT_IO 为 EnvBool(False)（grep 验证） |
| 02 | backend_factory 注册 "extent" 内置后端（懒加载，指向 sglang.srt.mem_cache.storage.extent.extent_file_backend.ExtentFileBackend）+ server_args：choices 加入 "extent" + `--hicache-storage-backend` 未显式给出时回退 `envs.SGLANG_L3_BACKEND`（配置层，非引擎核心） | python/sglang/srt/mem_cache/storage/backend_factory.py；python/sglang/srt/server_args.py | — | true | coder | S (≤40K) | `python3 -c "from sglang.srt.mem_cache.storage.backend_factory import StorageBackendFactory; assert 'extent' in StorageBackendFactory._registry; print('ok')"` 退出 0 且打印 ok；`grep -n '"extent"' python/sglang/srt/server_args.py` ≥1（choices 内）；`grep -n "SGLANG_L3_BACKEND" python/sglang/srt/server_args.py` ≥1；`python3 -c "import sglang.srt.server_args"` 退出 0 |
| 03 | 新包 storage/extent/：extent_allocator.py 纯逻辑核心（ExtentRef 用 msgspec.Struct(frozen)；circular allocator；slot generation 单调递增；RAM 索引 dict[key→ExtentRef] + slot 反查 + recency；字节水位 lazy GC：used_bytes > max_size×eviction_ratio 或磁盘 free < min_free_space 时回收最旧 slot；reuse 即 generation++）；配 torch-free 单测（allocator 回绕 / generation 失效 / GC 水位） | python/sglang/srt/mem_cache/storage/extent/__init__.py（新）；python/sglang/srt/mem_cache/storage/extent/extent_allocator.py（新）；test/registered/unit/mem_cache/test_extent_file_backend_unit.py（新，本子任务只落 allocator 用例） | 01 | false | coder | M (≤80K) | `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -k "alloc or gen or gc or watermark" -q` 退出 0 且全部通过；allocator 模块零 torch import（`grep -c "import torch"` 该文件 = 0）；extent_size 默认 64MiB 且强制 4096 倍数（越界断言单测在） |
| 04 | extent_file_backend.py：v1 全实现 + 聚合 IO 核心。config 解析（extra_config 优先于 env，沿用 lru evictor 先例）；config_suffix 隔离复刻（hicache_storage.py:370-390 语义）；预分配 sparse 文件 + 持久 fd；字节转换走 duck-typed memoryview helper（torch 张量 .numpy() / 测试用 bytearray，模块顶层不 import torch）；batch_set：批次内连续 keys 聚合成 extent（按字节 ≤ extent_size 双限，超限切多个 extent）→ 每 extent 一次 pwrite；batch_get：按 extent 分组 → [min_offset..max_offset+len) span 一次 pread → 页切片写回 target；get/set/exists 薄封装；batch_exists 覆盖为纯 RAM 命中数（O(batch)）；generation 读写双端校验（失配 = miss 且删条目）；写 ACK 语义 = pwrite 成功 + 索引登记后返回 True；get_stats() 维护 io 计数器（pread/pwrite/open 累计）供单测与 M2 判据 | python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py（新） | 03 | false | coder | M (≤80K) | `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -k "v1 or batch or exists or crash or stats or aggregate" -q` 退出 0 且全部通过；聚合用例：100 key 一批（同 extent）读 → stats 中 pread 增量 = 1（mock/patch 双保险：patch.object(os,'pread',wraps=os.pread) 计数相等）；crash 语义用例：关实例后同目录重建 → 全 key exists False、get None、stats 归零；>128 key 跨批写入 → 多 extent 正确 round-trip |
| 05 | v2 三件套（batch_exists_v2 最长前缀 + ALL_PAGES/TRAILING_PAGES 逐池语义；batch_get_v2/batch_set_v2 按 transfer 走 registered_pools + 组件 key 独立 extent）——逻辑移植 HiCacheFile v2（hicache_storage.py:604-712）但全部 RAM 索引 + extent 聚合 IO；配 torch-free 单测（v2 round-trip / 前缀语义 / 侧车池 mock） | python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | 04 | false | coder | M (≤80K) | `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -k "v2 or sidecar or prefix" -q` 退出 0 且全部通过；侧车池用 mock HostKVCache（get_data_page/set_from_flat_data_page/page_size 三方法）驱动；KV 页与组件 key 索引条目互不串池（断言 key 命名含 ".mamba"/".swa" 后缀隔离） |
| 06 | 收口：新单测全量 + 现有测试适配 + M1 本机门。适配点：test_hicache_spec_file_storage.py 增兄弟类 TestHiCacheSpecExtentStorage（storage_backend="extent"，expected_storage_backend="ExtentFileBackend"，页数等待谓词从 .bin 计数改为 extent 语义，即"首个请求 restore 成功"）；test_hicache_file_lru_unit.py 与 test_unified_radix_cache_unittest.py（HiCacheFile stub 用途）保持不动但纳入回归门；full-file 端到端（>128 页多批跨 extent）+ clear() + 重启全冷 + factory create_backend("extent") 真实实例化 | test/registered/unit/mem_cache/test_extent_file_backend_unit.py；test/registered/hicache/test_hicache_spec_file_storage.py；回归：test/registered/unit/mem_cache/test_hicache_file_lru_unit.py、test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py | 04, 05 | false | tester | M (≤80K) | `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py test/registered/unit/mem_cache/test_hicache_file_lru_unit.py test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py -q` 退出 0 全绿（M1 门）；`python3 -m pytest test/registered/hicache/test_hicache_spec_file_storage.py --collect-only -q` 退出 0 且输出含 TestHiCacheSpecExtentStorage；`python3 -c "from sglang.srt.mem_cache.storage.backend_factory import StorageBackendFactory; from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig; b=StorageBackendFactory.create_backend('extent', HiCacheStorageConfig(tp_rank=0,tp_size=1,pp_rank=0,pp_size=1,attn_cp_rank=0,attn_cp_size=1,is_mla_model=False,enable_storage_metrics=False,is_page_first_layout=True,model_name='t',extra_config={}), None); assert type(b).__name__=='ExtentFileBackend'; print('ok')"` 退出 0 打印 ok；`git status --porcelain` 只显示本计划列出的文件（引擎核心零改动证据） |
| 07 | 3090 验证（M2）：launch-l3-3090.sh 后端切换 `--hicache-storage-backend "${L3_BACKEND:-file}"` + extent env 注入（STORAGE_DIR 新命名空间）；跑 20911-token 链 restore，t38c 日志测 prefetch_io_finished-issued 间隔；get_stats io 计数或 strace 窗口验证 open/read ≤32/state；p50 判据 | /home/charles/Workspaces/homenet/server/gpu/3090-dev/launch-l3-3090.sh | 06 | false | tester | M (≤80K) | 3090 上 3+ 次 restore：单 state 从 issued 到 io_finished < 1.0s；恢复窗口 io 计数（get_stats 增量或 `strace -f -e trace=openat,pread64 -c` 捕获）openat ≤32 且 pread64 ≤32；p50 ≤ 0.6s；file 后端同 smoke 不回归（可选对照）；全程不中断 4c（K=32 margin=16384）运行 |

## Context Boundary

**01（envs）**
- context_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/skills/env-var-conventions/SKILL.md", "reason": "必须读技能：新增 SGLANG_* env 前强制要求（Rule 1-3：Envs 类定义、EnvField API、命名）"}]
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/environ.py", "lines": "686-709", "reason": "HiCache storage backends 段注释与现有 SGLANG_HICACHE_FILE_BACKEND_* 定义风格（EnvStr/EnvBool 用法）"}]

**02（wiring）**
- context_files: []
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/storage/backend_factory.py", "lines": "16-63, 196-251", "reason": "register_backend 签名 + 内置注册块（"file" 为对照样板）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/server_args.py", "lines": "2790-2822", "reason": "--hicache-storage-backend 参数与 choices 列表（需加 "extent"）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/server_args.py", "lines": "8355-8400", "reason": "hicache 校验/解析段，SGLANG_L3_BACKEND 默认回退落点参考"}]

**03（allocator 核心）**
- context_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/general-code-style.md", "reason": "新代码风格（小而纯、protected 方法、构造期解析静态值）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/no-dataclasses.md", "reason": "新容器必须 msgspec.Struct（ExtentRef），禁止 dataclass"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/comment-style.md", "reason": "注释纪律（跨边界约束、magic number 出处）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/unit-test-admission.md", "reason": "新单测准入：allocator 回绕/generation/GC 用例须守卫真实失效模式（derived property）"}]
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/p2io-scout-backend-e1.md", "reason": "侦察报告全文（设计要点摘要 :117-131、接口事实）"}, {"path": "/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md", "lines": "240-262", "reason": "§2.5 allocator/generation/GC 设计 + §2.6 continuity（ACK 对象页→extent）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/ledger.md", "lines": "14-38, 70-84", "reason": "首版规格（固定 64MB/128MB extent、circular、crash 整盘作废）与 O1 裁决"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py", "lines": "127-148", "reason": "_parse_size_to_bytes 与 extra_config 优先于 env 的解析先例（可复用/import）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hicache_storage.py", "lines": "26-40", "reason": "HiCacheStorageConfig 字段（extra_config 承载 extent 配置键）"}]

**04（v1 + 聚合 IO）**
- context_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/general-code-style.md", "reason": "函数 <100 行、核心函数像伪代码"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/comment-style.md", "reason": "O_DIRECT/对齐/ACK 语义等跨边界约束注释"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/unit-test-admission.md", "reason": "聚合正确性/IO 计数/crash 语义用例准入"}]
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hicache_storage.py", "lines": "152-328", "reason": "ABC 签名（v1 方法返回语义）+ HiCacheStorageExtraInfo"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hicache_storage.py", "lines": "363-561", "reason": "HiCacheFile 对照实现：config_suffix 构造 :370-390、get/set/batch 语义、无 fsync 现状"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/cache_controller.py", "lines": "1093-1116, 1261-1284, 1340-1345", "reason": "v1 主路径三个调用点（batch_get 传 dummy 页列表 / batch_exists 命中数 / batch_set 传 flat 页列表）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/pool_host/base.py", "lines": "300-317", "reason": "flat 页三 API 签名"}, {"path": "/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md", "lines": "205-262", "reason": "§2.3-2.6 数据布局/读写路径/聚合规则/continuity"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/storage/sim_storage.py", "lines": "1-254", "reason": "v1+v2 全实现的参考后端（254 行，接口语义对照）"}]

**05（v2 侧车）**
- context_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/unit-test-admission.md", "reason": "前缀/命中策略用例准入（协议语义 derived property）"}]
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hicache_storage.py", "lines": "94-149, 604-712", "reason": "PoolTransfer/PoolHitPolicy/PoolTransferResult 数据类 + HiCacheFile v2 语义（最长前缀/ALL_PAGES/TRAILING_PAGES/_batch_io_v2 逐 transfer 循环）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/cache_controller.py", "lines": "1184-1212", "reason": "unified 侧车读调用（batch_get_v2，kv_derived_transfers）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py", "lines": "696-735", "reason": "hybrid 路径 v2 读写调用语义（只读参考）"}, {"path": "/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md", "lines": "216-228", "reason": "§2.3 组件 key 独立 extent、exists 走 RAM O(1) 语义"}]

**06（收口 + 适配）**
- context_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/rules/unit-test-admission.md", "reason": "测试增删准入（mirror 禁入、bookkeeping 保留）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.claude/skills/write-sglang-test/SKILL.md", "reason": "测试放置/CI 注册/夹具机制（register_cpu_ci 用法）"}]
- reference_files: [{"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/test/registered/unit/mem_cache/test_hicache_file_lru_unit.py", "lines": "1-135", "reason": "CPU 单测样板：register_cpu_ci、CustomTestCase、_make_config 夹具（新测试文件照此结构）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/test/registered/hicache/test_hicache_spec_file_storage.py", "lines": "1-89", "reason": "适配对象：storage_backend/expected_storage_backend 类属性 + .bin 计数等待谓词（:40-72）需为 extent 语义改版"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/test/hicache_spec_storage_common.py", "lines": "240-270", "reason": "断言 storage_backend==类名（output_streamer 报 type(storage_backend).__name__），extent 兄弟类预期 "ExtentFileBackend""}]

**07（3090 M2）**
- context_files: []
- reference_files: [{"path": "/home/charles/Workspaces/homenet/server/gpu/3090-dev/launch-l3-3090.sh", "lines": "70-180", "reason": "切换点：ARGS 里 --hicache-storage-backend file（:120-121）→ ${L3_BACKEND:-file} + extent env 注入（:145-148/:173-176 样板）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/ledger.md", "lines": "39-68", "reason": "3090 环境事实（12 核、/data 29G 余、无 liburing）+ 每请求耗时标定表（判据参照）"}, {"path": "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/tester-e8.md", "reason": "restore 延迟测量方法先例（t38c 埋点 issued→io_finished）"}, {"path": "/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md", "lines": "283-291", "reason": "§2.8 验收标准六项（p50≤0.6s / open-read≤32 / O(extents) / 无新依赖 / 兼容 / 崩溃语义）"}]

## Parallel Groups

- **Batch 1 = {01, 02} 并行**：文件域不重叠（environ.py vs backend_factory.py+server_args.py），无共享运行时/资源风险；02 不依赖 01（SGLANG_L3_BACKEND 消费点在 server_args 内是编译期字符串引用，01 的 EnvField 先于 02 落地即可，靠 01 验收门串接）。
- **Batch 2 = {03}**：依赖 01（config 用 env 名）。
- **Batch 3 = {04}**：依赖 03（allocator 是 IO 层的地基）。
- **Batch 4 = {05}**：依赖 04（与 04 同文件域 extent_file_backend.py，写者串行；v2 复用 v1 的聚合/索引原语）。
- **Batch 5 = {06}**：依赖 04+05（M1 门）。
- **Batch 6 = {07}**：依赖 06（M2 门）。

串行链 03→04→05 是同一模块自底向上的三个层次（纯逻辑 → v1 IO → v2 侧车），每步可独立 pytest 验证，不做并行以规避同文件写冲突（orchestrator §12 同工作区写者默认串行）。

## Epochs

- **E1**：Batch 1（01, 02）→ 各写 handoff：`work/p2io-coder-e1-01.md`、`work/p2io-coder-e1-02.md`。
- **E2**：Batch 2（03）→ `work/p2io-coder-e2-03.md`（新 epoch 从磁盘状态起，不依赖 E1 会话）。
- **E3**：Batch 3（04）→ `work/p2io-coder-e3-04.md`。
- **E4**：Batch 4（05）→ `work/p2io-coder-e4-05.md`。
- **E5**：Batch 5（06，M1 门）→ `work/p2io-tester-e5-06.md`。
- **E6**：Batch 6（07，3090 M2）→ `work/p2io-tester-e6-07.md`。

每个 epoch 边界 = 新鲜上下文轮换点；handoff 报告必须含：本步完成的文件清单 + 验证证据（命令+退出码）+ 留给下一步的接口契约（类/方法签名、env 名、配置键）。

## Execution Order

1. E1：01（envs）与 02（factory + server_args）并行落。
2. E2：03 allocator 纯逻辑 + 其单测（回绕/generation/GC 水位）。
3. E3：04 v1 全实现 + 聚合 IO + 单测（round-trip/聚合计数/crash 全冷/stats）。
4. E4：05 v2 三件套 + 单测（前缀/命中策略/侧车池）。
5. E5：06 收口（新套件全量 + spec 兄弟类 + 回归门）→ **M1 本机绿**。
6. E6：07 3090 切换与测量 → **M2**。

## Milestones

- **M1（本机绿）**：06 验收门 —— `pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py + test_hicache_file_lru_unit.py + test_unified_radix_cache_unittest.py` 全绿；spec 兄弟类可 collect；factory 实例化真实 ExtentFileBackend；git status 仅列计划内文件。完成即向 orchestrator 报告，可进 M2。
- **M2（3090 验证）**：07 —— 20911-token 链 restore <1s（目标 p50 ≤0.6s）、open/read ≤32/state、无新依赖、file 后端对照不回归；与 4c（K=32 margin=16384）自然结束协调，不中断其运行。

## Risks and B1-B5 Handling（含 O_DIRECT 对齐要求）

| # | 项 | 处理建议（第一刀范围） | 落点 |
|---|---|---|---|
| B1 | extent 上限值 | **固定 64MiB 默认（ledger 定案"固定 64MB/128MB"取小档），配置键 extent_size（env + extra_config，强制 4096 倍数）**；字节双限 = min(extent_size, 批次剩余字节)；8-64MB 标定（sweep）**不在第一刀**，延后为独立标定任务，输入 = M2 实测带宽与每页字节 | 03（默认值+断言）、07（收集标定输入） |
| B2 | O_DIRECT 时机 | **第一刀用普通 buffered IO**（设计 B2 "v1 普通文件"）：持久 fd + os.pread/pwrite 显式偏移，消除每 key open/close；**O_DIRECT 语义与页粒度冲突**：O_DIRECT 要求 offset/length/缓冲均 4KiB 对齐，而 ps=1 每页 ~31KB 非 4096 倍数 → 只对整 extent 对齐 IO 才安全 → DIRECT_IO env（默认 False）预留为后续标定档；buffered 模式崩溃丢脏页恰好与"crash 整盘作废"语义自洽 | 04（buffered 实现）、01（DIRECT_IO env 预留） |
| B3 | 单文件 vs 多文件 | 单文件（hicache.data sparse 预分配，FILE_SIZE 默认 64GiB）v1 定案 | 04 |
| B4 | 重启索引重建 | v1 全冷：重启 = 索引空 = 整盘作废，allocator 从头开始；不读文件头 | 04（crash 语义单测） |
| B5 | 与 ps=64 HiCacheFile 取舍 | 裁决点属 orchestrator（M2 数据输入 §2.8 五维表）；HiCacheFile + "file" 注册名**保留**（对照基线 + 回退，scout O5 建议），extent 以新名注册 | 02、06（回归门） |
| R1 | ACK = 落盘 的定义（scout O3） | 第一刀：pwrite 成功（进页缓存）即 ACK + 索引登记后才 publish；无 fsync（现状同语义，设计接受）；掉电 = cache miss | 04 |
| R2 | 并发读写 | 单写线程（backup_thread）+ 读线程（prefetch_io_aux）共享持久 fd；pread/pwrite 显式偏移天然线程安全；索引操作单锁；读侧先取 refs（锁）→ IO（无锁）→ generation 复检（锁），失配 = miss | 04 |
| R3 | 同 key 重写 | append 新 extent + 更新索引（旧条目变孤儿由 GC 回收）；不 in-place 覆盖，幂等重写语义与 controller 部分失败重写一致 | 04 |
| R4 | extent 大小/聚合块标定落点 | 聚合块 = extent_size 单键控；标定（B1 sweep）独立子任务，依赖 07 的 M2 带宽/每页字节实测输入 | 07 输出 → 后续 |
| R5 | 3090 资源 | M2 须等 4c（K=32 margin=16384）自然结束或与 orchestrator 协调窗口；4c 全程不受扰动 | 07 |
| R6 | 引擎零改动回归风险 | 06 用 `git status --porcelain` 固化改动面；file 后端对照 smoke（07 可选） | 06、07 |

## Missing Information

1. **SGLANG_L3_BACKEND 消费点未指明**：任务要求"environ.py 新增 env（如 SGLANG_L3_BACKEND=extent）"但未说谁消费。计划假设：server_args 中 `--hicache-storage-backend` 未显式给出时回退该 env（配置层 2-3 行，非引擎核心）+ launch 脚本 `--hicache-storage-backend "${L3_BACKEND:-file}"`。备选命名 `SGLANG_HICACHE_STORAGE_BACKEND`（更贴近现有 SGLANG_HICACHE_* 前缀）——待确认用哪个。
2. **extent 默认尺寸二选一**：ledger 写"固定 64MB/128MB extent"。计划取 64MiB（10 extent/640MB 链，满足 open-read ≤32 且聚合块更小、GC 粒度更细），128MiB 仅改 env 即可切换——待确认默认档。
3. **HiCacheFile / "file" 是否保留（scout O5）**：计划保留（对照基线 + 回退，两个既有测试文件零改）。若用户裁决删除，06 的适配范围将扩大为把 lru 单测改指 extent 语义——需确认。
4. **M2 执行环境**：3090 盒（12 核、/data 197G 剩 29G）与本机关系、SSH/部署通道、docker vs native（launch 脚本默认 docker）——第一刀开发全在本机（ledger 已定），M2 部署机制待 orchestrator 确认。
5. **DIRECT_IO 档是否进第一刀验收**：计划默认 False（buffered），M2 判据按 buffered 达标（带宽受限路径，冷读 1.1GB/s → 640MB ≈ 0.58s 与目标吻合）。若要求 O_DIRECT 进第一刀验收，需在 04 增加对齐缓冲实现（mmap 匿名页对齐缓冲 + extent 级对齐约束）——待确认。
6. **spec 兄弟类（TestHiCacheSpecExtentStorage）是 CI-only 还是 M2 在 3090 实跑**：EAGLE3 spec E2E 需 GPU+模型，本机无 3090；计划列为代码交付 + collect-only 验证，实跑归 M2/CI——待确认。

## Suggested Prompt

请确认以下 6 项（对应 Missing Information）：

1. SGLANG_L3_BACKEND 消费点与命名：server_args 默认回退 + launch 脚本 ${L3_BACKEND:-file}，命名取 SGLANG_L3_BACKEND 还是 SGLANG_HICACHE_STORAGE_BACKEND？
2. extent 默认尺寸：64MiB（计划默认）还是 128MiB？
3. HiCacheFile 与 "file" 注册名是否保留（计划：保留，作对照基线与回退）？
4. M2 部署通道：3090 盒如何访问（SSH 主机名/用户）、docker 还是 native 模式、与 4c 的窗口协调由谁负责？
5. O_DIRECT 是否进第一刀验收（计划：buffered 达标即 M2 通过，O_DIRECT 留标定档）？
6. spec E2E 兄弟类的实跑归属（CI 还是 M2 在 3090 实跑）？

若以上按计划默认值通过，本计划可直接派发：Batch 1 = {01, 02}（并行，coder），Batch 2 = {03}（coder），Batch 3 = {04}（coder），Batch 4 = {05}（coder），Batch 5 = {06}（tester，M1 门），Batch 6 = {07}（tester，3090 M2）。
