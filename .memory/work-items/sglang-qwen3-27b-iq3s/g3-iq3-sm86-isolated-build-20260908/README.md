# G3-IQ3-SM86-ISOLATED-BUILD-20260908

- **工作标题：** G3-IQ3-SM86-ISOLATED-BUILD-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在隔离目录中按 RTX 3090 / SM86 目标配置构建 `sgl-kernel` AOT 扩展，验证 build 是否包含 native `sm_86`，不触碰正在运行的 v1 服务或替换已部署扩展。

## 实际改了什么
将含 `compute_86,code=sm_86` 的 staged source 放在隔离构建目录并运行 CMake/Ninja configure/build；没有编辑 deployed source、安装 live extension、重启服务或运行 benchmark。初始 wheel 命令因缺少 `uv` 即止，未下载/安装；改用支持的 host CMake fallback 配置构建。

## 生成结果与验收
CMake configure 成功并确认 NVCC flag 包含 `compute_86,code=sm_86`。报告截点 Ninja 仅到 `[2/506]`，构建仍运行且无最终 `.so` 或 `cuobjdump --list-elf` 结果。因此任务仍 pending，native SM86 未确认。环境观察为 RTX capability `(8,6)`、PyTorch 2.13.0+cu130、nvcc 12.8；这些不替代产物验收。

### 产物/证据
隔离远端 build root 与本地 raw logs 路径/hash 见来源报告；未安装扩展，v1 PID/8035 按报告未触碰。上述服务状态仅为历史任务边界记录。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-SM86-ISOLATED-BUILD-20260908.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-SM86-ISOLATED-BUILD-20260908.md`; SHA256 `183a51c10e285961c7a6e0219563e7d1350fe49624bdb6c54c8802ba7e700978`; source state `local-only`
