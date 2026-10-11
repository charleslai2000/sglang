# G3-IQ3-DRIVER-RESEARCH-20260909

- **工作标题：** G3-IQ3-DRIVER-RESEARCH-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
基于公开资料区分 RTX 3090 CUDA runtime compatibility 与 SGLang AOT 扩展缺少 `sm_86` cubin 两类问题，判断是否有依据因 GPU 型号而升级驱动。

## 实际改了什么
仅完成公开资料研究并撰写报告；没有访问私有 host/IP/path/credential/process/log，也没有更改驱动、源码或构建产物。

## 生成结果与验收
报告结论：未见因“RTX 3090 本身”需升级驱动的公开依据；CUDA 12.x minor compatibility 有最低驱动版本，但仍须以实际加载版本/runtime 核实。驱动升级不改变已有 `.so` 的 cubin 内容；native `sm_86` cubin 属于构建目标/产物问题，应优先重新构建并检查，只有低于 runtime 要求或出现明确不兼容证据才考虑驱动变更。本结论是公开资料 research，不是对现场驱动或实际扩展的运行验证。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-DRIVER-RESEARCH-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-DRIVER-RESEARCH-20260909.md`; SHA256 `b4646081fa53a16c41cfd7cff5bdebacec2f6c41c1be164656f4c8de4b305f4c`; source state `local-only`
