# G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909

- **工作标题：** G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在上一轮 NCCL wheel hash 已通过独立校验后，继续使用锁定 requirements 下载完整 Torch wheelhouse，避免 hash 不符包被安装。

## 实际改了什么
将 SHA-256 与锁定 requirement 一致的 NCCL wheel 从共享 cache 复制到 task wheelhouse，并用授权的 PyTorch/NVIDIA index 继续 `--require-hashes` 下载。未安装或重试超时包；无 GPU/service/benchmark/source/lock 修改。

## 生成结果与验收
NCCL wheel hash 验证符合锁定值；随后下载 exact Torch wheel 在 198.2/526.5 MB 因 HTTPS read timeout 失败。wheelhouse 仅留下已校验 NCCL wheel，venv 未填充，整体仍 blocked。需要新 dispatch 在网络/下载可用时继续。
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-008
epoch: E30

## 实际改了什么
报告记录将 SHA-256 符合锁定 requirement 的 NCCL wheel 从共享 cache 复制到 task wheelhouse，并用授权 PyTorch/NVIDIA index 继续 `--require-hashes` 下载。未安装 wheel、未重试超时下载，也未动 GPU/service/benchmark/source/lock。

## 生成结果与验收
NCCL wheel hash 符合锁定值；exact Torch wheel 下载到 198.2/526.5 MB 时 HTTPS read timeout。wheelhouse 仅有已验证 NCCL wheel，venv 未安装，整体 blocked；需新 dispatch 在下载可行时续做。

**`g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909.md`：**
Copied the exact cached NCCL body into the task wheelhouse; SHA256 matched the
locked requirement. Hash-locked download with the authorized PyTorch and NVIDIA
indexes then reached the exact Torch wheel but failed on HTTPS read timeout at
198.2/526.5 MB. No install or retry was performed.

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909.md`：Raw log: [download log](raw/g3-iq3-env-retry-shared-008-20260909/env-rebuild-download-008-20260909.log).
NCCL wheel hash verified as `edd81538446786ec3b73972543e53bb43bcaf0bfc8ef76cb679fcc390ffe136d`.
Wheelhouse contains only that 205,976,000-byte wheel (197M total); venv 16M;
shared cache 7.8G. No source, service, benchmark, GPU, or lock changes.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909.md`; SHA256 `b5e71c62539148b028dad6e6f8b69e2dc43823016c63bf1dd0bfe6c344807c9c`; source state `local-only`
