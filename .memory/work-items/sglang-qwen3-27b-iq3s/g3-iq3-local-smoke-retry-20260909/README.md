# G3-IQ3-LOCAL-SMOKE-RETRY-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-RETRY-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在本机 RTX 3090 队列锁保护下，使用指定 IQ3_S 模型、冻结 serving 参数和端口 18035 执行隔离 smoke 启动，检查本地运行环境能否进入服务 admission。

## 实际改了什么
取得 `/mnt/data/gpu/3090.lock` 后执行一次精确 launch；没有停止或修改其他进程，未发送 health 或 benchmark request。未报告产品/仓库文件改动。

## 生成结果与验收
Invocation `INV-G3-IQ3-LOCAL-SMOKE-002` / epoch E14 在 Python import 阶段因缺 `openai` 退出，未产生活动 server PID，未发送请求、未加载 GGUF。失败后端口及 lock 释放，GPU 保持空闲。故 smoke **blocked**，不能据此评价模型或 kernel；raw queue/server logs 的 hash 见原报告。后续须补 approved dependency 并以新 invocation 重试。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY-20260909.md`; SHA256 `24dbf7e48941020d1f1694301d39609240df798753a17d5f1361eb76ad9d1eea`; source state `local-only`
