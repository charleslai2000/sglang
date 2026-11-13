# T003 — 代表性并发与分层性能对照

Status: READY
Work area: experiments；基于冻结 R17 serving scripts/manifests，在独立 GPU 窗口采集

## Objective
用同一冻结输入与可证明的状态构造，对照 GPU-only、GPU+Host、以及仅在恢复门通过后 GPU+Host+Disk 的 Prefill-heavy、Decode-heavy、真实多轮 cache reuse。提供优先 c8/c16 的 >=3 独立 repeats，复用合格 c20/c24，不重复无命中短随机负载。

## Inputs
- `goal.md`、`plan.md`
- 已验收 R16/R17 c20/c24 measurements 和 R17 实际 scheduler/metrics evidence
- T001 GPU phase/NV counters 与 T002 层级 restore/correctness 的结论；R7C 成功 L2 workload；现有 `benchmark/hicache/bench_multiturn.py`/cache-hit kit
- 冻结 baseline/model/revision 及 `/tmp/sglang-r17` 隔离 worktree

## Completion
- 每工作负载/token manifest 哈希、cache cold/warm precondition、请求顺序、并发和实际 scheduler running/queue 可复现；三种配置完全等价。
- 每关键点至少三次独立运行；报告 prompt/output/有效复用 tokens、每阶段 GPU TPS/time/kernel/window指标、GPU 利用率/clock/power/temp/VRAM、层级命中/恢复 bytes+duration、scheduler wait/queue、request RPS/E2E/TTFT/TPOT/ITL p50/p95/p99、错误率与重复波动。
- 只对 L1/L2/L3 正确性合格的配置比较 cache收益；L3未通过则 `NOT_QUALIFIED`，不阻断 GPU-only/L2 工作。
- 从实测证据区分 compute、memory bandwidth、cache IO、scheduler瓶颈；不以单一 TPS 排名代替延迟与正确性解释。
- 全部原始数据和汇总可重算，更新 task/plan/frontier，提交并 push 已验收范围，保留无关 worktree 更改。

## Result
未开始。此前 R17 唯一输入短 workload Host 命中为零，因此不是 Host收益证据；R16/R17已验收数据将复用。R7C 有独立 L2正确性恢复结果，R11 有持久化写入证据；L3读回/恢复尚未通过。

## Remaining
待 T001/T002 提供可用阶段计量和正确性合格的 cache 结果后执行对照；可并行准备负载复用审计，但不得先行重复无命中实验。