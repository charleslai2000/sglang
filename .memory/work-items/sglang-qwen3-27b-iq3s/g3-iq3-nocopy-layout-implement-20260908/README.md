# G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908

- **工作标题：** G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
实现 IQ3 GGUF 权重布局的第一项优化：将合并 shard 一次性打包到 flat allocation，并让 forward 使用该 allocation 内稳定连续 view，以避免重复 padded layout/切片拷贝。

## 实际改了什么
报告明确改动文件：
- `python/sglang/srt/layers/quantization/gguf.py`：增加 `_pack_gguf_shards` 与 `_gguf_shard_view`；将 padded merged-weight 改为一次 flat packing，保存逻辑/物理 metadata；apply 使用 packed view，同时保留旧 rectangular 参数兼容 fallback。
- `test/registered/expert_pack/test_gguf_shard_layout.py`：新增 CPU-only 布局、字节、顺序、连续 view、data pointer 稳定性及重复 apply 测试。
未改远端、模型、CUDA/C++ kernel、benchmark 或服务配置。

## 生成结果与验收
`py_compile` 与 `git diff --check` 成功。因本地环境缺少 torch 与 pytest，新测试未执行；无 CUDA graph、GPU kernel compatibility 或端到端输出等价性结论。正确性边界包括 IQ3 bytes 原样复制、QKV 顺序保持、256-byte shard alignment；后续仍需 torch/pytest、GPU/operator 与 graph 验证。Activation quantization reuse 和 IQ3 small-batch kernel 不在本项范围。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908.md`; SHA256 `86c71ceed02049a768e55b9db29a448579afc32ba921c657269d565195b1ad37`; source state `local-only`
