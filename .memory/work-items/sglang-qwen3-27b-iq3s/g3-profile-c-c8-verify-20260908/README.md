# G3-PROFILE-C-C8-VERIFY-20260908

- **工作标题：** G3-PROFILE-C-C8-VERIFY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
对已完成的 Profile C8 原始 artifacts 做只读独立核验，复核服务/runner 身份、三次结果、GPU telemetry 与 C1/C6 比较，并列明证据限制。

## 实际改了什么
只读 tester 核验；未运行 workload、未改产品文件、未增加 audit/tracing hook，也未下载或访问 dataset。交付核验报告与本地保存的 raw copy/hash 清单。

## 生成结果与验收
Verdict **PASS_WITH_EVIDENCE_LIMITATION**。27 个 measured files 的本地副本逐项 hash 与远端一致；三次 C8 均 64/64 请求完成、长度固定、无错误，median aggregate output throughput 36.5579 tok/s、total 182.7896 tok/s。C8 相比 C6 output throughput 约 +4.6%，但 TTFT 约 +46.5%、TPOT +15.6%，支持该 workload 下吞吐趋于平台而 latency 增大的观察，不支持强 batch scaling 主张。

限制：未独立保存 C8 model SHA256；flush HTTP response 未单独捕获；warmup_requests=0，不满足三次显式 warmup 证据；runner peak concurrency=16 与 server cap=8 不符，未当作实际并发；有非致命 resource_tracker traceback。故仅按证据边界接受，不扩展为更强门槛通过。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-VERIFY-20260908.md`：1. The C8 raw tree has no separate model-sha256 artifact. The server model
   path and GGUF load identity are captured, but this verification does not
   independently claim a C8-specific model digest.
2. Flush endpoint response bodies/statuses are not separately captured;
   `--flush-cache` is present on all three commands and before snapshots are
   idle/empty.
3. C8 used `warmup_requests=0`; launch graph/kernel warmup is evidenced, but
   the stronger three-explicit-request warmup contract is not evidenced.
4. Runner peak concurrency 16 is inconsistent with the server cap 8 and is
   not treated as actual service concurrency.
5. The runner emitted a non-fatal post-success…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-VERIFY-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C8-VERIFY-20260908.md`; SHA256 `14a125cd04e3dc8e9273613dc2b9f7841aa084ff0ef088b579951e1a052fe505`; source state `local-only`
