# R17-MAINLINE — Falcon GPU and HiCache acceptance

## Goal
在唯一授权的 `3090-24g-hicache` 工作树，以真实 Falcon-H1-7B GPTQ-Int4 / RTX 3090 运行，交付可复算的 GPU Prefill/Decode 计量、L1/L2/L3 有效恢复与分层耗时、高并发吞吐及调度指标；完成 dirty Runtime 审查与必要回归，选择性 commit/push 有资格成果。

## Authority and constraints
- 工作树 `/home/ubuntu/workspaces/3rdparty/sglang-hicache`，分支 `3090-24g-hicache`；固定 HEAD `6f612b0301416157e48fc5e40ac01680bc212b3c`，不创建分支/worktree、不碰 sibling `opt`。
- 保护全部现有 dirty/untracked 资产；不以旧历史身份冒充当前主线，不覆盖或丢弃任何既有工作。
- 模型 `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4` revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`；真实 RTX 3090；执行每次 GPU 作业前复核进程、端口、锁与设备，执行后清理本任务服务。
- 复用主线 runner、已存 NCU工具与 CUDA profiler、R7C/R11 正确性/持久化资产；不得新建通用测量框架。Clean throughput 与 profiling分开。
- 不得以 backup、Device hit、零命中负载或 D→H bytes 冒充 Host/Disk有效命中及 H→D恢复。未通过层保持 `NOT_QUALIFIED`，不得阻断独立 NCU/GPU 与 L2推进。
- 不跳过或放宽 correctness assertions；失败完整记录，不能宣称 PASS。阶段交付必须注明 CUDA forward、GPU union、CPU scheduler、请求服务时间边界及异步 overlap。
- GPU sudo与独占已获授权；不因一般命令/脚本工程问题提前停止，重复失败时先用源码、日志、栈、进程映射实证诊断。

## Scope
1. 诊断 c16 停顿：保存 c16 t2 NCU外 clean runtime 日志与活动重放；定位 scheduler CPU/锁/共享内存实际owner，核实 call chain并作窄修复，c16再完成独立重复。不得以graph capture在NCU期间超时替代 clean run证据。
2. 对 c8/c16 Prefill/Decode 采集真实scheduler NCU hardware counters，包含 SM、Tensor、DRAM读写/峰值、L2、occupancy/warp stall、duration、kernel与batch/graph身份，窗口NVML clock/power/temp。保持 NCU replay不计入吞吐；逐kernel与整窗利用率分列。
3. 补齐真实 Prefill tokens/forward GPU time/TPS，Decode batch/step/active TPS、Queue wait/scheduler gap、GPU admission至first token ready、服务级 TTFT/TPOT/ITL。无可信 seam的指标明确缺失，不推算。
4. 用 R7C/R11已有正确性/持久化负载，在当前产品 runtime 上验证 L1有效复用、FULL+MAMBA L2 D→H→D Host source、correctness与DMA completion/bytes/time/ready latency；再独立证明L3 storage read-back/restore和分层耗时。保留25.82GB旧 D→H账本为其来源运行结果，仅可通过实际operation ID/ACK归因复核。
5. 独立查明 UnifiedRadix OOM/cudaHostRegister lifecycle；全面审阅 Runtime identity/ACK、host ownership/eviction与buffer-mode返回契约，跑必要回归，不将全文件失败误报PASS。
6. 有效修复、measurement工具及结果经审查后选择性commit/push；原始证据和既有资产保留。

## Completion
- 两并发GPU throughput有三次独立有效 clean repeats与原始manifest/request/NVML/FPM；NCU c8/c16两phase真实kernel报告及stage映射、单位和硬件窗证据。
- Queue/forward/phase/window/service延迟分别按真实采样口径可复算。
- L1/L2/L3 hit tokens、hit rate、迁移bytes/time/bandwidth、source、DMA/GPU ready、saved prefill tokens与输出正确性通过证据闭合；未通过tier如实保持NOT_QUALIFIED。
- Dirty Runtime和回归审查完成，不弱化断言；全文件未通过项逐项分类。选择性commit/push有精确身份记录；GPU/端口清洁。
