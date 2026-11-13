# T001 — Falcon Prefill Stock/Unlocked A/B

Status: ACTIVE
Work area: experiments/

## Objective
取得Falcon固定模型的Stock/Unlocked Prefill配对数据；Stock无法由GEMM证实时不生成A/B结论。

## Inputs
- `control/falcon-rtx3090-prefill-ab/goal.md`
- 原始数据：`/data/sglang-hicache/falcon-prefill-ab/runs/`
- 历史口径对照：`control/falcon-rtx3090-prefill-ab/comparability-report.md`

## Completion
相同运行配置下有至少5次有效Stock及Unlocked Prefill重复，Stock状态由短GEMM确认；完整输入/缓存、时间和环境证据留档，最终Unlocked可用且服务停止、GPU锁释放。

## Result
本次Unlocked独立runner有效数据：Batch1 1K 205.442ms / 4,984 tok/s，4K 769.820ms / 5,321 tok/s，8K 1,588.132ms / 5,158 tok/s；Batch4 1K 766.714ms / 5,342 aggregate tok/s，每格5次。16K Batch1及较长Batch4因显存余量不足而OOM。真实服务对1K/4K各完成5次零缓存请求；TTFT字段未返回。Profiler无可用trace。

Stock尝试移除cmdline target后GEMM仍为FP16/BF16/TF32 111.433/117.129/62.400 TFLOPS，不是Stock；未运行Stock Prefill。T002历史1K/4K Event/CUPTI值不是Stock样本，与本次runner计时边界亦不同，详情见对照报告。当前GRUB临时条目已移除、默认targets项恢复、Guest重启后GPU CUDA可用但日志为`gpu_unlock: unlock failed (-114)`；因此未声称成功恢复解锁事务。服务已停、端口清空、GPU空闲、锁释放。

## Remaining
不再重启或修改GRUB。Stock/Unlocked Prefill A/B及加速比未完成；历史T002与本次结果仅按`comparability-report.md`作口径和配置对照，不拼接、不作因果归因。
