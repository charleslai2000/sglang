# G3-PROFILE-C-C6-LAUNCH-EQUALS-20260908

- **工作标题：** G3-PROFILE-C-C6-LAUNCH-EQUALS-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
修正 C6 launch 的 JSON argv 传输形式，以 equals-form 参数保留 chat-template JSON，并完成候选服务 admission，供独立 decode task 使用。

## 实际改了什么
远端运维启动候选 PID 488839 于 loopback 18036，使用 frozen quality/runtime flags 与 C6 capacity knobs；将 `--default-chat-template-kwargs={...}` 作为单一 argv token，并从 `/proc/488839/cmdline` 验证。未下载或发 benchmark request。

## 生成结果与验收
C6 admission **成功**：health HTTP 200，loads idle，有效 max-running=6/max-total-tokens=91677；候选留待单独授权的 decode task。该报告仅证明启动和容量 admission，不是 decode/performance 测量。v1 PID 被身份核验后停止；历史候选运行状态不应推断为当前服务状态。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-LAUNCH-EQUALS-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-LAUNCH-EQUALS-20260908.md`; SHA256 `dae2eaf9d8bc10928220119676dbfacb983cb351d753bfb0b2eabe7db753eb62`; source state `local-only`
