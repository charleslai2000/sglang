# G3-SSH-KEY-20260907

- **工作标题：** G3-SSH-KEY-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
为已授权实验主机配置专用 SSH public key 并验证 BatchMode SSH 连通性，避免后续运维执行交互式认证。

## 实际改了什么
报告简记 key appended，权限设为目录/文件 `700/600`，并记录 key fingerprint（部分遮蔽）。原文没有给出具体本地 key 文件路径，也未记录被修改的产品仓库文件；不据此补猜实际 path。

## 生成结果与验收
新 BatchMode SSH 成功，invocation done、无 open issues。该运维准备项只证明当时认证连通性，不包含后续服务/benchmark 操作，也不代表当前 key 或连接状态。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-SSH-KEY-20260907.md` → `.memory/g3-serving-and-runtime-operations/work/G3-SSH-KEY-20260907.md`; SHA256 `7945dc5b3eb0daa978f948521a7457b5310d8b799a6b445db4fe3e957395f541`; source state `local-only`
