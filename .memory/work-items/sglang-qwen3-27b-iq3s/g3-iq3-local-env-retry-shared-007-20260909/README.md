# G3-IQ3-LOCAL-ENV-RETRY-SHARED-007-20260909

- **工作标题：** G3-IQ3-LOCAL-ENV-RETRY-SHARED-007-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在共享 cache 与授权 PyTorch/NVIDIA index 下，按既定 hash-locked requirements 再尝试一次 wheelhouse download，准备本地 IQ3 venv。

## 实际改了什么
仅经 `sg dev -c` 执行锁定依赖下载；未绕过 hash、改用替代 package、安装部分结果或做额外操作。无 GPU/service/benchmark/lock/source 修改。

## 生成结果与验收
下载到 `nvidia-nccl-cu13` 时实际 SHA256 与 requirements 锁定 hash 不符，pip 失败并保持 wheelhouse 0 files，环境仍 blocked。报告未省略失败或继续使用不匹配包；需新授权解决 index/artifact 与 hash 不一致。

### 证据
下载日志为 `raw/g3-iq3-env-retry-shared-007-20260909/env-rebuild-download-007-20260909.log`；工具版本及 venv/cache 状态见原报告。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-007-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-007-20260909.md`; SHA256 `063313d95c62ab3d3c51b8221dc501fd6edcb2599b48ae3756df341f0855c312`; source state `local-only`
