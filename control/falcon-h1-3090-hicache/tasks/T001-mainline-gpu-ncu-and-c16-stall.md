# T001 — 当前主线 GPU/NCU 计量与 c16 stall 收敛

Status: ACTIVE — hardware matrix acquired; report/regression/allowlisted commit and push remain.
Work area: experiments.
Objective: 在当前dirty主线上完成c16独立clean repeat与c8/c16 Prefill/Decode真实Falcon scheduler NCU counters；不以工具失败代替指标交付。

## Completed

- 当前 authorized target `/home/ubuntu/workspaces/3rdparty/sglang-hicache`，branch `3090-24g-hicache`，HEAD `6f612b0301416157e48fc5e40ac01680bc212b3c`；dirty product tree未重置/覆盖。Scheduler SHA `a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc`。
- c8 t2/t3/t4 clean 40×128 trials：311.4992/312.1240/310.9236 output tok/s，mean311.5156，sample SD0.6004；c16 t1/t3/t6：397.5463/393.9869/395.5923，mean395.7085，SD1.7826。NCU capture与clean throughput分开。
- NCU 2025.2.1用经过验证的ubuntu UID+capability launch path。真实Falcon scheduler worker在warmup后通过CUDA Profiler API marker启停，NCU设置`--profile-from-start off --graph-profiling node`、kernel filters与bounded launches，无全服务kernel replay。
- Prefill c8/c16分别capture Marlin+BF16 CUTLASS，各8 launches；Decode c8/c16分别capture Marlin+BF16 GEMM，其中c8 Marlin8+BF16 4、c16主矩阵8；Mamba Conv/Selective Scan与FlashInfer paged attention在两个并发度分别独立bounded补采。交付10份所选有效reports/53 launch rows（另保留c8 Decode早期1-row诊断报告）；normalized证据`control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/ncu-matrix-normalized.json`。
- 代表kernel table、GA102 metric units/definitions、单kernel瓶颈判读、采样duration、clean TPS、旧timeline映射及限制在`.../R17-NCU-HARDWARE-MATRIX.md`；操作和身份记录在`.../R17-NCU-CONTINUE-PROGRESS.md`。失败的导入/显存/OOM/driver attempts均留在独立目录，不算有效sample。
- c8 Decode首行旧样本198.88µs和其不足counter保留，不与新8-launch Marlin replay平均混淆。Attention和c8 Decode BF16已有补采。Prefill Attention没有定点capture，标UNKNOWN。
- 测试中过往有量纲异常stall ratios已换成GA102支持的`.pct` per-warp-active stall指标；报告注明它们不是kernel wall-time百分比。NCU CSV包括units、grid/block、context/stream、duration；独立profile windows另存完整~1Hz NVML。NCU graph profiling没有给出具体graph node ID，因此node identity仍UNKNOWN；无current-mainline request-ID-joined full scheduler/GPU timeline，不能给整阶段kernel-family wall time分数。
- CPU checks：capture shell `bash -n`、driver `py_compile`及normalized JSON/report row counts通过。`git diff --cached --check`对原始NVML CSV/profile stdout捕获日志的尾随空白报错；任务、报告、脚本本身没有此类问题。无本任务NCU/SGLang compute pid，GPU 4MiB/0%；protected ports 30000/30107未碰。

## Remaining / closeout

- 当前主线仍有R16C/R7等大量dirty/untracked资产，均未stage。本次已按逐文件allowlist暂存R17报告、capture scripts、10份成功矩阵/补充capture及其raw CSV/NVML/identity/log、normalized JSON与本Task；R16/R7/dirty产品均明确排除。
- commit/push前还需最终核实stage diff及remote ref；当前含10个原始`.ncu-rep`文件，总计约93.7MiB。
- Prefill Attention counters、具体CUDA graph node ID、current-head scheduler timeline与阶段kernel-family wall-time贡献目前不存在；报告保留UNKNOWN与原因，不用旧isolated timeline、per-kernel replay duration或whole-service utilization替代。
- c16 clean trial只确认新独立成功run；不推断此前c16 stall原因已诊断/修复。
