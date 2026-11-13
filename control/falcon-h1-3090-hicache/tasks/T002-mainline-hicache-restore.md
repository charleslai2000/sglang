# T002 — 当前主线 HiCache L1/L2/L3 恢复与分层计量

Status: READY
Work area: experiments
Objective: 复用R7C/R11/T38C已存在负载，当前主线证明L1有效复用、L2 FULL+MAMBA Device→Host→Device与L3 storage read-back；实测source/bytes/time/ready及correctness。
Inputs: `goal.md`/`plan.md`；R7C `l2_driver.py`/`launch_l2.sh`；R11 driver/provenance；当前dirty Runtime telemetry；R17 probe logs及host ACK operation identity。
Completion: 按层有效hit tokens/rate/saved prefill、真实lookup/wait/host与storage source、D→H/H→D/Disk→Host bytes/durations、DMA completion→GPU ready、恢复输出一致性均有本次主线证据。未通过层保持NOT_QUALIFIED，不阻断GPU/NCU。
Result: R7C提供target FULL+MAMBA正确性 workload；R11仅durable write ACK，不证明read-back。主线GPU-only运行HiCache off/0 hits；L1/L2/L3未验收。早先主线dirty runtime尝试有host ACK tracing，但当前是否稳定需审查。
Remaining: 先逐行审核R7C身份过滤/eviction ownership和当前请求hash/tokenizer一致性；核实当前Host capacity/eviction eligibility及MAMBA detach；执行Host-source H→D并校验greedy输出。L3紧接独立复用耐久映射与read-back，不得以Backup/Device Hit冒充。
