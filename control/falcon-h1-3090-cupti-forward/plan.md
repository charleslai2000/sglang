# T002 当前计划

## Established / result
- 完成七种真实 Falcon-H1 Forward；原始报表、trial JSON/logs、失败诊断保存在本目录，主结果和详细统计见 `report.md`。
- 有效性能集：Prefill EXTEND 1K/4K 和 Decode CUDA Graph b1/b2/b4/b8/b16，各三次独立 fresh process/session。b1直接继承原 r17/r18/r19。每个 session一个单pass window、1个目标UserRange、dropped=0；记录实际batch/Graph、fixture SHA、输出argmax，Decode记录Mamba pool index。独立parity sessions对每形状执行 CUPTI-on vs unprofiled真实Forward；Decode logits bitwise exact，Prefill 1K exact；Prefill 4K final trials 2/3 exact，剩余一个max abs logits diff=0.452953但argmax一致，报告中明确披露。
- 核心样本：Prefill1K使用 `p1-stable-r0..r2.json`。较早 `p1-final-r0..r2` 中有一个370.618 ms/SM Active 69.45%样本；整组三个保留但排除于稳定核心统计。Prefill4K用 `p4-final-r0..r2`；Decode b1继承 `decode-b1-r17..r19`; b2/b4/b8/b16使用 `d{2,4,8,16}-final-r0..r2`。Parity文件单独列在report。
- CUDA Event与CUPTI GPU duration分别报告，Prefill差约0.05–0.16%，Decode约2.75–4.32%。DRAM GB/s逐样本使用同一次Forward的bytes及graph-seam CUDA Event重算；不使用旧 `dram_gbps` JSON字段。
- Counter说明：SM Compute字段固定100%，Prefill SM active高达92–96%，Decode 68–79%；DRAM吞吐占峰约39.8–71.1%。证据不足以归结roofline瓶颈，结论UNKNOWN。b8/b16仅离线batch。
- Harness修正：Profiler window一个trial一个fresh process；精确Graph key才触发range；真实Falcon b16容量配置；fixture词表界限与offline cache诊断接口。没有改变生产Forward/cache语义。离线post-forward CUPTI finalize同步仅限Harness。
- 验证：Python编译与 `git diff --check`通过；Forward metrics单测在显式SM86 overlay/PYTHONPATH下15 passed。默认测试路径未装载主线sg_kernel overlay导致导入失败，使用正确overlay后通过。
- GPU已清理：RTX3090 1 MiB，0%。

## Remaining
1. 检查report所有数字/原始路径/每行n、P50/P95、CV和Pass完整性与被选trial一致；报告保留Prefill 1K离群诊断与Prefill4K单个logit差异。
2. 完成必要回归、源码/差异检查。对共享 dirty graph backend核实本阶段所有权；任何无关改动不得stage。
3. 按精确文件allowlist仅提交实验代码、报告和必要原始证据，以及确认为本任务专属的graph seam改动；检查staged names/diff后commit并push到当前branch。排除 `control/frontier.md`（同含其他目标状态），保护所有其他dirty/untracked资产。
