# Bounded CPU-first diagnosis of the residual SGLang GGUF incoherence on M3/M4 under

- **工作标题：** GGUF-M3M4-RESIDUAL-CAUSE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/GGUF-M3M4-RESIDUAL-CAUSE-20260918.md`：**
the post-fix working tree (tokenizer id-binding fixed), where llama.cpp (same GGUF, same
prompt, equivalent sampling) is coherent.
Scope: Read-only product source. CPU-only: no GPU, no CUDA, no server start/stop, no port
bind, no process signals. Probes used the already-authorized interpreter
`/opt/sglang/local-prod-v1/env/bin/python` with `PYTHONPATH=<repo>/python`. The CPU-only
llama.cpp build at
`/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu/bin/` was run
read-only (no server; `llama-tokenize`, `llama-completion`, `llama-cli`) — no CUDA libs

## 实际改了什么
只读产品源码与已存在的 per-request metrics/log，调用授权 Python 环境及 CPU-only llama.cpp tokenize/completion/CLI；未使用 GPU/CUDA，未启停服务、绑定端口、发 signal 或修改源码。诊断产出报告，没有产品修复。

## 生成结果与验收
五项诊断完成：prompt 的 `enable_thinking:false` 分支及 canonical input_ids 正确；SGLang 与 llama.cpp 对 raw probes tokenization 一致；同文件同 prompt greedy 下 SGLang 循环而 llama.cpp 输出正确，定位残余到 SGLang qwen35 forward/weight path，但具体 tensor transform 尚未证明。EMPTY_CONTENT/TOO_SHORT 均由模型主动输出 EOS 解释；M3 chat_code PASS 是空代码 compile 导致的 harness vacuous pass。排序的权重布局、FP8 KV、recurrent/cache 候选仍属推断；唯一决定性 FP8-vs-auto GPU discriminator 未执行，因此没有更深层 root cause 结论或产品改动。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/GGUF-M3M4-RESIDUAL-CAUSE-20260918.md` → `.memory/phase2-hicache-design/agents/GGUF-M3M4-RESIDUAL-CAUSE-20260918.md`; SHA256 `0506b6e58dbd904769a467b9adea3b00eda3d7612faa7ba325a6fb2669f01d41`; source state `tracked`
