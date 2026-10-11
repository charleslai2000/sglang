# G3-RUNNER-OOM-FIX-SETTLE-20260907

- **工作标题：** G3-RUNNER-OOM-FIX-SETTLE-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
独立 settle/验证 runner OOM 修复 D5：核对部署与本地 `serving.py` 身份，检查真实 GGUF 路径在受限 RSS 下是否避开整文件解析，并确认模块可独立导入。

## 实际改了什么
此报告是验证，不是修复提交；未记录代码文件改动。未执行 benchmark、server 操作或 inference request。

## 生成结果与验收
D5 settled 且独立核验：local/remote `serving.py` byte-identical，SHA-256 一致；真实 GGUF 检查在 8 GiB cap 下返回 True，耗时 2.356s，peak RSS 1.428 GiB；standalone import exit 0。该验证没有发服务请求或进行端到端测量，不能扩展为性能结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-RUNNER-OOM-FIX-SETTLE-20260907.md` → `.memory/g3-performance-and-serving/work/G3-RUNNER-OOM-FIX-SETTLE-20260907.md`; SHA256 `9544f1b99f3eb8c372904028a9863444802755fed957069af3022d7aad4483d6`; source state `local-only`
