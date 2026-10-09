# G3-PROFILE-C-C1-RESTORE-20260908

- **工作标题：** G3-PROFILE-C-C1-RESTORE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 C1 decode 前置 guard halt 后，停止精确身份核验的 C1 候选进程并按 frozen v1 命令恢复服务，确保不遗留候选 listener 或 GPU process。

## 实际改了什么
身份核验并停止候选 PID 470950 及其明确子进程；经历一次错误 wrapper 启动和一次 OOM failed v1 restore 后，显式清理已确认失败 worker，最终以冻结 v1 命令启动服务。未改产品/模型，未发 benchmark/dmon/query telemetry。

## 生成结果与验收
最终 restore **done**：v1 health HTTP 200，loads idle，有效 max-running=5/max-total-tokens=132436，8035 由 v1 持有、18035 不存在；模型、server_args、runner 身份记录见报告。Profile C1 decode 未发生，仍 blocked，需要新 Task ID。历史 PID/服务状态不代表当前状态。

## 生成结果与验收
- **原报告状态：** done

**`g3-baseline-20260907/work/G3-PROFILE-C-C1-RESTORE-20260908.md`：**
Restored frozen v1 on the authorized experimental host after the C1 decode
pre-run guard halted. No benchmark traffic, dmon, client, or query telemetry
was sent.

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-RESTORE-20260908.md`：- Candidate PID 470950 was identity-checked against the captured Python SGLang
  argv (`sglang serve`, `--port 18035`) and stopped; explicit descendants were
  captured. Port 18035 is absent.
- Remote artifacts: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-20260907T182700Z/c1/restore/`.
- Final v1 launch PID wrapper: 473868; health HTTP 200 on 127.0.0.1:8035.
- `/v1/loads?include=all`: idle, `max_running_requests=5`,
  `max_total_num_tokens=121394`, one RTX 3090.
- Final GPU evidence: one attributable SGLang worker (`494253`, driver name
  `[Not Found]`, 22294 MiB); no benchmark/dmon/18035 processes.
- Frozen command is preserved in `restore/v1.command`, including required PATH,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-RESTORE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-RESTORE-20260908.md`; SHA256 `10c4790bf8ec8d4f574c68a6c4afebfc8bd1481aee788b7dc2d15a0238bfb9f6`; source state `local-only`
