# G3-BASELINE-C1-20260907

- **工作标题：** G3-BASELINE-C1-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 frozen v1 baseline 服务/API 上执行一次最小 C1 chat-completion probe，确认服务可响应且不将单请求冒充正式并发矩阵。

## 实际改了什么
执行一条实际 API 请求并保存命令参数、preflight、stdout/stderr、退出码及 postflight 证据；没有改产品文件或服务配置。

## 生成结果与验收
probe 成功：对报告指定的服务 PID 298123/API 8035 发出一次请求，exit status 0、stderr 为空，约 1.4 秒返回 `pong`。服务/API 身份保持，日志记录恰好一条新增 chat-completion 请求。未形成正式矩阵或 JSONL scorecard；后续 C1/C4/C8/C16 需独立授权运行。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-BASELINE-C1-20260907.md` → `.memory/g3-baseline-core-unblock/work/G3-BASELINE-C1-20260907.md`; SHA256 `c1e1ffcffea6f3a97b9e2e9b17708f912d0144f5779b7c375ca81dd664fb3407`; source state `local-only`
