# G3-PROFILE-C-C8-LAUNCH-PYTHON-20260908

- **工作标题：** G3-PROFILE-C-C8-LAUNCH-PYTHON-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在授权 host 上以 Profile C8 容量配置启动候选 SGLang 服务，验证 startup/health/effective capacity 与 CUDA graph capture，作为独立 decode workload 的前置 admission。

## 实际改了什么
这是远端服务运行任务，不含产品文件修改。先身份核验并停止 v1 PID 496268，再在 loopback 18037 按冻结 parser/tool/KV/Mamba/template 加 C8 capacity flags 启动候选 PID 497622；无 benchmark traffic、audit hook 或下载。

## 生成结果与验收
Candidate startup **通过启动 admission**：health 200、loads idle、effective max-running=8、max-total-tokens=54093，完成 prefill/decode CUDA graph capture，未 OOM。只观察到启动/health/load 与 startup warmup traffic，未执行 benchmark；报告记录候选服务继续留存供独立授权 decode task。需后续 decode、v1 restore 及独立验证；该 startup 不能当作 C8 性能测试结果。远端 launch artifacts 与 hashes 见报告。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-LAUNCH-PYTHON-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C8-LAUNCH-PYTHON-20260908.md`; SHA256 `f6cbb7e183a8f968f12df6749b330db11f4391ce17affc9ea2a4e8c3af158006`; source state `local-only`
