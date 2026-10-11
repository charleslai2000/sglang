# G3-IQ3-LOCAL-SMOKE-RETRY5-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-RETRY5-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在本机 GPU1 队列锁内，对固定 IQ3_S 模型与冻结 server argv 执行一次隔离启动，验证从参数预检到服务启动是否可通过；不替换 workload 或环境。

## 实际改了什么
无 GPU 的 `prepare_server_args()` preflight 成功；随后在 `flock` 保护、CUDA_VISIBLE_DEVICES=1 下尝试启动 loopback 18035 服务。未触碰用户进程、driver、CUDA、repository 或 production service；未发送 benchmark。

## 生成结果与验收
Invocation `INV-G3-IQ3-LOCAL-SMOKE-006` 的参数预检 PASS，但 server 在 bind/health 前因缺少 `compressed_tensors`（import `sglang.srt.model_loader`）退出，故 smoke blocked。没有 service admission 或 benchmark request。日志/preflight 与 GPU lock/后置资源证据见报告；参数检查通过不等于运行时可用。
- Health: not reached; no successful request; no exact-length server receipt evidence.
- Teardown: own failed launch PID 458884 was cleaned; port 18035 is not listening; GPU1 has no benchmark compute process.
- Residual cleanup: exact original wrapper tree PIDs 458488/458879 (child sleep 464040) was terminated after identity check; lock is released and port 18035 remains free. Evidence: `raw/g3-iq3-local-smoke-retry5-20260909/cleanup.txt`.
- The torch warning about GT 1030 is incidental; process used `CUDA_VISIBLE_DEVICES=1`.

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY5-20260909.md`：Remote/local artifact directory: `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry5/`.
Raw evidence: `.memory/g3-baseline-20260907/work/raw/g3-iq3-local-smoke-retry5-20260909/`; SHA256SUMS is included.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY5-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY5-20260909.md`; SHA256 `2513f354aa916ca784574fe616b4ce2fda53088c7c33d450fd0f920db8ecea79`; source state `local-only`
