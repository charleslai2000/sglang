# G3-PROFILE-C-C1-LAUNCH-FIX-20260908

- **工作标题：** G3-PROFILE-C-C1-LAUNCH-FIX-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
修复 Profile C1 启动命令中 JSON default-chat-template 参数的 argv 引用方式，并在有界启动门槛内尝试一次 C1 admission；失败时恢复冻结 v1。

## 实际改了什么
报告记录的是一次运维启动尝试；未报告源码文件改动。使用 bash argv array 启动候选服务，并在失败后按精确身份停止候选、恢复原 v1。远端 artifact 留在报告给出的 RUN_ID 路径。

## 生成结果与验收
JSON 参数现已正确到达，日志确认 `preserve_thinking=False`；候选 PID `476413` 分配 weights/Mamba/KV 后进入 CUDA graph capture，但有界门槛超时前未达到 health/admission（health 000、最终 `ADMISSION=FAIL`）。没有 benchmark traffic 或 dmon。精确 v1 在 8035 恢复成功，HTTP 200 且 loads idle。故 C1 运行未通过，不能据此声明 profile 验收；仅启动参数引用问题得到验证修正。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-LAUNCH-FIX-20260908.md`：- candidate command is in `command`; it uses a bash argv array and `%q` output.
- candidate log shows effective `max_running_requests=4`, `max_mamba_cache_size=20`,
  `cuda_graph_max_bs_decode=4`, JSON template value, weights 11.86GB, Mamba
  allocation 3.01GB, KV allocation 4.52GB, then prefill graph capture.
- candidate health remained 000; `loads` empty; listener absent; final admission
  is `ADMISSION=FAIL`.
- rollback PID `477405` exact v1 command; final health 200, loads idle,
  effective v1 max_running_requests 5 and max_total_num_tokens 132436.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-LAUNCH-FIX-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-LAUNCH-FIX-20260908.md`; SHA256 `207e25eb4fdbe199f3c073ad546f14c536a6923d168e66e017984e275a01e8a6`; source state `local-only`
