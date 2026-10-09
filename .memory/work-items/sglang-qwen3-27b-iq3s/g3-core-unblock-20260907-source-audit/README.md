# G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT

- **工作标题：** G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读审计 G3 E3 benchmark runner/source，判断 frozen `random-ids` + tokenized exact-length workload 是否避开 ShareGPT、如何形成 native SGLang `input_ids` 请求，以及 GGUF client OOM 防护与运行时 smoke 仍需哪些证据。

## 实际改了什么
仅本地源码与既有状态的 read-only audit；无 SSH、benchmark/API request、source edit 或 remote operation。没有改文件。

## 生成结果与验收
报告确认源码路径上 `random-ids` 选择非 ShareGPT 分支；`random_range_ratio=1.0` 对应精确长度；`--tokenize-prompt` 经 native SGLang backend 发送 `input_ids`，保持 streaming/ignore-EOS 默认值。现有 `serving.py` 的 GGUF guard 检查 sidecar，避免 AutoTokenizer 将 GGUF 当 JSON 读取。但源码检查不能证明部署身份、实际收到的请求长度或无网络；这些仍需授权 runtime smoke。报告未声称运行时 gate 通过。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT.md` → `.memory/g3-baseline-core-unblock/work/G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT.md`; SHA256 `fc2ac37e57d228dbca62f4999de1f4217ef666eb376ea2557b707d6512053f12`; source state `local-only`
