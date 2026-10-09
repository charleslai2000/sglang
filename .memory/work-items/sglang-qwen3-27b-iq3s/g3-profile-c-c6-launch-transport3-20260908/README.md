# G3-PROFILE-C-C6-LAUNCH-TRANSPORT3-20260908

- **工作标题：** G3-PROFILE-C-C6-LAUNCH-TRANSPORT3-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
尝试启动 Profile C6 候选（max-running=6、Mamba pool=32、decode graph max=8），验证远端 shell transport 能否保留 frozen chat-template JSON 参数，并确认失败时不留候选进程。

## 实际改了什么
运维启动一次候选服务；确认并使用 v1 PID 486264/8035 的身份信息。候选未通过 argparse/startup 后未保留，随后使用 frozen argv 启动 v1 restore PID 487847。未改产品、模型或 benchmark data。

## 生成结果与验收
候选在 startup 前因 transport 剥除 JSON quote，参数成为 `'{preserve_thinking:false}'` 而被拒绝；没有候选 traffic，C6 admission 未通过。v1 restore 在观察窗口内仍加载权重、health 尚不可用，因此本报告截点不能声称恢复已验证完成。状态 **blocked**；需 argv-safe transport 的新 dispatch，并后续确认恢复。
## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-LAUNCH-TRANSPORT3-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-LAUNCH-TRANSPORT3-20260908.md`; SHA256 `bc677dc3870bace14d401b0b527579bad2c617c706c2e93cf644701e320ddbb5`; source state `local-only`
