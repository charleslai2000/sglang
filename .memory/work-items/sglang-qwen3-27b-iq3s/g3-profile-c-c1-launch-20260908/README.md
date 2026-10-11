# G3-PROFILE-C-C1-LAUNCH-20260908

- **工作标题：** G3-PROFILE-C-C1-LAUNCH-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 Profile C1 容量 tuple 下启动候选服务并完成 admission/graph capture，作为独立 decode 测量的前置服务阶段。

## 实际改了什么
远端候选服务运维启动任务；没有产品文件变更。按授权核验并停止当时 v1 PID 与其明确子进程，在 loopback 18035 启动候选 PID 470950，使用并发 4、Mamba pool 20、decode graph max 4。

## 生成结果与验收
C1 admission **PASS**：health HTTP 200、effective max-running=4/max-total-tokens=148053，prefill/decode graph capture 完成，无 OOM；8035 下线、18035 由候选进程持有。报告明确没有 benchmark traffic 或 dmon，候选按计划留给独立 decode task。因此这是 startup/capacity admission，不是 C1 性能结果。历史 run ID 和容量/显存细节见原报告。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-LAUNCH-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-LAUNCH-20260908.md`; SHA256 `02f7800ff92e79cfba71357b0f6aff9b17c7c3db551350fcef2e357d64a5bb73`; source state `local-only`
