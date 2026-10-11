# O3060-RH-MATCH-EMIT-PROBE-20260910

- **工作标题：** OPS3060-RH-MATCH-EMIT-PROBE-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
对指定远端 RH 服务执行一次 bounded `/generate` probe，验证经接受的 scheduler deployment 是否会为该请求产生 `rh_match_prepare.v1` 等 runtime telemetry；不重试、避免无界或误判。

## 实际改了什么
只读核对远端 checkout binding、服务 PID/health、scheduler SHA 与 log offset；发送且仅发送一条包含 `text` 和 `sampling_params` 的请求，timeout 90 秒。未修改源码/服务/GPU/HiCache storage，也未重试。

## 生成结果与验收
Probe safely bounded，但 telemetry 验收失败：HTTP 400，服务因输入被计为 1,265,001 tokens、超过 262,144 context length 而在模型执行前拒绝；因此无 request ID、无 probe-correlated RH events，`rh_match_prepare.v1` 未验证。无 fatal/OOM/HTTP5xx；health 仍 200、PID 与 scheduler hash 保持。不能声称运行时 RH 值、性能或 restore 成功。短输入重测需 fresh Task ID。
- HTTP status: `400`.
- Curl exit: `0` (the HTTP error was returned by the service).
- Raw response: `{"error":{"message":"The input (1265001 tokens) is longer than the model's context length (262144 tokens)."}}`
- Remote raw artifact: `/tmp/rh-match-emit-probe-03a170-20260910.raw`
- Raw artifact bytes: `109`.
- Raw artifact SHA-256: `5fe9d38ce1d3a36deea032771e11911059956aebd3f349afa7451d53280f766d`.
- No abort was required because the request was rejected before model execution and
  did not hang. No retry or second request was made.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-PROBE-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-PROBE-20260910.md`; SHA256 `9a104205a30d9f9484164db9539a63da6a5a8ca84b047d1eb4e1cc320146a085`; source state `tracked`
