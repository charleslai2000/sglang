# G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908

- **工作标题：** G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在授权的完整 600 秒 startup gate 下启动 Profile C1 候选，核实 frozen flags、effective capacity、CUDA graphs 与服务 health，作为独立 decode task 的前置 admission。

## 实际改了什么
远端运维启动 C1 候选 PID 478926/18035，tuple 为 max-running=4、Mamba pool=20、decode graph max=4；先身份核验并停止明确的 v1 PID。未发 benchmark traffic/decode、dmon/query sampler，也未添加 audit/tracing、reset GPU、下载或改 source/model。

## 生成结果与验收
C1 admission **PASS**：完整 600 秒 gate 内 health 200、loads idle，effective max-running=4/max-total-tokens=148053，prefill/decode graph capture 完成，无 OOM；18035 仅候选持有。候选留给依赖任务，未得到任何 benchmark performance result。显存分配与启动证据见报告。
- RUN_ID: `g3-profile-c1-timeout-20260908T025800Z`
- Remote artifacts: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-timeout-20260908T025800Z/c1-timeout/launch/`
- Candidate PID: `478926`; port `18035`
- Tuple: `max-running-requests=4`, `max-mamba-cache-size=20`, `cuda-graph-max-bs-decode=4`
- Health: HTTP 200; 8035 absent; 18035 owned only by PID 478926
- Loads: idle (`num_running_reqs=0`, `num_waiting_reqs=0`), effective `max_running_requests=4`, `max_total_num_tokens=148053`
- Allocation: weights 11.857 GB; Mamba conv 0.06 GB + SSM 2.95 GB; KV 2.26 GB K + 2.26 GB V; graph 1.90 GB
- CUDA graphs: prefill completed in 70.41 s and decode completed in 2.21 s; no OOM; free VRAM 1.46 GB after decode graph
- GPU attribution: one candidate tree via `/dev/nvidia0` handles (478926/479012/479013); driver query shows one `[Not Found]` worker row (500367, 22792 MiB), with no competing fuser owner


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908.md`; SHA256 `9e8231d33b442ebb989f6f30b922feb240e7bb8306e29123384f28d7fca5b5f6`; source state `local-only`
