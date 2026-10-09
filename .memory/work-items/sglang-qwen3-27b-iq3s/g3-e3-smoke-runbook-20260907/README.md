# G3-E3-SMOKE-RUNBOOK-20260907

- **工作标题：** G3-E3-SMOKE-RUNBOOK-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
设计一-request E3 smoke runbook，验证原生 serving runner 对 GGUF 模型使用显式 tokenizer sidecar，客户端不解析 GGUF、不访问外网/数据集，并以服务日志、JSONL、RSS 和 audit evidence 共同证明单请求准确性；smoke PASS 后才允许独立 formal matrix。

## 实际改了什么
设计型运维文档，仅写本报告；未发 benchmark request、远端写入、下载、process control、service change 或 product edit。文中的 `sitecustomize.py` 是未来 run-local audit 模块建议，不是本工作实际写入的产品文件。

## 生成结果与验收
定义只针对 loopback 8035 冻结 v1 服务的一次请求：ISL 2048、OSL 512、random-ids、seed 42、tokenize-prompt、明确 sidecar、flush 与离线环境；需同时通过不读 GGUF、RSS <4 GiB 且稳定、仅 loopback socket/无网络下载、JSONL 精确单请求与服务日志 `#new-token: 2048`、HTTP 200/服务身份未变等五项证据门槛。任一缺证或异常均 FAIL 并阻断 formal matrix。文档审查时旧 E2 process tree 未排空，故当时禁止启动；runbook 完成不代表 smoke 已执行。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-SMOKE-RUNBOOK-20260907.md` → `.memory/g3-performance-and-serving/work/G3-E3-SMOKE-RUNBOOK-20260907.md`; SHA256 `4d7d8bc63d65a03e242a15bf21826e3555117a3d16a497f582fd6caef6beb04d`; source state `local-only`
