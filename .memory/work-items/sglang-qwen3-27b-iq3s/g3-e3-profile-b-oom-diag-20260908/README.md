# G3-E3-PROFILE-B-OOM-DIAG-20260908

- **工作标题：** G3-E3-PROFILE-B-OOM-DIAG-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读诊断 Profile B 已发生的 startup OOM，区分容量设计在当前单 RTX 3090 + 当前 SGLang/model 条件下过载，还是命令/模型/source mismatch。

## 实际改了什么
只读查看指定实验 host、原 B command 与 OOM artifacts；未 launch service、发 traffic、改 flags、reset GPU、signal、remote write 或 instrumentation。仅新增本报告。

## 生成结果与验收
分类为 (a)：按冻结 Profile-B contract 在该 SGLang build/model/single RTX 3090 上 startup over capacity，失败发生在必需的 prefill CUDA-graph capture；证据不支持误配 B flag/model/source。B 未通过 health/admission，无 effective capacity 或 benchmark result。报告明确该结论不外推至其它 allocator/backend/更大 GPU；改变这些条件属于新诊断范围。



## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-OOM-DIAG-20260908.md` → `.memory/g3-performance-and-serving/work/G3-E3-PROFILE-B-OOM-DIAG-20260908.md`; SHA256 `a2e2c11a7fe6d0b1b0843ab01315d986b81d8b05b05fbaeed95ee64864385afe`; source state `local-only`
