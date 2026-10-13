# T002 — 3090 Falcon Forward CUPTI 实测（收敛）

## Goal
在唯一主线 `3090-24g-hicache` 上，使用冻结 Falcon-H1-7B-Instruct-GPTQ-Int4 和独立真实 Forward Harness，交付 RTX3090 Prefill EXTEND 1K/4K、Decode CUDA Graph b1/b2/b4/b8/b16七行矩阵，每形状至少三个独立有效样本、可复算原始计数及报告。

## Authority and constraints
- 唯一工作树 `/home/ubuntu/workspaces/3rdparty/sglang-hicache`，不建分支/worktree，不改 sibling opt。保留全部既有 dirty/untracked Cache/Runtime/实验资产。
- Model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`。RTX3090独占，sudo授权。
- 重用本地 Offline Harness/CUPTI Helper；不改生产 Forward/cache语义，不在在线请求路径加入同步。核心metrics单pass，不以multi-pass Application Replay或NCU Kernel Replay替代。
- DRAM GB/s必须用同一测量Forward CUPTI bytes及对应CUDA Event计算；CUPTI GPU time独立列示。离线 b8/b16不得被表述为在线并发/TPS。
- 仅提交本目标精确allowlist，保护其他工作区修改；提交推送至当前主线。

## Completion
- 七种形状各至少三次独立有效真实 Falcon Forward，验证实际 batch/Graph、KV/Mamba状态、fixture/output、pass/drop完整性；ON/OFF输出核验。
- 报告每行 Event与CUPTI GPU Duration、SM/Tensor/DRAM计数、read/write bytes、n/P50/P95/CV、Graph identity和raw evidence。
- 对测量边界、输出差异、扰动和瓶颈不确定性如实说明。必要回归通过，GPU资源释放。精确allowlist commit/push完成。

## Current result
七形状硬件矩阵与主要raw evidence完成；见 `report.md`。遗留：完整最终检查、提交推送。本goal不得在这两项前标记完成。