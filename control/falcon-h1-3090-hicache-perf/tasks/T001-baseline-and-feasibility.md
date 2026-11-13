# T001：基线、模型和历史集成可行性

Status: DONE
Work area: research / experiments / ops（只读调查；未启动 GPU 实测）

## Objective
确认 Falcon-H1-7B GPTQ checkpoint 身份与路径，梳理本 fork 已集成的 SGLang/HiCache 代码和历史实测/源权威规则，制定后续公平高并发基线，不触碰 sibling checkout。

## Inputs
- Goal：`control/falcon-h1-3090-hicache-perf/goal.md`
- 本仓库 Git tree、`.memory/phase2-hicache-design/` 历史记录、现有模型文件只读元数据。

## Completion
- 固定模型和 revision，验证本地目录及 checkpoint 文件结构。
- 检索历史 SGLang/HiCache 集成、真实测试/性能记录，并区分适用范围。
- 识别开发源权威历史裁决与当前拓扑差异，避免越权/误导性源码修改。
- 不启动 GPU workload，不改模型文件，不碰 sibling checkout。

## Result
### 模型
- 用户指定：`tiiuae/Falcon-H1-7B-Instruct-GPTQ-Int4`，revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`。
- 当前 agent shell 中 checkpoint 在 `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`；复核时 `/mnt/data/models` 不存在，`/mnt/data` 只含 `archive/`、`debug-gateA/`、`gpu/`、`nerun-dev/`。`/data` 与 `/mnt/data` 当前是不同目录，均位于 `/dev/sda1`，但可能用户终端和 agent 处于不同 namespace/container；不能据一侧观察否定另一侧路径。用户终端展示的 `ls /mnt/data/models/` 暗示其执行环境中模型在那里；两边均为同一固定模型名，但文件身份需要在实际测试 namespace 再核对。
- checkpoint 目录约 7.3G，含 FalconH1 config、GPTQ 4-bit/group-size 128/desc_act 配置、safetensors index 和两片 shard、tokenizer/template。目录内 HF cache tree 与 download metadata 都指向给定 revision；config/index/shard 大小与该 revision tree 匹配。记录的官方 LFS SHA256 是 shard1 `00a9f15ca3dec4de0d4698e638b9d0a3328a1b3a95556b2b17746274ba21f822`、shard2 `2c2fb440852a7450690c6c3229d8db5cf2a1933404209fc6a180906223b67906`；未读取全量权重计算本地哈希。
- 本地代码有 Falcon-H1 model/config 与 0.5B/1.5B 手工 tests；更重要的是 sibling Falcon archive 的 G001 Phase 1 曾实际 bring up 本 GPTQ-Int4 checkpoint，通过 GPTQ-Marlin 权重加载和真实请求，并修复了混合 BF16 attention/GPTQ FFN topology 与 Falcon prefill graph policy。当前 hicache HEAD 继承 canonical Falcon fix（见 O008 记录）；因此不应把此目标描述为 7B 从未 load-smoke。若 T002 发现当前分支偏离归档 Falcon commit，才重新做定向兼容验证。

### Fork 集成历史（本仓库 `.memory` 和 `../sglang/.pi/control/falcon-archive/`）
- 当前 repo 不只是干净上游 SGLang：Git tree 已包含整套 HiCache/Unified Radix/host pool 以及 fork 的 `ExtentFileBackend`（`python/sglang/srt/mem_cache/storage/extent/`）、Rust native L3 write path、Option-C extent relocation、WAL durability/checkpoint 逻辑、HiCache telemetry/Ready-Horizon相关代码，还有 `3090-dev/` gates/harness。
- `.memory/phase2-hicache-design/work/E4-EXTENT-PERFORMANCE-20260912.md` 记录过真实 RTX 3090 L3 集成性能测试（旧 HEAD `4f41f5ba...`、Qwen3.5-GPTQ profile）：FileBackend 的 storage-query p50 17.777s，extent miss query 2.392ms（约 7430x）；extent cold/warm runs 59 requests、0 bad；有 403 extent writes、48 个 positive-hit queries，`sum(kv_hit_pages)=247168`。这是旧 checkpoint 与特定工作负载下的 L3 结果，不是 Falcon-H1、不是本 HEAD 的重现，不证明 Falcon 综合性能已最优。
- `.memory/phase2-hicache-design/work/RECONCILE-REPORT-20260917.md` 记载当时生产 frozen tree 和开发分支有若干源码差异以及明确 DO-NOT-EXECUTE 条款；它是历史证据，不是对当前环境的操作授权。
- `.memory/phase2-hicache-design/work/SOURCE-AUTHORITY-CORRECTION-20260917.md` 有清楚的 owner ruling：当时 `3090-24g-opt` 是唯一开发源权威，hicache 是归档/超集；正式代码在 task worktree 上改，经测试和独立 review 后整合；不许 `git add -A`，只导入 allowlisted 文件/hunks。`.memory/phase2-hicache-design/WORK-INVENTORY-20260914.md` 记载当时 opt→hicache 为父子超集（hicache 只有 3 个 archive commits）。这些都是带日期的历史快照。
- 当前目录实际在 `3090-24g-hicache`，HEAD `1c8c10b7c5cedc0034d44ec02e50a5b22afc2dd5`；当前邻近 `../sglang/` 在 `3090-24g-opt` HEAD `3dc03616d9661a54dd74dc100883140184417440`，两者从 `42693d23bd780a2e21b16dcc8681e0d5156c82f1` 分叉。当前 hicache 有 7 个只在此支线的提交，远程 opt tip `d59bfd4b...` 有 23 个相异提交；不同于 memory 的 2026-09-14 超集状态。Sibling worktree 有大量未提交改动；本任务未碰它。
- 原先只搜本仓库 `.memory`，漏了 sibling 里的完整归档。已找到并只读检查 `../sglang/.pi/control/falcon-archive/G001-phase1` 至 `G004-decode`：
  - **G001 Phase 1** 记录 Falcon-H1-7B-Instruct-GPTQ-Int4/GPTQ-Marlin bring-up、混合 BF16 attention + GPTQ FFN topology 修复、loader tensor-name mutation 修复、Falcon prefill CUDA-graph safe fallback。早期载入与语义问题经 Phase 1D/E 调查；最终记录有正确性/安全 fallback 结论。本分支已经含 canonical Falcon runtime fix，sibling `../sglang/.pi/ops/records/O008-hicache-branch-to-current-repo-change-audit.md` 指向 `2d74d9a582`；不需要从头实现或盲目 cherry-pick。
  - **G003 Phase 2B HiCache L2** 在真实 RTX 3090 验证 Falcon GPTQ-Int4 + FULL/KV 和 MAMBA host pool。PASS 配置：Mamba `extra_buffer`/BF16，HiCache ratio 2、`write_through`、kernel/`page_first`，prefill eager/graph off、decode full graph，L3/storage OFF。B4-R5/B5-INT 记录 device eviction 后 host-only lookup、FULL KV 与 Mamba 两个组件 H→D restore、正确性和稳定性通过。
  - B5 1000 turns correctness/stability PASS。B6 对完全相同 materialized 1000-request trace 做 OFF/ON 各一次 warmup + 三个 measured reps，每次 1000/1000 正确：OFF aggregate 11,365.60 tok/s，ON 11,368.03 tok/s（+0.02%）；E2E -0.02%，TTFT +0.20%。ON 平均 host_hit 2,316 tokens，而 device_hit 约 1.96M tokens；这是此 200-session/1000-turn workload 下的**中性性能结果**，host 复用不足，不是 HiCache 功能失败。报告建议专门测 high-session-pressure/long-dormancy workload；GPU/host 系统资源 telemetry 不完整。
  - **G004 decode saturation** 已结束，HiCache OFF 的 B=1/2/4/8/12/16 throughput 为 68.69/118.68/226.93/397.04/432.48/459.53 tok/s；最终判定无干净的单一优化目标，并明确 G004 完成，不因此自动授权继续 GPU profiling 或优化。该 decode workload 与 HiCache B6 trace 不同，不可直接横比。
  - **未找到 Falcon L3 storage/extent 结果**：G003 明确 L3/storage OFF。Qwen E4 extent 的测量不能外推为 Falcon L3 PASS/性能提升。当前真正待补的是 Falcon 高 host-pressure/长休眠/低 device reuse 的 HiCache L2 与 L3 候选测量，而非重复既有普通 L2 smoke/B5/B6。
- 用户最新明确方向：维持 opt/hicache 两支到最后再谋合并；当前继续在 hicache 推进，若需要可审查后从 opt 借用。Sibling checkout 仍只读，不在其脏工作树上改动。历史 source-authority 文档作为代码来源/审查规则和冲突检查，不再覆盖这条当前明确的双分支安排。

### 设备与路径
- 只读快照：RTX 3090 24GB，driver 580.178.04，当时 1MiB 使用/0%；RAM 125GiB；根盘约 172G 可用。它不是共享 GPU 使用授权。
- 当前 `/data/models` 和根卷在 ext4/QEMU HARDDISK，非已确认本地物理 NVMe。HiCache L3 extent 的文件 I/O 效益需在真实工作负载下测；不因旧 E4 数据预断结果。
- 未下载、复制或改写权重，未启动任何模型/GPU 服务，未进行全文件 hash，未触碰 sibling checkout。

### 基准和风险裁决
- 三组：GPU-only、GPU+L2 host、GPU+L2 host+L3 extent file；固定上述 revision 与代码身份，使用同一共享长前缀多轮请求 trace 与低复用对照，固定到达速率/并发、warmup 和测量期，冷/热阶段分开，每组至少 3 次随机顺序重复。
- 指标：成功请求/token throughput、TTFT/TPOT/E2E p50/p95/p99、queue、errors/timeouts、L1/L2/L3 hits/restore/write/eviction、HBM/host/L3容量、CPU/磁盘 I/O；先过 correctness/stability/capacity/SLO 门槛，再以吞吐、尾延迟和资源代价作 Pareto 综合选择。
- 尚未获得共享 RTX 3090 测试窗口；此外历史 source-authority ruling 指向 opt branch，但当前目标目录是 hicache 且分支已分叉。不能把旧 memory 中 opt-only 工作流默认为已由用户更新/废止，也不能在 sibling checkout 上直接修改。故当前只读研究完成，GPU/源码动作推迟到明确的权限/资源安排。

## Remaining
依据用户明确方向，继续在 `3090-24g-hicache` 推进，两分支最后再整合；需要时从 opt 的干净提交审查借入。RTX 3090 共享测试窗口仍需协调。窗口获批后创建 T002，复核当前分支 Falcon 集成并最小 load-smoke；然后以旧 B5 trace 作低 host-reuse control，另测高 host-reuse 压力 workload，开展 OFF/L2/L2+L3 对比。