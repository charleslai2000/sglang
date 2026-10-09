# G3-PROFILE-C-C1-LAUNCH-RETRY-20260908

- **工作标题：** G3-PROFILE-C-C1-LAUNCH-RETRY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按 Profile C1 launch admission 尝试以固定容量 tuple 启动候选服务；验证远端命令传输是否保留 chat-template JSON argv，并在启动失败时恢复 frozen v1。

## 实际改了什么
运维上先 identity-check 并停止当时 v1 PID 472940，候选启动一次后因参数解析失败退出；随后以修正 quoting 的冻结 v1 argv 恢复服务。未发 benchmark、dmon/query sampler，未改 source/model 或 reset GPU。

## 生成结果与验收
候选被 argparse 拒绝：shell quoting 将 `--default-chat-template-kwargs` 的 JSON 截断为 `'{preserve_thinking:'`，故未 admission，PID 474559 退出。精确 v1 rollback 在 8035 health HTTP 200 且 idle。C1 不得在本 Task 下重试；后续需新授权与 argv-safe transport。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-LAUNCH-RETRY-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-LAUNCH-RETRY-20260908.md`; SHA256 `202de360c97bdc6da16e912a8a1d2992016cb9e965753d39ffd4e3bd6405b26b`; source state `local-only`
