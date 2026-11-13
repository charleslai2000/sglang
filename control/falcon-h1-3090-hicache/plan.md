# R17-MAINLINE 当前计划

## Established
- 唯一主线 `3090-24g-hicache @ 6f612b0301416157e48fc5e40ac01680bc212b3c`；模型 revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`；R17历史 `/tmp/sglang-r17 @20c837f1` 与当前主线结果严格隔离。
- 当前主线GPU-only c8有效t2/t3/t4吞吐311.50/312.12/310.92 tok/s，40/40请求；mean 311.52±0.60 sample SD。c16 t1/t3 397.55/393.99 tok/s，40/40；mean 395.77±2.52 sample SD。所有命中为0，不能证明HiCache收益。
- c16 t2的早期scheduler CPU栈显示 `on_idle -> invariant_checker._check_all_pools -> _check_full_pool`；另一次NCU驻留run `py-spy` 栈转至 `DecodeCudaGraphRunner.execute -> replay`，NCU下decode graph capture耗时237.59s。后续c16 t3成功干净完成；具体 t2 停顿点不能仅凭这两个栈认定单一根因，需对原trial PID/SHM/锁持有者证据补强。
- NCU真实launch链试过 root launch 与 ubuntu runner嵌套。失败事实：root无法访问ubuntu lock；root Git安全目录限制；修补identity后root PyTorch CUDA service在 `cudaSetDevice/cuDevicePrimaryCtxRetain` startup segfault；NCU全指标集使Decode graph capture耗时237.59s。没有当前主线有效NCU counters。历史R17 NCU不可替代。
- T001/T002相关历史独立Goal `falcon-h1-3090-r17-metrics`仍ACTIVE；当前Goal对其仅复用已核实结论，不复用其错误worktree授权。R7C L2 driver、R11 durable-write与R17 T38C artifact均保留。
- Runtime dirty资产未提交；此前UnifiedRadix full file 128 failed/1020 passed/1163 skipped，OOM和`cudaHostRegister rc=712`未完整归因；focused 57 pass/1skip/2subtests pass。未声称全回归PASS。

## Active frontier
1. 独立修复/复测 c16 t2 stall根因，并完成一条第三有效clean c16重复（t3已经完成，仍需三次独立统计尚差t2以外额外一条）。
2. 用Ncu preflight/counter-set/source ownership审计，找到当前用户主线能稳定加载的root NCU launch与非root产品服务组合；按phase分别采c8/c16，避免NCU full graph replay拖延，确认计数器和单位。
3. 完成runtime产品code审查及UnifiedRadix host pool生命周期回归。
4. 使用R7C/R11正确性负载重验L1/L2 Host-source H→D并归因真实bytes/time；L3 readback独立继续，未过保持NOT_QUALIFIED。
5. 仅选择性stage/commit/push已审查通过文件及证据；保护全部untracked历史资产。

## Durable records
- GPU raw：`falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/mainline-gpu-only-c{8,16}-t*/`
- 运行状态/限制：同run下`MAINLINE-CONTINUATION-STATUS.md`
- 历史源：同run下`provenance-20c837f1/`；原`/tmp/sglang-r17`不改。
