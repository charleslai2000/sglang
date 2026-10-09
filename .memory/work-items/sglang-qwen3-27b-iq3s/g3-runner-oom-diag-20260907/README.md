# G3-RUNNER-OOM-DIAG-20260907

- **工作标题：** G3-RUNNER-OOM-DIAG-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
解释 native `python -m sglang.benchmark.serving` 对 11.77GB GGUF 发生约 42.6GB RSS、导致 OOM kill 的根因，并为后续安全 smoke 确定需修复的 runner 路径。

## 实际改了什么
这是取证/根因诊断报告；报告未指明本 invocation 修改代码。分析的目标代码路径是 `serving.py`，不能将其作为已改文件记录。

## 生成结果与验收
报告将 OOM 归因于单次 `check_chat_template(args.model)` 调用把 GGUF 文件路径传给 Transformers `AutoConfig.from_pretrained`，按 JSON config 读取导致整份 GGUF 被缓冲/解码，叠加 torch/transformers/sglang 基线内存将匿名 RSS 推至约 42.6GB。此为报告基于 stack/受限复现的根因结论；没有据此声称修复已部署或 benchmark 已可运行。后续需另有修复与受限验证任务。
ENTRY: ACCEPT
status: done

## 生成结果与验收
The deterministic ~42.6GB anonymous-RSS kernel OOM of `python -m sglang.benchmark.serving`
is caused by a **single call**, `serving.py:1902 check_chat_template(args.model)`, which
runs `transformers.AutoConfig.from_pretrained(<11.77GB .gguf path>, trust_remote_code=True)`.
In transformers 5.12.1 that call treats the raw GGUF file as the JSON config file and executes
`configuration_utils.py:888 _dict_from_json_file` → `reader.read()`, which **pre-reads the
entire 11.77GB GGUF into the TextIOWrapper/BufferedReader internal buffers and incrementally
decodes it as UTF-8 before raising UnicodeDecodeError** (the error only surfaces after the
whole-file buffering pass completes). That whole-file buffered read + partially built str in a
process that has already imported torch+transformers+sglang (patches, CUDA init, ~1.1GB baseline)
grows anonymous RSS to ~42.6GB — killing the host's 48GB/0-swap memory and OOM-killing the runner.
The allocating call frame (captured by faulthandler stack dump in a capped faithful run and in a
direct `AutoConfig.from_pretrained` replica):
```
transformers/configuration_utils.py:888 _dict_from_json_file  -> reader.read()

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-RUNNER-OOM-DIAG-20260907.md`：| phase | command | peak RSS | result |
|---|---|---|---|
| P0 `import sglang.benchmark.serving` | capped 10GB | 1.10 GB | rc=0, OK |
| P1 `get_tokenizer(<GGUF>)` as runner | capped 10GB | 1.33 GB | rc=0, OK |
| P2 `AutoTokenizer.from_pretrained(<GGUF>, trust_remote_code=True)` replicate | capped 10GB | 0.81 GB | rc=1 (fast MemoryError at the SAME `_dict_from_json_file` read — the 10GB ulimit -v capped the buffered read, which uncapped grows to 22-42GB; same site, cap changed failure mode not location) |
| faithful full runner (run_faithful.py) | watch kill @6GB | reached 6GB | faulthandler stack = `_dict_from_json_file:888 reader.read()` via check_chat_template |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-RUNNER-OOM-DIAG-20260907.md` → `.memory/g3-performance-and-serving/work/G3-RUNNER-OOM-DIAG-20260907.md`; SHA256 `fa012c7b7c6a4ea67567f259be017b9ba1c66741d074015501b9f8cbd9091421`; source state `local-only`
