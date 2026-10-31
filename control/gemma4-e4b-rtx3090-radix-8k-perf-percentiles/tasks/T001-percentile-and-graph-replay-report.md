Status: DONE
Work area: experiments
Objective: 从既有真实 c16/c24/c32 GPU 运行产物补齐P50/P95指标及Graph实际batch/replay shape边界。
Inputs: 既有运行目录、真实batch独立报告、现有CUDA事件解析器；不可运行新GPU workload。
Completion: 准确计算per-step GPU Decode Forward、request TPOT/TTFT/E2E的测量轮次P50/P95与样本数；解析Scheduler batch/event batch分布，解释配置capture buckets、padding与不能直接观测的replay内部细节；更新独立报告和plan；有针对性验证，限定提交/push并验证远端SHA。G1保持FAILED / NOT ACCEPTED。
Result: 用户要求的指标已从既有归档补齐，无GPU复跑。每并发三轮共有768个Decode CUDA Event；事件无Scheduler step identity，因此不把768个事件冒充per-step latency分布，而报告每轮event聚合时间/256步所得round means的P50/P95，明确n=3。请求级TPOT/TTFT/E2E以48/72/96个测量请求计算P50/P95。Scheduler/Event实际batch为16/24/32且Graph True；源码最小bucket选择对应16/24/32，padding=0。opaque graph handle/shape-key未被日志记录，报告只声明已证实的capture桶和replay batch。池容量、峰值采样显存及500ms采样限制已说明。
Remaining: None. 独立报告与离线分析器完成；最终差分/语法复核、选择性提交/push及远端SHA验证后关闭。G1继续FAILED / NOT ACCEPTED。