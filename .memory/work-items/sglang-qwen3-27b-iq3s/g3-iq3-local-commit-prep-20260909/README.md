# G3-IQ3-LOCAL-COMMIT-PREP-20260909

- **工作标题：** G3-IQ3-LOCAL-COMMIT-PREP-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在本地 checkout 中提交 SM86 AOT build-preparation 改动，保留无关用户 dirty/untracked 内容，并执行最小静态验证；不执行远端/GPU/service 操作。

## 实际改了什么
提交仅改 `python/sglang/kernels/aot/CMakeLists.txt` 一行：在 `ENABLE_BELOW_SM90` 下添加 `-gencode=arch=compute_86,code=sm_86`。报告说明其余用户改动与未跟踪产物保持 unstaged。

## 生成结果与验收
`git diff --check` 通过，staged diff 仅含上述一行。提交 `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`（`build: add sm86 AOT target for IQ3 validation`），branch 当时 ahead 1。push 因配置的 origin `/tmp/sglang-qwen3-27b-iq3s.bundle` 不是 git repository 而失败，未更改 remote。此提交仅为 build preparation，不证明 SM86 runtime support 或已验证编译产物。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-COMMIT-PREP-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-COMMIT-PREP-20260909.md`; SHA256 `6e81c67cefc509dc178049b1c5320019c861f5e7791ad0fbe79c7a25eebef4cb`; source state `local-only`
