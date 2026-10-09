# G3-IQ3-SM86-BUILD-CORRECTION-20260908

- **工作标题：** G3-IQ3-SM86-BUILD-CORRECTION-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
修正本地 AOT build architecture list 中缺少 native SM86 target 的配置，供后续隔离构建与运行时验证；不改远端部署或 SGLang dispatch/kernel 行为。

## 实际改了什么
仅改 `python/sglang/kernels/aot/CMakeLists.txt` 的 `ENABLE_BELOW_SM90` architecture flags，添加 `-gencode=arch=compute_86,code=sm_86`。未改远端、服务、模型、Python dispatch、MMQ、量化行为或 runtime flags。

## 生成结果与验收
`git diff --check` 通过；静态检查确认 `sm_80/sm_86/sm_89` 均在 common list；CUDA 12.0 nvcc 编译最小 `sm_86` object 成功，cuobjdump 确认该 object 有 `sm_86` cubin。完整 CMake configure 因本地缺 CMake/torch 未完成；没有构建或安装 AOT wheel，远端扩展未改变。因此是 build-ready 配置修正，不是已部署/已验证 runtime 支持。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-BUILD-CORRECTION-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-BUILD-CORRECTION-20260908.md`; SHA256 `849fcb8edeba66593897312618cbcd304f206314018c739fda1d6d3d400a5e27`; source state `local-only`
