# G3-IQ3-LOCAL-SMOKE-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 3
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
准备并尝试本机 RTX 3090/GPU1 的隔离 IQ3_S smoke。此卡按来源清单关联初始 preflight、针对 CLI `--help` 的调试报告及 retry4；关联理由是后两份明确指向同一 stable Task ID 并处理前序 gate 阻塞，而不是仅凭文件名。

## 实际改了什么
初始/retry4 阶段只执行 `CUDA_VISIBLE_DEVICES=''` 的启动预检；retry4 未取得 GPU lock，未启动 server 或 benchmark，也未更改产品/driver/CUDA/其他进程。debugger 阶段只做 root cause 调查并提出 `prepare_server_args()` full-argv parse 作为安全替代 gate，未记录产品代码修改。

## 生成结果与验收
初始 smoke blocked；`python -m sglang.launch_server --help` 在 Python 3.12 触发 argparse help formatting 的 `%o` TypeError（由含 `%` 的 `--hicache-writeback-reserve-gb` help text 引起），不是 CUDA/model/dependency failure。debugger 建议以无 GPU 的 full-argv `prepare_server_args()` 替代 `--help` gate，再在普通 GPU lock 下运行 unchanged argv。retry4 仍使用失效 `--help` 门槛而以 exit 1 失败，因此未获准 GPU lock；这几份材料没有记录 smoke request 或性能结果。后续是否采用 workaround、启动流程需 fresh authorization。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-20260909.md`; SHA256 `1f16051e1f7fbd97c57e3ad6dd503fb8d6768431d3c31bb5b151549f7a55a6c0`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-ARGPARSE-DEBUG-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-ARGPARSE-DEBUG-20260909.md`; SHA256 `a182315d82737610d1cb7f50dac9adf49b03292505eebc2dcda632e418934cea`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY4-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY4-20260909.md`; SHA256 `49af7c90af3998c2cf0007c30396f020c6cbb67f85ef4c29efe4250d04379a83`; source state `local-only`
