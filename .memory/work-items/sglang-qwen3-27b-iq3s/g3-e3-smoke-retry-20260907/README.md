# G3-E3-SMOKE-RETRY-20260907

- **工作标题：** G3-E3-SMOKE-RETRY-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在旧 smoke 失败且新的 admission/idle gate 复核通过后，按更正后的 audit hook 和固定 native SGLang 单请求参数重试一次 E3 smoke；不扩大 workload、不重复循环。

## 实际改了什么
在新 RUN_ID 下尝试一次指定 benchmark client；preflight 记录 service health 200、idle loads 与冻结身份。没有修改服务、产品或 workload，也未进行第二次重试；保存远端与本地 raw subtree及校验清单。

## 生成结果与验收
Smoke **blocked**：client 在 Python/CUDA import 阶段被更正后的 audit hook 对正常 runtime open 拒绝，未完成单请求。依 dispatch 不再重试、不改 hook/workload、不转入 formal matrix。Raw subtree 116 个文件的 SHA256SUMS 核验通过，但这只证明保存文件完整，不代表 smoke 通过。需新授权决定并修订后再试。
ENTRY: ACCEPT
invocation_status: blocked
task_id: G3-E3-SMOKE-RETRY-20260907
epoch: E3
role: devops

## 生成结果与验收
Exactly one fresh native-SGLang smoke launch was admitted and attempted under
run ID `g3-e3-smoke-retry-20260907T141610Z`. The benchmark client failed during
Python/CUDA import because the required corrected audit hook denied normal
runtime opens. Per the dispatch, no retry, workload change, audit change,
service transition, or formal matrix point was attempted.
Remote raw root:
`/data/qwen3-g3-baseline/g3-e3-smoke-retry-20260907T141610Z/`
Local copied raw root:
`.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-retry-20260907T141610Z/`
The local raw subtree contains 116 files and its `SHA256SUMS` passes
`sha256sum -c`.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-SMOKE-RETRY-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-E3-SMOKE-RETRY-20260907.md`; SHA256 `779aeaa19b678974cc4db180ed0ae650d992f5b7bdcf43dcafd028965e581327`; source state `local-only`
