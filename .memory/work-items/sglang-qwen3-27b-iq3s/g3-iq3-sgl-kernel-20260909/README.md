# G3-IQ3-SGL-KERNEL-20260909

- **工作标题：** G3-IQ3-SGL-KERNEL-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 5
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
为明确指定的 checkout commit `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143` 按 AOT Makefile 构建并安装 `sglang-kernel` 至 task venv，验证 `sgl_kernel` import、wheel/.so 身份与 SM86 ELF。报告明确以同 Task ID 关联首轮阻塞、后续 PEP668 恢复、monitor/resume/resume2、detached build 各阶段。

## 实际改了什么
本工作链最初因无 CMake ≥3.31 且 wheelhouse 无 CMake 阻塞，未改产品源码。后续不同 invocation 处理 system-pip PEP668：改用 venv pip/uv，经 `sg dev -c` 验证依赖，设置 CUDA 13.0、MAX_JOBS=2 后恢复既有 incremental build；monitor/resume/resume2/detached 报告均只观察/续跑已授权 build，明确避免 duplicate build。各阶段证据在所列原始报告和 raw logs 中；不把 target Makefile 当作已修改文件。

## 生成结果与验收
归集到的最后阶段仍为 **pending**，不可称 build/install/SM86 验收完成：原始起始报告记录 CMake 缺失导致 `sgl_kernel` 未安装；后续阶段报告显示 CMake configure 成功并发出 SM86 gencode，Ninja/CMake build 在观测时仍运行，dist 为空/尚无完成 status， detached invocation 也无 status file。无 wheel/hash、已安装 package、shared-object 或 cuobjdump 结果，且无 GPU test。更晚的已归集报告若未提供，不推断终态；后续应从原有 build 的完成状态继续收集证据，不另行重复构建。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-20260909.md`：- Raw evidence: `work/raw/g3-iq3-sgl-kernel-20260909/evidence.log`
- Evidence SHA256: `d23e6684db2da5b6bd6901e985f1fbc8c38f2a1e9bd8ba1f3241a46b26269fc3`
- Package/build instructions: `python/sglang/kernels/aot/README.md`, `Makefile`, `pyproject.toml`
- Target commit: `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SGL-KERNEL-20260909.md`; SHA256 `fc72f55f043df15735d53d2ecc84293df3d9ba50b4fccb8194998f43619ee787`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-DETACHED-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SGL-KERNEL-BUILD-DETACHED-20260909.md`; SHA256 `79e609f51f24e700806b2e007ee3969955f84672b51c4c28903c4f079a52de96`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-MONITOR-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SGL-KERNEL-BUILD-MONITOR-20260909.md`; SHA256 `7edcb60f693f19f285bb31a7fcdab0570e90dbac96cfde92c37fc9650d5e0b22`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME-PEP668-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME-PEP668-20260909.md`; SHA256 `0bb9b5d60d8ed4f7a7be6b6d1ad633bdbce8584d9c8455b87ea008db77f1cb37`; source state `local-only`
- `g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME2-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME2-20260909.md`; SHA256 `d908ae9e31fc67584926ec5724a3eba68d7be62097203fc12da2e8c42cc615fe`; source state `local-only`
