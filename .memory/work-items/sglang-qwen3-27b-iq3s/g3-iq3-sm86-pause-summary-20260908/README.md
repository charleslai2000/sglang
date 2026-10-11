# G3-IQ3-SM86-PAUSE-SUMMARY-20260908

- **工作标题：** G3-IQ3-SM86-PAUSE-SUMMARY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
汇总 G3 IQ3_S / SM86 阶段的已核实性能口径、kernel 路径、SM86 隔离构建和 no-copy 探索状态，并明确用户要求暂停后的边界，避免把未完成构建或性能假设误写成成果。

## 实际改了什么
这是文档总结工作。归集报告说明此前存在的本地 AOT CMake SM86 gencode 修改，但该修改属于所总结的先前工作，并非本总结报告新增改动；本报告自身写入仅为总结文档。其他本总结没有列出的实际修改文件未知。

## 生成结果与验收
总结确认没有完成 MMQ 实现、SM86 修正版扩展构建或性能提升验证。约 170 数值是 Total TPS 而非 output TPS；记录的比较来自既存三次重复 JSONL/stdout，不是新测量。隔离 Ninja 构建按暂停要求停止，未取得最终 `.so`/hash 或 runtime acceptance；flat-storage patch 曾被 BLOCK 并回退，相关测试删除。报告及后续工作状态为 pending；不声称 IQ3_S MMQ 已实现、fallback 已消失或吞吐已提升。后续只可在新授权/Task ID 下进行。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-PAUSE-SUMMARY-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-PAUSE-SUMMARY-20260908.md`; SHA256 `d57f947460c259b9843dd09f70210402c3399a4c9edd9215f25c69e5648811cc`; source state `local-only`
