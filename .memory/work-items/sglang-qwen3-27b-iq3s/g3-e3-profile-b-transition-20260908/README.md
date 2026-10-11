# G3-E3-PROFILE-B-TRANSITION-20260908

- **工作标题：** G3-E3-PROFILE-B-TRANSITION-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按授权执行一次冻结 v1 服务到 Profile B 的运维转换，评估 B 启动 admission；若失败则按 runbook 恢复原 v1，并保存可审计证据。

## 实际改了什么
执行了 v1 identity recheck、按精确身份停止 v1、在 8036 按 runbook 启动 B，并尝试一次精确 v1 restore。没有 benchmark traffic，也没有 source/model 修改或参数替换；本项产物是远端 run root 与本地 209 文件 raw copy/report。

## 生成结果与验收
Profile B 在 CUDA graph startup capture 阶段 OOM，未通过 health/admission，故有效容量未知。随后 v1 restore 因 shell 找不到 `/usr/local/cuda` 下的 `nvcc` 在 health 前失败。任务最终 **blocked**：报告记录当时两服务均未运行，等待 host owner 通过获准环境恢复或另行授权 recovery；不得将此历史服务状态视作当前状态。没有发送基准请求，不能形成性能结论。

### 证据
远端 run root、209 文件本地 raw copy、B/restore 命令和日志 hash 见来源报告。B startup OOM 与 restore failure 是阻塞证据；Profile B effective capacity 未知。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-TRANSITION-20260908.md`：- Remote run root: `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T170803Z/`
- Local practical raw copy: `.memory/g3-baseline-20260907/work/raw/g3-e3-profile-b-20260907T170803Z/` (209 files)
- Local report: `.memory/g3-baseline-20260907/work/G3-E3-PROFILE-B-TRANSITION-20260908.md`
Key raw hashes:
```text
launch/profile-b.command  cb02a208e967ff1786c6841b6aa0ca0abc46e2e4d9bbd3535590351b029c8840
launch/profile-b.log      e653fb4cd4b9b53a0cb319336b7b749510d3ca08bd9a36350e424e448de2b608
restore/v1.command        69f80370e67d3e8e4c364ee847c1ef914641567a07dfc1ba2edb882909d70007
restore/v1.log            6b8581858b60ff59cd35eaea85816ec33a725e391cb4136c93c5da3ba9c112bb
```

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-TRANSITION-20260908.md` → `.memory/g3-performance-and-serving/work/G3-E3-PROFILE-B-TRANSITION-20260908.md`; SHA256 `e7930380ee6ae7476ff22f5da181819ed58b2681bde1e3a68cd8cc6aab394bf6`; source state `local-only`
