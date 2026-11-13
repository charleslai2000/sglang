# GPU Per-Step Timeline 当前计划

## Established
- 唯一主线仍为`3090-24g-hicache`，HEAD基线`51caa48cf9ff6c5b525b8b355e276a1572748f61`。已验收NCU和clean TPS不复采；不碰sibling opt，不建worktree。大量现存dirty/untracked cache/runtime资产必须保留。
- 既有R17报告`control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/gpu-per-step/R17-GPU-PER-STEP-TIMELINE.md`只有1kHz整卡GPU Metrics+CUDA timeline/FPM aggregate，无batch join，不能判T002 PASS。
- FPM回归修复：`counter_id`继续由publisher重编号为transport sequence；新增末尾默认的`iteration_id`；缺少`forward_iter`发布`-1`，不改其它发布路径。定向unit+manual ZMQ测试`18 passed`，补上了transport序号覆盖与iteration ID保留断言。
- Scheduler最小NVTX range目前包围`_run_batch_impl`实际forward，range含worker、iter、stage、batch、prefill_tokens、decode_tokens；仅在`SGLANG_T002_NVTX_STEP=1`启用，缺少nvtx依赖时明确失败；没有增加CUDA synchronize。代码和字段修改仍未提交。
- 已安装nvtx于虚拟环境site-packages；root服务必须显式将该目录放入`PYTHONPATH`，仅设置`SGLANG_ENABLE_NVTX_SCHEDULER`不足以让标记生效。

## 2026-10-12 本轮结果与失败证据
- 主线、GPU/端口/服务初查通过。`sglang-swift.service`与`sglang-swift15-iq3s.service`保持disabled/inactive。最终本任务进程已停止、3090 1MiB/0%、无30000/30107/30160 listener。
- 一次手动session c8请求40/40完成、FPM收651条（目录`.../t002-c8-t103/`），但对应Nsys SQLite只有GPU_METRICS(1,060,324 rows)，没有任何NVTX/CUPTI activity表；这是无效capture，绝不用于逐step结论。
- 实际step-trigger初次运行因root子进程NVTX Python module路径缺失而Scheduler显式报错退出，已用错误栈定位且无报告；非捕获证据。
- 第二次将NVTX site-packages放入`PYTHONPATH`后，Scheduler/FPM正常且固定40请求完成，但Nsight的`--nvtx-capture=sglang.step`未触发。直接用`nvtx.annotate("sglang.step;...")`生成range，而Nsight capture range按message精确匹配；即使`@*`，完整长消息也不等于该range名。因此session留在StartRange，未产生Nsight报告；结束session及本任务server后GPU空闲。该问题与NVTX可见性不同，不能再重复相同错误配置。
- 官方Nsight NVTX capture语法用range message匹配；本机最小验证中range=`foo`与`--nvtx-capture=foo@*`可触发并生成nsys-rep，range=`sglang.step;worker=...`与前缀名`sglang.step`不触发。NVTX API没有range name prefix匹配；使用完整动态name作单次capture trigger不可行。
- Nsight手动`start`命令不接受`--trace`/CUDA trace选项；`launch`命令接受trace但不接受GPU metrics选项，所以既有尝试启动的session只有其launch trace配置，后续start仅打开metrics，不足以取得同session数据。该组合目前没有被证明可用。

## Decisive frontier
- 必须改变capture mechanism而不是请求身份/推理语义。最小可靠路径可能是现有run profile启动时`--capture-range=none`完成整生命周期CUDA/NVTX+Metrics采集，或使用以固定范围`foo`开启的独立profiling gate并在稳态外层marker内包裹 workload；但后者须评估NVTX nest/capture semantics，不能把step range嵌套关系当kernel join。先用不占GPU的Nsight help和NVTX机制确认配置，再做有明确停服兜底的短GPU验证。
- 不可通过重命名step range为固定消息来冒充iteration身份；可用外层固定capture range仅控制capture，内层动态`sglang.step;...`范围提供ID。FPM也用同一`iteration_id`字段。启动capture时必须显式包含`nvtx` venv site-packages和`SGLANG_T002_NVTX_STEP=1`。
- 一旦SQLite出现NVTX_EVENTS、CUPTI_RUNTIME/KERNEL/GRAPH及GPU_METRICS，按真实step message与CUDA correlation id对step work做join，核查each active FPM exactly-once及token/request守恒。用CUDA kernel interval union算GPU execution/idle；1ms sample按step时间边界关联，但跨step的样本不分摊；此类sample只报告共同窗口聚合。无法用CUDA API/graph correlation还原的时间标UNKNOWN。不能把FPM GPU计时当作kernel union。
- 当前无合格step capture，不能生成c8/c16逐step、steady utilization、Idle/Busy P50/P95、批处理效率归因或loss ranking；不得声称已满足请求验收。用户要求的收敛仍有效：解决普通工具/环境问题后连续验证，不得用边界报告替代继续工作。
- 后续有合格c8 capture后按相同机制采c16 Prefill/Decode连续稳态Step；已有原始有效旧报告不覆盖、不重复采NCU/TPS。完成脚本、报告和定向回归后才允许精确allowlist提交/push；最终检查GPU为1MiB/0%，两服务持续disabled。
