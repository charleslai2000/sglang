# G3-E3-SMOKE-VERIFY-20260907

- **工作标题：** G3-E3-SMOKE-VERIFY-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
独立只读复核 native one-request E3 smoke 的五项 gate：客户端不解析 GGUF、RSS 稳定、无外网/数据集下载、请求长度精确、单请求成功且冻结服务身份不变；同时检查 raw evidence 完整性。

## 实际改了什么
只读取并独立解析 native smoke report、raw subtree、source audit 和 runbook；未发 benchmark、改远端状态/产品、加入 audit/tracing 或额外 workload。无文件改动。

## 生成结果与验收
五项 runtime smoke gate 均 PASS（部分为 observational PASS）：JSONL 单请求 2048/512，服务日志精确记录 flush、generate 200 和 `#new-token: 2048`；RSS 峰值低于 4 GiB 且稳定，pre/post service PID/命令/health/idle loads 一致。正式 Production A 获得 smoke gate GO。限制：raw subtree 缺少 SHA256SUMS，冗余 source hash 指向错误路径；共享 server-log tails 仅时间区间观察而非 byte-range delta，故 integrity 为 PARTIAL/INCOMPLETE，不得宣称 checksum 全量通过。
### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-E3-SMOKE-VERIFY-20260907.md`：- Command/result: `.../raw/g3-e3-smoke-native-20260907T143437Z/command.txt`,
  `result.jsonl`, `client.exit`, `client.stdout`, `client.stderr`
- RSS/process: `client_status_samples.txt`, `client_ps_samples.txt`,
  `client_observed_times.txt`, `client_ps_initial.txt`
- Offline/connections: `environment.txt`, `preflight_connections.txt`,
  `postflight_connections.txt`, `preflight_listener.txt`,
  `postflight_listener.txt`
- Server correlation: `server_log_post_tail.txt` (lines 280–282 for flush,
  generate, exact prefill), `server_log_pre_tail.txt`
- Service invariant: `preflight_service_ps.txt`, `postflight_service_ps.txt`,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-SMOKE-VERIFY-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-E3-SMOKE-VERIFY-20260907.md`; SHA256 `94584ca67bd618c12cd7835abace94375734c4dac6239dc8fe8c082365e7f0b2`; source state `local-only`
