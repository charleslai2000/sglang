# G3-PROFILE-C-C6-DECODE-20260908

- **工作标题：** G3-PROFILE-C-C6-DECODE-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在已 admission 的 Profile C6 候选（max-running=6、Mamba pool=32、decode graph max=8）运行三次固定长度 native decode benchmark，记录缓存清理、吞吐、延迟、实际并发和 GPU telemetry。

## 实际改了什么
远端 benchmark 执行；使用候选 PID 488839/loopback 18036，`random-ids` + tokenizer sidecar、ISL/OSL=1024/256、seed 42、C=6/N=48，每次 flush，三次执行。无产品、服务配置、audit hook 或外部 dataset 修改/使用。

## 生成结果与验收
三次均 return code 0，144/144 请求成功；每轮平均实际并发约 5.99。output TPS 35.04/34.93/34.96，total TPS 175.20/174.66/174.80。无 warmup request（本矩阵此前 C1 已做初始 warmup）。runner stderr 在成功后有 resource_tracker RLock AttributeError，保留为非致命证据；runner peak concurrency=12 不作为有效并发，报告的有效平均 occupancy 为 5.99。候选 restore 是另项待办，报告不声称 C6 为最终最优。JSONL、日志、loads 与 dmon 的原始 artifacts/hash 见报告。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-DECODE-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-DECODE-20260908.md`; SHA256 `a24bfc20fc5c574410a3a06e6089210792b4f6260199f83ef2dce478be4d4adb`; source state `local-only`
