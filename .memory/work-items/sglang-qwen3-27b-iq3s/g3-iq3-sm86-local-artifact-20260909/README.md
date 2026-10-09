# G3-IQ3-SM86-LOCAL-ARTIFACT-20260909

- **工作标题：** G3-IQ3-SM86-LOCAL-ARTIFACT-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读检查本地工作站是否存在 SM86 source correction 对应的已编译 `common_ops` shared object，并确认 GPU 队列/工作负载是否空闲，以避免误将源码提交当成编译产物。

## 实际改了什么
只读本地 `nvidia-smi`、process 和 filesystem 检查；未启动/停止/修改进程、driver、environment 或 product file。

## 生成结果与验收
报告时 RTX 3090 GPU1 空闲（37 MiB/24576 MiB，0%）；worktree commit `5c5f5e3b...` 含 SM86 AOT gencode correction。但 inspected workspace 未找到 `common_ops*.so`、`*.abi3.so` 或相关 build directory，故无法提供 artifact path/hash/ELF 架构，native SM86 不能确认。需另获或构建隔离 `.so` 并执行 `cuobjdump --list-elf`；本地闲置观察为历史时点，不代表现在队列状态。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-LOCAL-ARTIFACT-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-LOCAL-ARTIFACT-20260909.md`; SHA256 `598ef5b5fa0eea9247afc21052096e5e97889df87754deaf461e25be4c11d1c4`; source state `local-only`
