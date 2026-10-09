# G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908

- **工作标题：** G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
以只读检查诊断 Profile B 转换前 `nvidia-smi` 中 PID 315744 `[Not Found]`、占用 22888 MiB 的 compute entry，判断是否存在可归属的额外 GPU owner，避免在未清理的 admission gate 下启动 B。

## 实际改了什么
仅对授权远端执行只读诊断；没有 signal/kill/reset/restart、benchmark、download、instrumentation、source/model change 或 remote write。

## 生成结果与验收
诊断未发现可观察的第二进程或 PID namespace mismatch；该项更符合 stale/unattributable driver accounting，但报告不把假设升级为已确定原因。v1 PID 298123/8035 当时健康、idle、未触碰。Profile B transition 仍 blocked，须外部解决该记录，并由新 admission task 重跑全部门槛。raw diagnostic 及既有 pre-transition GPU evidence 路径/hash 见报告；不代表当前主机/GPU 状态。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908.md`：- Exact key command output and hashes:
  [gpu-owner-diagnostic-20260908.txt](./raw/g3-e3-profile-b-20260907T165140Z/gpu-owner-diagnostic-20260908.txt)
  (SHA-256 `5a1eef0c77d105652e2264f473f7b1038334c5decde7fb689d5a9979b1b7b455`).
- Existing pre-transition evidence:
  [gpu-compute.csv](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/gpu-compute.csv),
  [gpu-query.csv](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/gpu-query.csv),
  [nvidia-smi.txt](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/nvidia-smi.txt).
- Existing run decision:
  [G3-E3-PROFILE-B-LAUNCH-20260908.md](./G3-E3-PROFILE-B-LAUNCH-20260908.md).

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908.md` → `.memory/g3-performance-and-serving/work/G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908.md`; SHA256 `46df4638d5d275db771b47decbac1ada2f768536e9c67fbfe09a61b6ab359ba4`; source state `local-only`
