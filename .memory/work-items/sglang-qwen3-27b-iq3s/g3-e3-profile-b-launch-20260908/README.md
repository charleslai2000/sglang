# G3-E3-PROFILE-B-LAUNCH-20260908

- **工作标题：** G3-E3-PROFILE-B-LAUNCH-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
执行 Profile B 独立 transition admission：在满足 host/GPU owner、v1 identity/idle、8036 端口与容量前置门槛后，才允许停止冻结 v1 并启动候选 B。

## 实际改了什么
实际只完成 pre-transition capture 与门槛核验；未停止 v1、未启动 B、未尝试 8036 health，也未发送 benchmark。远端 run root 保存 HALTED marker、pre-transition 与 v1 retention evidence。

## 生成结果与验收
Admission 在 transition 前 **HALTED**：虽然 v1 身份/健康/idle、端口及基础证据通过，但 GPU compute owner 存在无法归属 PID 315744 `[Not Found]` 且 `/proc` 无对应进程，违反硬性 owner gate。没有 B PID 或 B 性能结果；不得把 preflight 完成写成 Profile B launch 成功。需先外部解决异常并由新 Task ID 重做 admission。
Profile-B launch/admission is blocked safely at the pre-transition GPU-owner
gate. Existing v1 remains healthy and unchanged; all pre-transition and
post-decision evidence is preserved in the remote run root and local raw copy.

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-LAUNCH-20260908.md`：- Remote run root: `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T165140Z/`
- Local practical raw copy: `.memory/g3-baseline-20260907/work/raw/g3-e3-profile-b-20260907T165140Z/`
- Halt marker: `launch/HALTED.txt`
- Pre-transition evidence: `pre-transition/`
- Existing-v1 retention verification: `restore/` (no restore launch was needed because transition never started)

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-LAUNCH-20260908.md` → `.memory/g3-performance-and-serving/work/G3-E3-PROFILE-B-LAUNCH-20260908.md`; SHA256 `236e3bbf692d136a8c97d70c8cdbdcc6537512517358be2c8015bad5d09d0592`; source state `local-only`
