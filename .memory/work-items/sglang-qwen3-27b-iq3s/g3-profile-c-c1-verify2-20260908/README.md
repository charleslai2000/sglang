# G3-PROFILE-C-C1-VERIFY2-20260908

- **工作标题：** G3-PROFILE-C-C1-VERIFY2-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
独立只读核验 Profile C1 decode 的三次原始结果、服务/runner 身份、固定长度与 cache flush 证据，重算 scorecard 并核对 telemetry/hash 完整性。

## 实际改了什么
只读 tester 工作：从远端与本地保存副本独立解析 artifacts、校验 manifest/hash；没有运行 workload、修改产品文件、添加 audit/tracing、下载或启动新 telemetry process。

## 生成结果与验收
Verdict **PASS_WITH_EVIDENCE_LIMITATION**。三次均 RC 0、32/32、输入长度 1024、输出 256，native C1 平均并发约 3.99；中位 output TPS 33.9076、total TPS 169.5380。证据支持固定 workload 与成功完成；但 dmon 文件本身在远端/本地一致，其 manifest hash entry 不匹配真实 dmon hash；runner 声称 peak concurrency 8 与 server cap 4 不一致，未当作实际并发；query telemetry 仅覆盖首段、无完整三次 post-repeat 样本。保留这些限制，不宣称无条件通过。没有新 workload。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-VERIFY2-20260908.md`：Remote:
```text
/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/
```
Local:
```text
.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-retry2-20260908/
```
Key hashes (SHA-256, verified against the local copy and remote content):
```text
c172f6deddf06d66ac12b1d016d9bc8fb9efd5a1c0cf5aabbd7d074c8f5fc883  runner/repeat-1.jsonl
dc27ce7b102674b9d86d25da33ae80b886f7fc85ee5acf1ff43730a0b8b08899  runner/repeat-2.jsonl
9fc6804a3d2b23fd176821709411daded16deebfe1292678d1f76393b540cad8  runner/repeat-3.jsonl
7f6a24802960697685f59e051c5f37cc1ff0a6f4880fd6a11cdf3c675c1a2227  runner/repeat-1.log

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-VERIFY2-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-VERIFY2-20260908.md`; SHA256 `7c8179a3752995bf8b99690fd05d1a27b53b5cd06f62169096e80371438157bd`; source state `local-only`
