# G3-PROFILE-C-C6-LAUNCH-RETRY-20260908

- **工作标题：** G3-PROFILE-C-C6-LAUNCH-RETRY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 Profile C6 容量参数下尝试启动候选服务，验证之前的 argv quoting 问题是否解决；失败时恢复冻结 v1，并禁止在未 admission 情况下发送 workload。

## 实际改了什么
对授权 host 进行一次候选 launch 和 v1 restore；C6 tuple 为 max-running=6、Mamba pool=32、decode graph max=8。未发 benchmark、下载、audit hook 或产品文件修改。

## 生成结果与验收
候选服务因 shell quoting 丢失 JSON 引号，`--default-chat-template-kwargs` 收到 `'{preserve_thinking:false}'` 并被拒绝，未绑定端口/未产生 health、graph 或 workload 证据。随后 frozen v1 restore 经报告核验成功（health 200、idle；具体身份见报告）。C6 launch **blocked**，属于 quoting failure 而非 OOM；后续需要新授权与 argv-safe transport。
ENTRY: ACCEPT

## 实际改了什么
授权 host 上执行一次候选 launch 和 frozen v1 restore；C6 tuple 为 max-running=6、Mamba pool=32、decode graph max=8。未发 benchmark、下载、audit hook 或产品文件修改。

## 生成结果与验收
候选服务因 shell quoting 丢失 JSON 引号，`--default-chat-template-kwargs` 收到 `'{preserve_thinking:false}'` 并被拒绝，未绑定端口/未产生 health、graph 或 workload 证据。随后 frozen v1 restore 经报告核验成功（health 200、idle；具体身份见报告）。C6 launch **blocked**，属于 quoting failure 而非 OOM；后续需要新授权与 argv-safe transport。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-LAUNCH-RETRY-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-LAUNCH-RETRY-20260908.md`; SHA256 `60121b63d0a8b03924f0ab4ab3206cc96bb5cdc78eb18622f048c0bdb7c46ad0`; source state `local-only`
