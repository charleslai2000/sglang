# G3-PROFILE-C-C1-RESTORE2-20260908

- **工作标题：** G3-PROFILE-C-C1-RESTORE2-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
C1 decode 测量结束后，身份核验并停止唯一候选 PID，恢复 frozen v1 服务并检查 health/load/参数与端口状态。

## 实际改了什么
仅执行远端候选清理与 v1 还原；TERM 停止经完整身份验证的候选 PID 478926，没有针对其他候选或 production PID。随后以既有 frozen 命令/离线环境启动 v1 PID 482817。无产品、模型或 service config 文件变更。

## 生成结果与验收
Restore **done**：v1 health HTTP 200，loads running/waiting 均为 0，max-total-tokens=132436、max-running=5，冻结 parser/tool/KV/Mamba/template flags 存在；8035 恢复、候选 18035 消失。证据保存在对应 run 的 `restore2/`。此为历史还原验证，不代表当前服务状态；进一步 benchmark/process 操作需 fresh Task ID。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-RESTORE2-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-RESTORE2-20260908.md`; SHA256 `bd3a2d16f07a064b904a4054a2a4f8c390eaec688bb282ddd343bb7a9e75c8d8`; source state `local-only`
