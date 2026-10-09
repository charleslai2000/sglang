# G3-E3-V1-RESTORE-20260908

- **工作标题：** G3-E3-V1-RESTORE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
Profile B 转换任务失败后，在授权 host 上恢复冻结 v1 并独立确认服务身份、health、idle loads、端口与模型/启动参数未变。

## 实际改了什么
按 runbook 原样启动冻结 v1，仅补充已授权 PATH prefix 以满足 nvcc 环境；未启动 B、发请求、benchmark/dmon、改源码/模型或重置 GPU。保存 recovery launch、日志与 pre/post snapshots。

## 生成结果与验收
还原通过：v1 health HTTP 200，loads idle，effective `max_running_requests=5`、`max_total_num_tokens=132436`；仅 8035 监听、8036 无 listener；冻结 parser/tool/KV/Mamba/template 参数、模型 MD5 与 source/runner 哈希核对见报告。此为历史恢复验收，不代表当前服务状态或 Profile B 成功。

## 生成结果与验收
- **原报告状态：** done

**`g3-baseline-20260907/work/G3-E3-V1-RESTORE-20260908.md`：**
Frozen v1 service successfully restored and verified healthy on 8035. Profile B was not retried and no benchmark traffic was sent.
Followups: none.
Open issues: none for this restore invocation.
Final status: **done**

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-E3-V1-RESTORE-20260908.md`：- Remote evidence: `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T170803Z/restore-recovery/`
- Launch PID: `462700`; listener PID: `462700`; GPU worker PID: `483639`.
- Exact command: `restore-recovery/v1-restore.command`
- Logs: `restore-recovery/v1-restore.log`, `restore-recovery/prior-failed-restore-v1.log`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-V1-RESTORE-20260908.md` → `.memory/g3-serving-and-runtime-operations/work/G3-E3-V1-RESTORE-20260908.md`; SHA256 `ad864fb4a35b1b720e2b932bd1dfde98728259573023f460ebd030c9faf5b7d2`; source state `local-only`
