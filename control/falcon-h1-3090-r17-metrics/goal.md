# R17-METRICS — Falcon GPU 与 HiCache 分层性能实测

## Goal
在冻结的 R17 Falcon GPTQ-Int4 / RTX 3090 基线上，补齐并交付真实 scheduler 硬件计数器、GPU Prefill/Decode 计算效率，以及 GPU/Host/Disk 分层命中与恢复耗时；在正确性合格的配置上完成代表性负载对照，并提交可重算原始证据。

## Frozen target and authority
- 基线：`origin/r17-falcon-hicache` 已推送提交 `20c837f1a3daaec47508feaecf5514dd586c636c`；应在隔离 worktree `/tmp/sglang-r17` 上继续，除非先核验远端更新并按提交身份重新基线。
- 模型：`/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`，revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`；单张 RTX 3090。
- 复用通过验收的 R16/R17 数据与现有测量工具；不得把独立 GEMM smoke、零命中负载或新增通用 profiler/benchmark 框架当作 Falcon 性能证据。
- sibling `opt` worktree 只读；隔离并保护原有未提交成果。R16/R17 的已验收测量不重复执行。
- 用户已授权本目标使用 sudo 与独占 GPU；每次实际操作仍须确认当前目标进程、服务、GPU 和锁状态，实验后清理本任务进程。

## Scope
1. 以管理员权限在真实 SGLang scheduler CUDA worker 上采集 NCU；验证 PID/身份、CUDA Graph 及采样窗口，并与既有 scheduler PyTorch timeline 交叉匹配。对 c8/c16 Prefill/Decode 代表 kernel 采集 SM、Tensor、DRAM、L2、occupancy、warp/stall、duration 与 GPU 状态；逐 kernel 与整窗数据严格分开。
2. 在现有 instrumentation 上建立明确 GPU 执行起止边界，分开报告 Prefill compute tokens/time/TPS、batch/chunk、Decode batch/step/TPS、scheduler queue/ready wait/GPU 空档、first-token-ready；服务 TTFT/TPOT/ITL 与计算效率不得混淆，profiling 不得污染干净吞吐基线。
3. 先审查已验收 R7C L2 恢复工作负载/代码和 R11 持久化证据；确定性复用并验证 L1、L2 Host→GPU、L3 Disk→Host→GPU。按层采集 logical hit 与有效复用 token、weighted hit rate、lookup/wait/admission、真实 bytes/duration/bandwidth、恢复完成至 scheduler ready、节省 prefill tokens、KV/MAMBA 正确性。L2 独立报告 DMA CUDA completion；L3 分解 lookup、队列、物理/OS cache IO、Host ready、H2D、GPU ready。未经成功恢复不得认定有效命中或收益；不重复认证已通过的写入。
4. 解析既有 25.82 GB D→H 备份中的 FULL KV、MAMBA、重复备份与异步开销，分析其对 GPU 计算、PCIe 与 Host 带宽的实测影响；不得把 D→H 计数当作 H→D 证据。
5. 使用冻结负载对照 GPU-only、GPU+Host、GPU+Host+Disk 的 Prefill-heavy、Decode-heavy、真实多轮复用；优先 c8/c16，关键点至少 3 次独立重复，复用合格 c20/c24 数据。仅在分层正确性通过的配置上报告性能收益。

## Constraints / exclusions
- 先检索历史实现、验收测试和成熟上游工具；复用已存在路径，避免重复建设。
- GPU 计数器和 profile 采集与 clean throughput 分开运行；所有比例注明采样边界与统计口径。
- L3 生命周期尚未证明成功恢复时，相关性能项目保持 `NOT_QUALIFIED`，但这不阻断 NCU、计算效率和 L2 路径。
- 不改冻结模型/架构，不改变 cache 语义来制造命中；不改 sibling opt；不覆盖或夹带无关 dirty state。

## Completion
- 真实 Falcon scheduler NCU 有原始样本，c8/c16 Prefill/Decode 采样身份、CUDA Graph、窗口及 kernel 与阶段归属均可核验；逐 kernel / GPU 时间窗指标和 GPU 状态分列。
- Prefill/Decode GPU 计算 TPS/执行时间/批次与调度等待有可重算证据，服务 TTFT/TPOT/ITL 独立呈现。
- L1/L2 有效命中、H→D bytes 与 DMA completion 及 KV+MAMBA 正确性通过；L3 若成功恢复则给完整分层时间和正确性，否则明确状态与证据，不宣称收益。
- 对照覆盖要求的工作负载及并发点，结果含吞吐、延迟分位、cache、scheduler、GPU/NVML 和波动；继承合格 c20/c24，不无谓重跑。
- 阶段报告含指标表、时间分解、证据支撑的瓶颈判断、无法取得指标的具体工具/设备证据；代码与原始数据归档，范围受限提交并 push；无本任务 GPU/服务残留。
