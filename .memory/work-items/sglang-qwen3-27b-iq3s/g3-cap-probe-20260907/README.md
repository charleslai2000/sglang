# G3-CAP-PROBE-20260907

- **工作标题：** G3-CAP-PROBE-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
执行授权范围内的纯能力/连通性探测，确认本地 Bash/SSH 工具可用、指定实验 host 可达，以及冻结 v1 health/PID 与远端 Python/SGLang 基本可读；不触发 benchmark 或服务变化。

## 实际改了什么
四项只读命令检查工具、SSH key 文件权限元数据（不读取 key 内容）、SSH host/health/PID 与远端 runtime 版本。无远端 mutation/write、无本地仓库文件修改（报告除外）；无 benchmark、服务启停或 mutating HTTP。

## 生成结果与验收
所有探测命令 exit status 0；当时 SSH 可达，health HTTP 200、PID 298123 存在，远端 Python 3.12.0/SGLang 0.5.10.dev0 可读。结论仅为 capability/reachability evidence，不证明具备运行完整 benchmark 的条件，也不是当前主机状态声明。



## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-CAP-PROBE-20260907.md` → `.memory/g3-baseline-core-unblock/work/G3-CAP-PROBE-20260907.md`; SHA256 `20fbae08e99804e46f7834e32ee8ebfa54ffafa9d0868d6431ed05c00d77c68c`; source state `local-only`
