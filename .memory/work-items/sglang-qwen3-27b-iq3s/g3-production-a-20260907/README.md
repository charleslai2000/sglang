# G3-PRODUCTION-A-20260907

- **工作标题：** G3-PRODUCTION-A-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按 E2 授权对冻结 v1 服务尝试 Production A C1/C4/C5 矩阵，并在 runner 内存或 workload binding 不满足约束时 fail closed，不制造无效分数。

## 实际改了什么
尝试 C1 的默认数据集路径及显式 tokenizer 重试；四个客户端均被 Linux OOM killer 终止。保留失败 scorecard、命令、内核/runner 证据并停止矩阵；未改变 frozen v1 profile、产品代码或服务配置，也未下载 ShareGPT、替换 `random-ids`、伪造 JSON 或 monkeypatch。

## 生成结果与验收
E2 Production A **blocked**：四次 C1 均约 42.64–42.65 GB anon RSS、rc=137，在 dataset preparation/warmup/flush 前被 OOM kill；无 `result.jsonl`、无 measured request，因此不存在有效 C1 分数，C4/C5 未启动。原因包括当时 deployed runner 将 raw 11.77GB GGUF 交给 `AutoTokenizer.from_pretrained` 后才处理显式 tokenizer；另发现 `dataset-name=random` 会选择 ShareGPT 路径，而任务禁止下载且无已批准本地数据。任何 workload binding 或产品修复都需新 Task ID。

### 证据边界
该报告识别的 deployed source 没有 Git 元数据，未伪造 deployed commit；记录运行窗口内服务身份与故障证据。该历史状态不是当前服务状态，也不能把后续修复任务的成果倒灌进此 E2 结果。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `dac6db1ebabdb80209b757fd063cf53e05c091e7`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PRODUCTION-A-20260907.md` → `.memory/g3-performance-and-serving/work/G3-PRODUCTION-A-20260907.md`; SHA256 `1bdb283ebf2291063da2100d51ddd634c1c9514c9f43217908ea0c91daad8871`; source state `local-only`
