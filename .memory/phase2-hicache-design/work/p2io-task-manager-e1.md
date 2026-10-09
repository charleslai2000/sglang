# p2io — task-manager e1 report（P2-IO 第一刀：ExtentFileBackend 替换 HiCacheFile）

## 1. status

done

## 2. artifacts

- 计划文件：/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan-p2io.md（用户指定文件名，task-manager 计划文件）

## 3. evidence（计划自检）

- 上下文已加载：scout 报告（p2io-scout-backend-e1.md 全文 171 行）、p2-io-design.md Part 2（:160-309 实读）、hicache_storage.py（全文 727 行）、ledger.md（全文 83 行）；另核对 cache_controller.py（:593-706/:1085-1212/:1255-1384）、backend_factory.py（全文）、server_args.py（:2785-2834/:8355-8400）、environ.py（:685-709）、pool_host/base.py（:300-317）、launch-l3-3090.sh（全文 180 行）、两个既有测试文件、hicache_spec_storage_common.py（:240-270）、output_streamer.py（:70-107）、hybrid_cache_controller.py（:696-735）；env-var-conventions SKILL 已读（environ.py 改动前置）。
- 状态已检查：.memory/phase2-hicache-design/ 下已有 plan.md（2026-08-30，phase2 旧计划，grep "P2-IO" 零命中，无范围冲突）；work/ 下 55 个历史报告，先例 agent 名（coder/tester/architect/external-scout/reviewer）与 handoff 命名（<task>-<agent>-e<n>）已沿用。
- 计划已重读自检：7 子任务全部具备 goal/affected files/depends_on/parallel/agent/context_budget/acceptance 七要素；depends_on 仅指向前序 id（DAG 无环）；并行组 = {01, 02}（文件域不重叠：environ.py vs backend_factory.py+server_args.py），其余串行（03→04→05 同文件域写者串行，符合 §12）；验收全部为可执行命令 + 预期输出/退出码；Context Boundary 双数组分离（context_files=标准，reference_files=源材料）；Parallel Groups/Epochs/Execution Order/Milestones/Risks(B1-B5)/Missing Information/Suggested Prompt 齐备。
- 关键事实已核实（非仅转述 scout）：零拷贝名单（cache_controller.py:667-675）不含 "extent" → 新后端走 _generic_page_get/_generic_page_set，controller 零改动成立；v2 调用点仅 cache_controller.py:1195（unified 侧车读）+ hybrid_cache_controller.py:606/:696/:731；spec 断言 storage_backend == type(storage_backend).__name__（output_streamer.py:85-95）；launch 脚本切换点 :120-121/:145-148。

## 4. summary

- 子任务数：7（01 envs / 02 factory+server_args 接线 / 03 allocator 纯逻辑核心 / 04 v1+聚合 IO / 05 v2 侧车 / 06 收口+M1 门 / 07 3090 M2 验证）。
- 并行组：Batch 1 = {01, 02}（并行）；Batch 2 = {03}；Batch 3 = {04}；Batch 4 = {05}；Batch 5 = {06}；Batch 6 = {07}（串行链）。
- 依赖链结构：01/02（根）→ 03 → 04 → 05 → 06 → 07；04 依赖 03、05 依赖 04（同文件 extent_file_backend.py 串行写）、06 依赖 04+05、07 依赖 06。
- Agent 建议：01-05 coder（S/S/M/M/M），06 tester（M1 门），07 tester（M2 3090，含 launch 脚本切换）；无 FAST 档建议（无涉密材料，但 07 涉及 3090 部署与 4c 并行窗口，归 tester 验证域）。
- Epoch：6 段，handoff 文件 work/p2io-<agent>-e<n>.md（E1 双 coder 报告）。
- 测试策略：新套件 test_extent_file_backend_unit.py（torch-free，bytearray 页 + mock HostKVCache，register_cpu_ci 同 lru 样板）；覆盖 allocator 回绕 / generation 失效 / GC 水位（03）/ v1 round-trip+聚合 pread 计数+craash 全冷+stats（04）/ v2 前缀+命中策略+侧车（05）/ full-file 跨批端到端+clear+重启全冷+factory 实例化（06）；既有文件适配：spec 兄弟类 TestHiCacheSpecExtentStorage（.bin 计数等待谓词改 extent 语义）、lru 与 radix-unittest 保持不动纳入回归门。

## 5. followups

1. Missing Information 第 1 项：SGLANG_L3_BACKEND 消费点与命名（server_args 默认回退 + launch ${L3_BACKEND:-file} vs 备选名 SGLANG_HICACHE_STORAGE_BACKEND）——orchestrator 确认后 01/02 即可派发。
2. Missing Information 第 2 项：extent 默认 64MiB（计划默认）vs 128MiB——影响 03 默认值与 07 的 extent 数标定，建议 64MiB 先行。
3. Missing Information 第 4 项：3090 盒访问通道与 4c 窗口协调——07 派发前置条件，属部署环境事实，需 orchestrator 给出。
4. 06 中 `git status --porcelain` 零改动面固化：建议 M1 通过后由 reviewer 或 orchestrator 复核改动面清单（本计划文件列表为准）。
5. B1 标定（8-64MB sweep）建议作为 M2 之后的独立子任务，输入 = 07 的带宽/每页字节实测，不阻塞第一刀。

## 6. open_issues

- O1：SGLANG_L3_BACKEND 命名与消费点未定（计划假设：server_args 默认回退 + launch 脚本 ${L3_BACKEND:-file}）。
- O2：extent 默认尺寸 64MiB vs 128MiB 未定（ledger 允许两者）。
- O3：HiCacheFile/"file" 保留与否未定（scout O5；计划默认保留，若删除则 06 适配范围扩大）。
- O4：M2 执行环境（3090 盒通道、docker/native、与 4c 协调）未确认。
- O5：O_DIRECT 是否进第一刀验收未定（计划：buffered 达标即过，O_DIRECT 留标定档；对齐约束已在计划 Risks B2 注明）。
- O6：spec 兄弟类实跑归属（CI-only vs M2 实跑）未定。
