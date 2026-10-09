# G3-PROFILE-C-C8-LAUNCH-20260908

- **工作标题：** G3-PROFILE-C-C8-LAUNCH-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按授权启动 Profile C8 admission 候选（并发 8、Mamba pool 40、decode graph max 8），检验 shell-safe JSON argv 能否通过 CLI 并达到 startup/health gate。

## 实际改了什么
一次远端候选启动尝试；身份核验后停止当时 v1 进程树，候选退出后按冻结参数恢复 v1。未发送 benchmark traffic、下载、注入 audit/monitoring 或修改产品/模型/source 文件。

## 生成结果与验收
候选在 model loading 前因该 checkout CLI JSON parser 拒绝 equals-form `--default-chat-template-kwargs` 退出；未发生 candidate traffic、health 或 capacity admission。此为 argv/quoting incompatibility，不是 OOM 或 C8 capacity 结果。v1 已按报告验证 health 200、8035 监听、候选端口 18037 absent。任何 retry 需 fresh Task ID 使用 CLI 接受的 JSON 形式。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-LAUNCH-20260908.md`：Remote directory:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-20260908/launch/`
- `server.log` SHA-256 `fdb9c04e0c7b322117ec6e3e2f3f64bbc7035acd8d78510ea5f07152c197ef7f`
- `v1_restore.log` SHA-256 `87392d32c56f12ebb55f25faec390dfa7c50404fe227804544c9b6aab7cda327`
- `evidence.txt`, `pre_ps.txt`, `server.pid`, `v1_restore.pid`, and startup timestamps

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C8-LAUNCH-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C8-LAUNCH-20260908.md`; SHA256 `b98a1da1ed5040cda798aa1aa9a3b522f50e28faf6cf764df1275482aaaced62`; source state `local-only`
