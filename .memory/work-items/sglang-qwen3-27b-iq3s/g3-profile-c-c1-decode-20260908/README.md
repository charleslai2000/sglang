# G3-PROFILE-C-C1-DECODE-20260908

- **工作标题：** G3-PROFILE-C-C1-DECODE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
对已 admission 的 C1 candidate 执行三次 decode benchmark；开始前验证服务进程与 C1 admission 身份，严格按失败即停规则控制 traffic。

## 实际改了什么
只创建 C1 measure 子目录并执行 pre-run guard；没有发 warmup/flush/generate、没有启动 dmon/query telemetry、没有产品或模型文件改动。候选服务 PID 470950 被保留给单独 restore task。

## 生成结果与验收
测量在任何 benchmark traffic 前 fail-closed：guard 用 `pgrep -x sglang` 判断，但服务实际进程名是 Python，argv 才含 `sglang serve`，造成错误否决。按任务约定未 retry、未进入 repeat 2/3；无 JSONL 或性能数据。报告末次检查 candidate 仍健康（当时观察值），restore 另派。此为 guard defect，不是服务失败或 C1 性能结果。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-DECODE-20260908.md`：Remote measurement subtree (authorized fresh `measure/` subtree):
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-20260907T182700Z/c1/measure/repeat-1/`
contains `start.utc`, `pre.pid`, and `HALTED.txt`. No JSONL, stdout/stderr,
loads-before/after, dmon, query CSV, or server-log delta exists because the
guard stopped before those steps. A local raw copy is retained at:
`.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-20260908T/measure/`
The final remote check observed PID 470950 alive with RSS 1,605,736 KiB and
`/health` HTTP 200. No product/model files changed. No remote files outside
the authorized C1 `measure/` subtree were written.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-DECODE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-DECODE-20260908.md`; SHA256 `3c39e1b8c98782fa0b6cf55637cd54a4de70343fe7609250f219ddcbe988b098`; source state `local-only`
