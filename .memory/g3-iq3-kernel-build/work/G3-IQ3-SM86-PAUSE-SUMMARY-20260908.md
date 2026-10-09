# G3 IQ3_S / SM86 工作暂停总结

任务：`G3-IQ3-PAUSE-SUMMARY-20260908`  
编排 epoch：`E9`  
角色：`doc-writer`  
状态：**pending（按用户要求暂停）**

## 结论摘要

本轮没有完成 MMQ 实现、SM86 修正版扩展构建或任何性能提升验证。工作在
SM86 隔离构建阶段按用户要求暂停；后续动作只能在新的授权/Task ID 下继续。

已确认的性能口径是：Production A 报告中的约 `169--171 tok/s` 是
`Total token throughput`，不是 output/decode throughput。对应 output TPS 为：

| 点位 | Output TPS | Total TPS |
|---|---:|---:|
| Production A C1 | 24.545720 | 122.728599 |
| Production A C4 | 33.881157 | 169.405783 |
| Production A C5 | 34.186597 | 170.932986 |
| Profile C C1/pool20 | 33.907601 | 169.538004 |
| Profile C C6/pool32 | 34.959714 | 174.798571 |
| Profile C C8/pool40 | 36.557910 | 182.789552 |

因此不能把 `170` 与 `35` 作为同一指标比较。Production A C4→C5 的 output
仅约增加 0.9%；Profile C C1→C8 的 output 增加约 7.8%，但延迟明显增加。
这些数字来自已保存的三次重复原始 JSONL/stdout，不是新测量。

证据：
`G3-PRODUCTION-A-THROUGHPUT-RECON-20260908.md`。

## 已确认事实

### 现场与服务不变

- 唯一使用的实验主机为 `175.155.64.171:22109`。
- RTX 3090 capability 为 `(8, 6)`，驱动 `580.173.02`。
- loopback v1 服务 `127.0.0.1:8035`、PID `503601` 未停止、重启、重配置或替换扩展。
- `/data/sglang-qwen35` 无 Git 元数据；本地 checkout commit 为
  `dac6db1ebabdb80209b757fd063cf53e05c091e7`，工作树有既存未提交修改。
- 已加载扩展路径为
  `/data/sglang-qwen35-env/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so`，
  SHA-256：
  `7107039cd6d78c62cbb96bfa677cfdbbd4ae355c50e1ce9481590e033f61feff`。
- `cuobjdump --list-elf` 显示 native `sm_80/sm_89/sm_90/sm_100/sm_120`，没有
  native `sm_86` cubin；这不是对实际 JIT 选择路径的推断。

证据：`G3-IQ3-SM86-KERNEL-IDENTITY-20260908.md`，以及
`raw/g3-iq3-sm86-kernel-identity-20260908/`。

### 当前 IQ3_S 执行路径事实

部署源与本地对应文件字节一致。IQ3_S 位于 imatrix/MMVQ 集合，不在
`MMQ_QUANT_TYPES`；小 batch decode 进入 `ggml_mul_mat_vec_a8`，较大 prefill
形状进入 `ggml_dequantize` fallback。`GGUFLinearMethod.apply()` 中存在
每个 shard forward 的 `.contiguous()` 调用；wrapper 每次调用都会创建并量化
Q8_1 activation。源代码本身没有证明每次 slice 都实际分配，也没有证明其端到端
瓶颈占比。

证据：`G3-IQ3-LIVE-PATH-CHECK-20260908.md`。

## 阻塞/未完成事项

### SM86 构建修正：源码变更存在，但未被接受

本地 AOT CMake 仅增加了：

```cmake
"-gencode=arch=compute_86,code=sm_86"
```

独立的最小 CUDA 编译与 object `cuobjdump` 检查通过，但完整 AOT 构建/运行时
验证没有完成。评审结论为 `BLOCK`：没有最终 `.so`、ELF 检查、3090 加载/dispatch
证据，因此不能把它当作已完成的 runtime correction，也没有部署到远端。

证据：`G3-IQ3-SM86-BUILD-CORRECTION-20260908.md`、
`review/gates/G3-IQ3-SM86-BUILD-REVIEW-20260908.md`。

### 隔离构建：按暂停要求停止，状态 pending

隔离树位于远端：
`/data/qwen3-g3-baseline/g3-iq3-sm86-isolated-build-20260908/`。

配置成功并确认 CMake 使用 `compute_86,code=sm_86`；随后启动的 Ninja 构建在
用户暂停时被停止。构建 PID 为已核验的隔离树进程 `566317/566318/566319`，
未触碰 PID `503601`。没有最终退出码、`common_ops*.so` 或其 hash；因此
native SM86 仍未确认。缓存、对象和日志保留在远端隔离目录。

本地原始状态证据：
`raw/g3-iq3-sm86-build-accel-20260908/status.txt`。相关报告：
`G3-IQ3-SM86-ISOLATED-BUILD-20260908.md`、
`G3-IQ3-SM86-BUILD-ACCEL-20260908.md`。

### Flat-storage/no-copy 方案：已 BLOCK 并回退

改变 Parameter/state_dict 语义的一维 flat-storage patch 未通过独立评审，原因是
缺少真实 CUDA/runtime 验证、边界语义未证明且收益未证明。该 patch 已回退；新增
测试已删除。当前不应重新部署、扩展或据此做性能结论。

证据：`review/gates/G3-IQ3-NOCOPY-LAYOUT-REVIEW-20260908.md`（如需查阅）和
`G3-IQ3-REVERT-FLAT-LAYOUT-20260908.md`，回退报告记录 `git diff --check=0`。

## 暂停边界与后续（均为 pending）

用户已要求暂停并准备关闭机器。后续可选工作仅保留为 pending，不代表已获执行：

1. 在同一隔离构建缓存上恢复构建，检查最终 `common_ops.abi3.so` 的 hash 与
   `cuobjdump --list-elf`，再做独立 runtime acceptance。
2. 在 SM86 构建事实闭合后，按新 Task ID 设计/移植 IQ3_S MMQ/batched kernel，
   先做真实层形状 microbench 与数值/Graph gate，再做短端到端复测。
3. `.contiguous()` no-copy 与 quant_X reuse 只能作为后续独立、证据驱动的工作；
   不得把未证实的复制量或收益写成事实。

本总结不声称 IQ3_S MMQ 已实现，不声称 prefill dequant fallback 已消失，也不
声称吞吐已提升。

## 原始 artifacts

主要本地证据目录：

- `raw/g3-iq3-live-path-check-20260908/`
- `raw/g3-iq3-sm86-kernel-identity-20260908/`
- `raw/g3-iq3-sm86-build-correction-20260908/`
- `raw/g3-iq3-sm86-isolated-build-20260908/`
- `raw/g3-iq3-sm86-build-accel-20260908/`
- 保存的 Production A/Profile C 原始树及其 `SHA256SUMS`

## Invocation

`invocation_status: pending`  
原因：文档已完成，但用户要求暂停；SM86 隔离构建尚未完成，后续验证需新的
授权/Task ID。额外工作需要 fresh Task ID。
