# T001 — Scheduler NCU 与 Prefill/Decode GPU 计算计量

Status: ACTIVE
Work area: experiments；在隔离 worktree `/tmp/sglang-r17` 使用现有 Falcon serving/profile 负载与工具

## Objective
取得真实 Falcon `sglang::scheduler` CUDA 子进程的 c8/c16 Prefill/Decode NCU 硬件计数器，并用可信 GPU timeline 确认 kernel、阶段、CUDA Graph、异步重叠与采样窗口；同时给出 Prefill/Decode GPU compute tokens、时间、TPS、batch/chunk、调度等待以及单独服务级延迟。

## Inputs
- `control/falcon-h1-3090-r17-metrics/goal.md` 与 `plan.md`
- 首个有效运行 `runs/R17-20261012T0100Z/ncu-c8-decode-t4/SUMMARY.md` 与关联 `.ncu-rep`/decoded details
- 基线 commit `20c837f1a3daaec47508feaecf5514dd586c636c`；隔离 worktree `/tmp/sglang-r17`
- R17 状态 `runs/R17-20261012T0100Z/R17-METRICS-STATUS.md`、`ncu-attach-*`、`ncu-c8-decode-t1/`、profile traces、`profile_capture.py` 与 workload manifest
- 合格 R16C scheduler PyTorch profiles；已安装 NCU 2025.2.1
- 用户明确授权 sudo、GPU 独占；冻结 RTX 3090 与 model revision

## Completion
1. 以服务真实 scheduler PID/argv/CUDA context 为目标，不是 smoke；原始 NCU report 能解码并有 Falcon kernels。
2. c8、c16 各有 Prefill 和 Decode 阶段代表性窗口；提供 kernel 与 scheduler trace 的时间/名称映射、CUDA graph/launch 证据及窗口旁证。每 kernel 指标与整 GPU 窗口指标分开。
3. 逐 kernel 尽可能覆盖 SM Active、SM Compute Throughput、Tensor Pipeline、DRAM/L2 带宽与命中、occupancy、warp issue/stall、duration；缺失指标需记录实际 metric 查询/硬件支持失败证据，不得臆造。配套 GPU clock/power/temp/throttle 采样。
4. 在 unprofiled 普通 workload 中，以现有或最小改动 instrumentation 可靠区分 GPU Prefill/Decode kernel execution tokens/time/TPS、batch/chunk、GPU gaps、scheduler queue/ready wait、GPU first-token-ready；E2E TTFT/TPOT/ITL 单列。异步 overlap 的 union wall 不将重叠 kernel 时长简单相加。
5. 原始证据、manifest/命令/commit/hash、可重算脚本与结论提交至 R17 run artifact；profile 与 benchmark 干扰分别说明。无残留服务/GPU进程。

## Result
初次只读核验时 RTX3090 空闲。R17初始 attach 的错误是非法 `--target-processes`；去掉后直 attach因没有 NCU已注册目标而找不到进程。使用 `sudo ncu --target-processes all -- <R17 server runner>` launch-and-attach 后，成功捕获真实 Falcon scheduler PID 259848 的 kernel。普通权限 NCU 曾报 `ERR_NVGPUCTRPERM`，管理员运行路径成功。有效 c8 run位于 `/tmp/sglang-r17/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/ncu-c8-decode-t4/`：NCU原始report 75.6MB，NCU import导出 details可解码；固定负载40请求均生成128 tokens。原始服务在NCU下40请求耗时202.28s，明显被kernel replay扰动，仅计数不算吞吐证据。NCU full set提供逐kernel Duration、SM/DRAM/L2 throughput及hit、tensor pipe、occupancy、issue/warp latency与stall区块；sudo指标目录查询也确认GA102支持 read/write bytes及主要stall项。NVML此轮未按采样窗口归档，状态和整卡时窗需后续补测。与现有 c8 `/start_profile` trace交叉核验，Decode实际 kernel包括 Marlin M=1（约29–52us）、Mamba conv（约3us）、selective scan（约60–62us），使用 full decode graph；NCU报告部分首48 kernel包括初始化/非主要 kernel，不能把不同kernel汇总成一个平均值。全局GPU利用率/时钟/功耗/温度及整窗口数据不得与逐kernel NCU百分比混淆。GPU采集结束后3090回到1MiB/0%，NCU/service PID和30160 listener消失。

## Interim results — 2026-10-11
`/tmp/sglang-r17/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/MEASUREMENTS-SUMMARY.md` 汇总本轮原始 artifacts 与可重算口径。使用现成 `ForwardPassMetrics` + CUDA-event `DeviceTimer`、request JSON、NVML sampler，在未开 profiler 的 Falcon 服务中完成 GPU-only c8/c16 各 3 个有效重复（同 manifest、40/40 每次成功）。请求窗口分别为 c8 mean 16.379s (16.366–16.405)，c16 mean 12.997s (12.786–13.303)；FPM forward-event sum mean 16.213s / 12.834s。FPM phase-bin Prefill event sums c8 5.015–5.066s、c16 4.937–5.407s；Decode c8 11.159–11.178s、c16 7.707–7.721s。定义限于 model_runner.forward/cuda_graph.replay 的 CUDA-event seam，不是全 GPU busy/union、并非完整 kernel execution 边界。请求级 latency、queue time 和 NVML per-run 数据见汇总及 raw dirs。

Host c8/c16 各做一个控制样本，但 40/40 request 的 cached_tokens 均为0，cached_tokens_details 均为空；不能称有效 Host hit。NCU 原始 c8 Decode 仍为异质 first-48 launches；额外 attach runner 因无服务而在启动时退出，未新增 profile。NCU首样本约202.28s replay请求不作 clean TPS。c8 t3/t4 是 FPM subscriber 接线失败试跑，不纳入重复统计；有效 c8 三重复为 t5/t6/t7。

## Interim results — 2026-10-12 filtered NCU + request-window GPU state
在 c8/c16 Prefill、Decode 用 profiler trace 映射 Falcon Marlin 和 BF16 GEMM 名称/geometry，使用 `ncu --kernel-name` regex 过滤真实 scheduler launch-and-attach，取得各阶段一个 c8/c16 报告（目录 `ncu-{prefill|decode}-c{8|16}-t8-*`，每报告 8 个 selected launches；对应40/40或80/80请求成功）。每个report含 `.ncu-rep`、import CSV、request manifest、PID/argv/设备状态。阶段kernel和并发/批次映射见 `Ncu-phase-summary.md`；既有 CUDA trace 仍为 kernel/阶段身份源。NCU replay窗口独立于干净重复，不能报作TPS；filtered requests 和同窗NVML字段不得推成 clean throughput。初始材料以报告中的逐 launch/逐 kernel数据呈现；异质 Marlin/GEMM不平均。NVML request-window脚本重算值：GPU-only c8 t5/t6/t7 utilization 84.65/98.06/97.31%、power 320.05/333.35/332.74 W、SM clock 1845.88/1854.38/1848.75 MHz；c16 t1/t2/t3 util 85.85/92.31/84.54%、power 299.85/320.75/297.65 W、SM clock 1723.85/1838.08/1719.23 MHz；仅含请求 epoch窗采样，不含 model load/120s idle。已保留 clean throughput、FPM event与NVML分表，具体样本数和边界见 `MEASUREMENTS-SUMMARY.md`。GPU Busy Union、Scheduler Wait、真实 TTFT/TPOT 仍缺可信采样 seam，不能从 DeviceTimer/FPM/request E2E 推算。

## Remaining
NCU各阶段过滤报告已采集，但完成全部要求的 counters/采样窗口映射需对照 `Ncu-phase-summary.md` 与原始 CSV逐字段复核；补充可复算 GPU-active/union、first-token-ready、TTFT/TPOT/ITL 证据。当前 DeviceTimer seam不满足完整GPU phase completion。T001仍未验收；D→H/H→D有效HiCache恢复另见T002。