# G3-PROFILE-C-PREFLIGHT-20260908

- **工作标题：** G3-PROFILE-C-PREFLIGHT-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
对 Profile C C1 运行前进行只读安全预检，核对服务/模型/runner 身份、GPU owner、资源、sidecar 与候选端口；仅在所有门槛满足时才准许后续启动。

## 实际改了什么
只读运维预检并生成报告及本地原始证据。报告明确未做 service transition、signal、launch、benchmark request、dmon、reset、download、remote write、source/model edit、audit、tracing 或 instrumentation；无产品文件改动。

## 生成结果与验收
Preflight **FAIL（fail closed）**，不得启动 C1。服务、身份、runner、sidecar、磁盘及候选端口检查通过，但 GPU-owner gate 失败：driver compute-app 查询连续报告 PID `483639`（`[Not Found]`、22,776 MiB），而 `/proc/483639` 不存在；虽然 `fuser` 将设备 handle 归于 v1 tree，此矛盾未在只读任务内解释或清除。该 PID 状态是报告当时观测，不代表当前主机状态。须由新授权任务解决并重新验证后才可继续。

### 产物
本地 raw evidence 位于报告列明的 `g3-profile-c-preflight-20260908T181900Z/`；包括远端快照、重复 GPU owner 检查、身份与端口证据及 SHA256SUMS。首次 identity 尝试超时，仅保留 provenance，不作为通过条件。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-PREFLIGHT-20260908.md`：Fresh local raw evidence and hashes:
`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/raw/g3-profile-c-preflight-20260908T181900Z/`
- `remote_snapshot.txt`: process/listener snapshot, health/loads/models,
  GPU summary, disk, memory, and candidate port probes.
- `gpu_owner_recheck.txt`: repeated GPU queries, `/proc` check, service tree,
  NVIDIA file-descriptor ownership, and stale watcher details.
- `identity_readiness2.txt`: tokenizer sidecar hashes/readiness and PATH.
- `identity_readiness.txt`: retained first identity attempt; it timed out
  after model MD5/tokenizer stat while attempting an unnecessary GGUF glob…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-PREFLIGHT-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-PREFLIGHT-20260908.md`; SHA256 `deff71ccacabb6bbd9c37d8089915dd3cf1b4e4b5c31952b36712e7e1a488277`; source state `local-only`
