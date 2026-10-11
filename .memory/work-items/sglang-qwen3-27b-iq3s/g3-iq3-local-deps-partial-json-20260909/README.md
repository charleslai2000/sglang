# G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909

- **工作标题：** G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
为隔离 IQ3 venv 安装启动链缺失的 `partial_json_parser`，验证固定版本可导入，解除对应一项 Python import 阻塞。

## 实际改了什么
仅向 `/mnt/data/qwen3-g3-baseline/venv` 以 pinned requirement 和 `--no-index --require-hashes` 安装 `partial_json_parser==0.2.1.1.post7`；无 GPU/service/driver/CUDA/repository 修改。

## 生成结果与验收
import 验证通过，包路径位于目标 venv，wheel SHA256 与报告记录值一致。pip 仍报告其他既存 SGLang 依赖缺失/不兼容，本项未处理；启动或 GPU smoke 需 fresh invocation。
Installed only the missing `partial_json_parser` dependency into
`/mnt/data/qwen3-g3-baseline/venv`. No GPU, service, driver, CUDA, or repository
changes were made.


### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909.md`：Raw command logs, pinned requirement, wheel hash, and pip metadata are under:
`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-deps-partial-json-20260909/`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909.md`; SHA256 `9688ae6e0be485632920cca826731d2d92c6c330f10dab7e69d2243f61a7832f`; source state `local-only`
