# G3-IQ3-LOCAL-DEPS-SENTENCEPIECE-20260909

- **工作标题：** G3-IQ3-LOCAL-DEPS-SENTENCEPIECE-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
解决本地隔离 venv 中阻止 SGLang launcher import 的 `sentencepiece` 缺失依赖，并验证包可导入。

## 实际改了什么
仅向 `/mnt/data/qwen3-g3-baseline/venv` 安装 binary wheel `sentencepiece==0.2.2`（`--no-deps`）；wheel SHA256 为报告记录值。未改 GPU、service、driver、CUDA 或 repository。

## 生成结果与验收
安装及 import check 通过，`sentencepiece.__version__` 为 0.2.2；解决了原 preflight 对该依赖的缺失报错。但本 invocation 未启动服务或运行 GPU test，后续执行需新 invocation。wheel 与 pip/install/import evidence 及 SHA256SUMS 保存在报告指定 raw 目录。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-DEPS-SENTENCEPIECE-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-DEPS-SENTENCEPIECE-20260909.md`; SHA256 `95d3ecb8746bf3d5252511832536a4cf1208710b5d2f9348c7d991c3a2b13da7`; source state `local-only`
