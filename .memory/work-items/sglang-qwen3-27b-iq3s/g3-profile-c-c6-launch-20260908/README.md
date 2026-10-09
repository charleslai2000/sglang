# G3-PROFILE-C-C6-LAUNCH-20260908

- **工作标题：** G3-PROFILE-C-C6-LAUNCH-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 loopback 18036 启动 C6 候选并完成 health/admission，容量参数为 max-running=6、Mamba pool=32、decode graph max=8；若启动失败，安全恢复 v1。

## 实际改了什么
只执行一次远端候选 launch 与授权 v1 rollback；无产品文件变更。候选在模型加载前退出，无候选 listener、request traffic、graph capture 或 GPU allocation。

## 生成结果与验收
C6 admission **blocked**：shell quoting 使 `--default-chat-template-kwargs` 到达 SGLang 为 `'{preserve_thinking:false}'`，被 argparse 以 `invalid loads value` 拒绝。该结果是 launch-command quoting failure，不是 OOM/capacity evidence。随后 frozen v1 在 8035 恢复，health 200、loads idle；报告时间点无 candidate PID。历史 GPU/服务观测不代表当前状态。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-LAUNCH-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-LAUNCH-20260908.md`; SHA256 `47e9a1b714fb7d51f59165adc6abf424ea3845f3d621fea056b41dc41c9847bd`; source state `local-only`
