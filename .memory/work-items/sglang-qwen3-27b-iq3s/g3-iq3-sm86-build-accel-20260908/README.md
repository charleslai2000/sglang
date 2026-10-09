# G3-IQ3-SM86-BUILD-ACCEL-20260908

- **工作标题：** G3-IQ3-SM86-BUILD-ACCEL-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在授权隔离 CMake build 中恢复/加速 SM86 AOT Ninja 构建，并在暂停时只停止明确归属该隔离 build tree 的进程，保留可续建 cache/object 与状态证据。

## 实际改了什么
确认隔离 Ninja/CMake/wrapper PID 与 build root 后停止这些 build 进程；按 resume command detached 启动一次，用户暂停时再仅对已确认的隔离 build PIDs 发 SIGTERM。保留 CMake cache、object files 与日志；生产 v1 PID 503601/8035 未触碰。无产品源码改动。

## 生成结果与验收
暂停时 Ninja 在 `[2/484]` 编译阶段；停止后指定 build PIDs 均消失。没有最终 exit status、`common_ops*.so` 或 hash，状态仍 **pending**，native SM86 未确认。raw status file 保存过程证据。任何续建需 fresh authorization；不得将启动或部分进度写为 build 完成。

结果：隔离 build tree 的既有 Ninja (555601) 被确认后停止；resume 启动至 `[2/484]` CUDA object 编译，用户暂停后仅终止所确认的 wrapper/CMake/Ninja PIDs，cache/object/log 保留。无最终退出码、`common_ops*.so` 或 hash，状态仍 paused/pending，native SM86 未确认完成。生产服务 PID 503601/port 8035 未触碰；续建须 fresh authorization。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-BUILD-ACCEL-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-BUILD-ACCEL-20260908.md`; SHA256 `91a657282abdfb857eeae27f0b502d492469a99d39467af057836d24ec1ea625`; source state `local-only`
