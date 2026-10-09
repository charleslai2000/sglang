# G3-IQ3-REVERT-FLAT-LAYOUT-20260908

- **工作标题：** G3-IQ3-REVERT-FLAT-LAYOUT-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按决定回退未通过审查的 flat-storage GGUF layout patch，仅恢复相关实现文件与新增测试，避免未验证的 Parameter/state_dict 语义变更继续留在工作树。

## 实际改了什么
将 `python/sglang/srt/layers/quantization/gguf.py` 恢复到 flat-storage patch 前工作树内容；删除 `test/registered/expert_pack/test_gguf_shard_layout.py`。报告明确未改远端、kernel、benchmark、review gate 或无关修改文件。

## 生成结果与验收
`git diff --check` 成功；新测试文件确认删除；`git status` 中既存无关 serving/OpenAI/sampling changes 与 handoff/memory 仍保留。回退范围仅限 flat layout patch。未做 runtime/GPU 验收，且该方案不应据此视为有性能收益。

结果：只回退 flat-storage patch，恢复 `gguf.py` 到原有 padded 2-D parameter 与 `.contiguous()` 实现，并删除新增 `test_gguf_shard_layout.py`；`git diff --check` 通过，确认删除测试文件，未触碰既存无关修改。无 runtime/GPU 验收；IQ3_S MMQ 另立任务。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-REVERT-FLAT-LAYOUT-20260908.md`：Commands run from the repository root:
```text
git diff --check
git status --short
git diff -- python/sglang/srt/layers/quantization/gguf.py
test ! -e test/registered/expert_pack/test_gguf_shard_layout.py
```
Observed:
```text
DIFF_CHECK_RC=0
TEST_REMOVED
```
`git status --short` retained the unrelated pre-existing changes:
```text

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-REVERT-FLAT-LAYOUT-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-REVERT-FLAT-LAYOUT-20260908.md`; SHA256 `52897f6bbd9b2aaeebf9cb705407d5ed9c3c2c80b81e0696b355c43f032891dd`; source state `local-only`
