# T004 — 基准、SWE 与生产验收

Status: DONE
Work area: experiments
Objective: 完成 ABCD benchmark、真实 coding workload、SWE-bench 及生产 acceptance gate，并给出边界准确的结论。
Inputs: benchmark 表、decode/MTP/TTFT/cache 门禁、并发/soak 记录、SWE 生成与评分记录。
Completion: 报告通过项、失败项、阻断项与排除项；不把中间轮询或评分进度当最终结论。
Result: DONE（结论性汇总）。SWE resolved=21/24=87.5%；decode/C2 等部分通过，但 MTP、128K cold TTFT、prefix reuse ratio、device-hit TTFT 未达门槛，C4 无实际价值。
Remaining: 若需确认 soak 的最后终态或修复门禁，另建新 Goal。
