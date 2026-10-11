# G3-IQ3-LOCAL-READY-SCAN-20260909

- **工作标题：** G3-IQ3-LOCAL-READY-SCAN-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读扫描本地工作站，判断是否具备在 RTX 3090 上进行 IQ3_S/SM86 验证所需的 GPU、Python/CUDA runtime、模型和 kernel artifact，并列出启动前依赖。

## 实际改了什么
只读 scout 检查当前主机和 repository；没有启动/停止 GPU workload、下载或安装 package/model，也未附着用户进程。无产品文件修改。

## 生成结果与验收
观察到 RTX 3090 在扫描时空闲，但本地部署 **not ready**：系统 Python 缺少 torch、sglang 等运行包；无匹配部署环境、GGUF/IQ3_S 权重或 `common_ops*.so`；仅有 CUDA 12.0 nvcc，不能证明目标环境或完整 AOT build 可用。仓库当时 HEAD 含 SM86 AOT CMake 改动，但本机没有编译产物。GPU 空闲仅是瞬时观察，测试前仍须取得共享队列并复查。报告为只读 readiness 结论，不包含实现或部署。

### 产物/证据
报告记录了定向 GPU/process/toolchain/import/dependency/model/artifact 搜索及 Git 状态检查；先前 prerequisite 报告为补充证据。远端部署路径未被假设存在于本机。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-READY-SCAN-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-READY-SCAN-20260909.md`; SHA256 `ad515e07819fbadf4fddb13c115b5a9def8f7e335d50723ace3dae43c13ff087`; source state `local-only`
