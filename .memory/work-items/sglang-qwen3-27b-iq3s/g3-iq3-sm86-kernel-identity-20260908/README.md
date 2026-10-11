# G3-IQ3-SM86-KERNEL-IDENTITY-20260908

- **工作标题：** G3-IQ3-SM86-KERNEL-IDENTITY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读确认实验机 RTX 3090 的 compute capability 与 v1 服务实际加载的 `common_ops.abi3.so` 是否含 native SM86 cubin，以判断是否存在 SM86 构建缺口。

## 实际改了什么
只读远端检查；未改远端文件，也未停止、重启、重配或 benchmark 冻结 v1 服务。无产品文件改动。

## 生成结果与验收
GPU capability 为 `(8,6)`；从 PID 503601 maps 确认加载扩展并核验 SHA-256，cuobjdump 显示 native cubin 有 `sm_80/sm_89/sm_90/sm_100/sm_120`，没有 `sm_86`。报告未推断驱动具体选择 sm_80 compatibility 或 PTX JIT 路径。缺口核验完成，但 build/dispatch correction 与 runtime 验证不在本只读任务范围，需新 Task ID。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-KERNEL-IDENTITY-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-KERNEL-IDENTITY-20260908.md`; SHA256 `b1f946136ffd97652c1d4fe64df86810bde45c859c5216c996741644f11b7920`; source state `local-only`
