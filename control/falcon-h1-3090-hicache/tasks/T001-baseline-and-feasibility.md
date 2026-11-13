# T001：基线与实验可行性

Status: DONE
Work area: research / experiments / ops（只读调查完成；GPU实验仍待协调）

## Objective
确认 Falcon-H1-7B 的准确公开模型/权重身份、许可和 SGLang 支持状态；确认本工作树及 RTX 3090 所需软件/HiCache host+disk 能力；制定能公平比较 GPU-only、GPU+host、GPU+host+disk 的高并发服务基线方案。保全并审查现有本地变更，不触碰 `../sglang/` 工作树。

## Inputs
- Goal：`control/falcon-h1-3090-hicache-perf/goal.md`
- Plan：`control/falcon-h1-3090-hicache-perf/plan.md`
- 当前仓库分支和工作树状态；本地项目说明与 HiCache 代码。
- 公开模型卡/权重仓库和 SGLang 当前模型支持代码。
- GPU/驱动/内存/存储信息：只读盘点；服务/缓存操作须先确认影响和授权。

## Completion
- 有来源证据记录模型 ID、revision、许可、配置/架构特征及权重下载/哈希计划；说明能否由本分支 SGLang 加载 Falcon-H1-7B。
- 识别当前工作树已有改动及其所有权/风险；不覆盖、不清理。
- 从代码与配置证据确认 HiCache 的 host 与 disk 分层接口、数据路径、限制和所需设置；若 disk 本非 HiCache 后端，准确界定可测路径，不虚构能力。
- 检查但不占用/改变共享 GPU 服务，记录 RTX 3090 可用性/驱动环境及需协调事项。
- 给出固定的负载矩阵、warm-up/测量/重复策略、指标及可判定的综合排序规则；若必须 GPU 测试，先明确用户协调/设备安全条件，再提出下一任务。
- 将结论、阻塞和下一步写回本任务与 Goal plan，并同步 frontier。

## Result
- **基线**：本仓库 `3090-24g-hicache`，HEAD `1c8c10b7c5cedc0034d44ec02e50a5b22afc2dd5`；`git status` 调查时仅看到此前的未跟踪 `AGENTS.md`、`control/`，未发现源码已跟踪文件改动。本任务创建后 `control/` 是本 Goal 的受控新增。未触碰旁边 `../sglang/`。
- **公开模型身份**：通过 Hugging Face Hub 官方 API 读取 `tiiuae/Falcon-H1-7B-Instruct` revision `41e72f27effbab80cd45b6e884688452253a3686`、license 标记 `other`，四片 safetensors（需遵守模型卡/权重的具体许可条款，API 的 `other` 不能替代许可审查）。`tiiuae/Falcon-H1-7B-Base` revision `c9a4cbb95c01b1ede39f69eda083d03d8903b8f0`，同为 `other`。Instruct config 在固定 revision 返回 `model_type=falcon_h1`、`architectures=[FalconH1ForCausalLM]`、BF16、44 layers、hidden size 3072、最大位置 262144。下载尚未进行；实验时应 pin revision，记录文件清单、哈希与模型卡许可。
- **SGLang 支持**：本地存在 `python/sglang/srt/configs/falcon_h1.py`、`models/falcon_h1.py`，且 `test/manual/models/test_falcon_h1_models.py` 有 0.5B/1.5B 手工服务测试；没找到 7B 手工测试。代码架构可识别并不证明这个特定 7B checkpoint 在本分支、单张 3090 和选定 dtype/上下文下运行成功，仍需有授权的模型加载 smoke test。
- **HiCache tiers**：文档与 `StorageBackendFactory` 确认 L2 是 host DRAM；L3 可用 `file` 或本分支注册的 `extent` 文件后端（`extent` 通过 `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` 在聚合 extent 文件上读写，绝非 RAM cache）。`HiCacheFile` 文档标为演示用途；extent 实现以本地单文件/extent、批量 pwritev/pread 为目标，源码注释描述 buffered IO 与对应的 WAL/持久化语义。能否有效跑到磁盘及其设备吞吐必须实测；当前 `/` 是 ext4 上的 QEMU HARDDISK 虚拟块设备，`findmnt/lsblk` 未暴露底层物理 NVMe，不能把它当作已确认的物理 SSD。测试 L3 应用隔离的专用新目录，先做配置/容量安全检查；不得清空或复用现有缓存路径。
- **只读硬件快照**：`nvidia-smi` 显示 RTX 3090 24,576 MiB、580.178.04 驱动、显存使用 1 MiB、GPU 利用率 0%。`ps`/`ss` 未发现本机 SGLang 推理进程/端口；该瞬时空闲状态不代表已获共享设备授权。主机 RAM 125 GiB（available 123 GiB）；根文件系统约 484G 总量、172G 可用。启动任何 GPU/model workload 前仍需遵循共享 GPU 协调偏好并重新检查。
- **负载协议提案**：固定模型 checkpoint、SGLang HEAD/补丁、sampling、max-running、KV dtype、上下文与到达过程；采用可重放的 prefix-heavy 多轮请求混合（共享系统前缀 + 不同 suffix），并另设低复用对照；各组分别 GPU-only、GPU+host HiCache、GPU+host+extent L3，比较 cold start/cold L3、L3 warm、host hit、GPU prefix hit。每组先相同 warm-up，固定到达率/并发阶梯并至少重复 3 次、随机化组序；记录 request/token throughput、TTFT/TPOT/E2E p50/p95/p99、命中/restore/evict、排队、错误/超时、HBM/host/L3 占用、CPU/磁盘吞吐与 I/O wait。以正确性、零崩溃、容量约束为硬门槛，再以目标并发下 SLO 内成功 token/s、延迟分位和资源成本作 Pareto 选择；先与用户明确权重，避免杜撰单一“最高”指标。
- **阻塞/授权**：本机 GPU 虽快照空闲，但按共享资源偏好需先协调；本 Task 不自行下载数十 GB 权重、不启动模型服务或性能负载。

## Remaining
建 T002：拿到共享 RTX 3090 的明确协调窗口后，固定环境与模型 revision，完成 SGLang 加载/正确性 smoke test、隔离 L3 文件目录及三组基线实测。若 7B BF16 权重/运行容量不适配 24GB，依据官方许可确认量化候选并另立清晰对照，不悄然换模型。
