# R17-METRICS 当前计划

## 基线与已成立事实
- 上游隔离 worktree `/tmp/sglang-r17`，分支 `r17-falcon-hicache`，HEAD `20c837f1a3daaec47508feaecf5514dd586c636c`；R17 原始证据、状态报告、脚本均在该提交中。主工作树另有未提交修改，不得借本 Goal 操作或清理。
- 权威既有状态：`/tmp/sglang-r17/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/R17-METRICS-STATUS.md`。R17-METRICS 未完成/未接受。
- 复用既有 R16C scheduler 内 PyTorch timeline 与 R17 V2 profile；R17起始提交没有 Falcon scheduler NCU counters。本轮在 sudo launch-and-attach 下新增首个真实 c8 Decode NCU profile，raw report与metrics已验证可解码，详见本Goal `R17-20261012T0100Z/ncu-c8-decode-t4/SUMMARY.md`。NCU synthetic GEMM只说明安装/权限通路可用，不作为Falcon性能证据。
- 固定短输入 R17 c1–c24 sweep 覆盖有限；Host c8 t5 120/120 完成但 L1/L2/L3 有效 hit=0，45,863 prompt tokens 全部新 prefill。聚合 D→H backup 25.82 GB（44,070 KV + 171 Mamba tokens）不是恢复证据；H→D load-back 无有效样本。L3 `NOT_QUALIFIED`。
- GPU 计算阶段时间/服务延迟不是同一指标；已新增可审计的 scheduler DeviceTimer event seam clean c8/c16 重复样本，但该 seam 不等同完整GPU union/kernel边界。详见隔离 R17 run 下 `MEASUREMENTS-SUMMARY.md`。不可把逻辑 input TPS、客户端 TPOT 或 profiler 时间当 GPU compute TPS。
- 用户明确授权 sudo 与独占 3090；执行前对独立 R17 worktree、具体 scheduler PID、锁/GPU/服务和目标配置重新核实，禁止碰 sibling opt。

## 独立推进的工作流
1. Scheduler NCU c8/c16 Prefill/Decode：复核历史 NCU attach 失败日志、现有 scheduler profile trace、进程树与 launch/graph seam；用管理员 NCU 对真实 scheduler worker 做有限代表性采样。采样前后采集 PID/argv、GPU/clock/power/temp、stage markers、profile 时间窗；与 timeline kernel 名/阶段/图回放交叉校验。先 c8 验证，再扩 c16；禁止以 smoke 替代。
2. Prefill/Decode 计算计量：直接复用已有调度器 timeline / instrumentation，在已有确定性负载下匹配真实 GPU start/end、async kernel 与 overlap，分别算计算 tokens/time/TPS；关联 scheduler batch、queue、ready wait、first token ready 和服务级 TTFT/TPOT。普通 benchmark 不开 profiler。
3. L2 正确性与时延：从 R7C 已通过链路/请求轨迹/目标 token workload 与当前隔离 R17 源码作差异审计，确认可直接复用的恢复驱动，不发明新 cache semantics。先重放成功 Host restore并确认 FULL+MAMBA 输出一致、实际 H→D bytes 与 DMA event completion；记录 lookup 到 scheduler ready 的边界。
4. L3：继承 R11 durable-write 证据；查当前源码及历史失败路径，直接定位 target read-back/restore 阻断点。仅补 read/restore，不重做已通过写入。与 NCU/L2 并行。若恢复没有成功，维持 NOT_QUALIFIED，不进入 L3 性能对照。
5. 25.82GB D→H 账本：从 R17 原始 metric 定义、操作/ACK 事件与 FULL/MAMBA component 代码核对字节口径、重复备份、异步时间；只在有 operation identity 的证据上量化真实 transfer/overhead。分别报告 GPU、PCIe、Host 带宽影响，不以总 backup byte 推测。
6. 只有完成确定性 L1/L2 hit 验收后，使用冻结 token-ID workload做三配置对照。复用已有合格 c20/c24；短 prompt 唯一请求 workload不再重复。预先检查各负载确实会达到 intended cache state，跑前验证数据和冷/暖状态。

## 已推进的 NCU 采集诊断
- 起始 R17 attach 的 `--target-processes` 选项与 NCU attach 模式不兼容；移除后直接 attach仍找不到通过NCU端口注册的worker。
- 普通权限 NCU launch-and-attach能连接真实Falcon服务树，但遇 `ERR_NVGPUCTRPERM`。以sudo运行取得真实scheduler counters；首个c8 Decode attach report为异质 first-48 launches，后按profiler trace 的Marlin/BF16 GEMM kernel regex单独采得 c8/c16 Prefill/Decode四个 filtered reports。NCU仍是diagnostic窗口，不作clean TPS。
- 启动阶段实测模型weight load约194s，随后还需decode CUDA Graph capture；240s health timeout不足。本轮延长到540s后服务完成启动并采集成功。
- NCU metric目录经sudo确认支持 requested GA102 counters；本轮 c8 report 是首48异质CUDA launches，不是代表 kernel矩阵完整覆盖，也没有可关联同次run的NVML整窗统计。
- NCU replay显著污染服务请求性能（固定c8 40个request/5120输出token约202.28s）；所有GPU perf counter/profile数据只用于逐kernel诊断，不报告为 clean TPS。
- 采集后GPU为1 MiB/0%，无 NCUscheduler/service/port残留；R17 worktree新建原始数据尚未提交，隔离worktree现有其他dirty state无。

## 下一决定性动作
- 首要完成GPU Busy Union、Scheduler Wait、首token-ready与TTFT/TPOT/ITL可信计量，定位稳定 instrumentation seam；已提交报告只含阶段 filtered NCU rows、clean event-window rates和NVML request windows，不能合并推算。
- T002 的本轮R17新L2尝试已失败：fresh FULL+MAMBA backup ACK存在，restore实际是 L1（`device=1792,host=0`）；早期 barrier `detach_not_sealed`、本run缺失 target `residency_detach`。其 probe 与 driver event ID run identity 关联需先修复并增加强断言；不得重跑/扩压前验证驱动代码和目标状态。L3保持NOT_QUALIFIED，先定位R17 Host detach/read-back边界。
- 复用既有清洁c8/c16重复，补齐三张验收表、硬件 counter逐kernel表及cache tier有效hit/恢复分解；清洁对照只在对应正确性门通过后执行。
- run artifacts已保留在隔离 R17 worktree；本轮结束3090为1 MiB/0%，无服务/PID/port或共享probe marker残留。提交/push待证据与验收范围确定。
