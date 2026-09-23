# NINfer-V100 + Qwen3.8-27B NVFP4 — Evaluation Instance Ledger

- Task root (absolute): `/home/ubuntu/workspaces/3rdparty/.memory/ninfer-v100-qwen38-nvfp4-eval`
- **Working directory (owner-binding, 2026-09-19)**: `/home/ubuntu/workspaces/3rdparty/ninfer-v100`（repo 根；本 Goal 的所有 build/run/bench 均以此为 cwd）
- Opened: 2026-09-19. Only the orchestrator writes this file (append-only history; control state at top).

---

## CONTROL STATE

**Goal**
在单张 Tesla V100 PCIe 32GB 上部署并验证 `geoffwatts/ninfer-v100` + `neroued/Qwen3.8-27B-nvfp4-NInfer`，最终只报告：
Environment / Build / Functional validation / Benchmark table / Defects-blockers / Conclusion。
仅做部署、验证、benchmark；**不修改 inference runtime**，除非现有代码明确无法构建，且必须先报 blocker。

**Scope**
- In: 环境记录（`nvidia-smi` / `nvidia-smi -q` / `nvcc --version` / `uname -a` / `free -h` / `df -h`）；确认 GPU=Tesla V100 32GB、sm_70、CUDA Toolkit 12.8；获取 `geoffwatts/ninfer-v100` 并记录 `git rev-parse HEAD`；CUDA 12.8 + `-DCMAKE_CUDA_ARCHITECTURES=70` 的 native 构建（**不得原样使用仓库 CUDA 13.1 Dockerfile**；若必须用 Docker，则自建 CUDA 12.8+sm_70 image）；下载 `qwen3_8_27b_nvfp4.ninfer` 并校验 SHA256；text-only CLI 功能验证；OpenAI-compatible server；benchmark A(无 spec)/B(MTP K=1)/C(MTP K=3)/D(MTP K=4) × {2K,8K,32K,128K}；一组真实 coding workload。
- Out: vision；`preserve-thinking`；kernel 优化；模型修改/重新量化；扩大测试范围（用户 Step 9 STOP）。
- Prohibited: **用 CUDA 13 编译 Volta**；修改权重；未经授权安装系统组件（例如安装 CUDA 12.8 属系统改动，须先报 blocker）。

**Terminal condition**
用户 Step 9：拿到第 7/8 步数据后**停止**，只输出六项报告 ⇒ `VERIFIED DONE`。
若硬件/工具链前提被证伪且无法在授权范围内解决 ⇒ `EVIDENCED BLOCKED` 或 `MATERIAL USER DECISION`（例如目标机并非 V100、或缺失 CUDA 12.8）。

> ### 🎯 OWNER 最终收敛判据（2026-09-19，**binding，取代上条**）
> **「在远程启动 Qwen3.8-27B 之后，用 `swe-harness-901` 直接开始测试；测试完成，本 Goal 才算结束。」**
> ⇒ **Terminal = ① `ninfer-serve` 在 V100 上成功监听 + ② 经 `swe-harness-901` 跑完 SWE 评估**。
> ⇒ `:8080` 起服只是**中途里程碑**，**不是**终点；不得在起服后即宣布 DONE。
> ⇒ 前置仍是 **BLOCKER-4（容器 rev3 vs rev2 不匹配）**：必须先解决才能加载模型/起服。

> ### 🔴 OWNER 追加指令（2026-09-19，**binding：持续推进至服务可启动**）
> **owner 去休息，授权 orchestrator 自行持续推进，直至「服务可以启动」**（不再逐项等确认）。
> **收敛判据**：`ninfer-serve` 在目标机**成功启动并监听** ⇒ 视为本阶段终点。
> **公网暴露（owner 提供的平台规范，必须遵守）**：
> - **必须监听 `0.0.0.0`**（**绝不能 `127.0.0.1`**，否则无法转发到公网）。
> - **必须用端口 `8080`**（平台"自定义服务"只转发 8080）。
> - 起服后须用 `ss -anplt | grep 8080` **验证端口处于 LISTEN**；无输出即启动失败，须查日志。
> - 长驻须用 `tmux` 或 `nohup` 托管，避免终端断开导致服务中断。
> ⇒ 与用户 Step 6 的原始 argv（`--host 0.0.0.0 --port 8080`）**一致**，无需变更。
> **边界**：仍**不得**修改 inference runtime；仍**不做** kernel 优化/模型改动/扩范围；网络或版本问题**只报告、不改系统环境**。

**Decisive frontier（当前）**
1. **CONTEXT-CAPACITY-AUDIT** — execute the tokenizer-aware single-request and concurrency admission probes under frozen V100/Qwen/NInfer K=3; no performance optimization.
2. **CLEAN EXECUTION** — remove the orphaned prior audit driver/flood, then run one bounded probe at a time; preserve exact PID/argv, hashes, start time, tokens, reservation/admission outcome, KV occupancy, memory, errors, and health.
3. **FINAL TABLE** — derive only the nine requested capacity fields and one production-safe recommendation below measured stable boundaries.
4. **STOP** — after the table and recommendation are evidenced, stop; no scheduler/cache/runtime changes.

**ACTIVE**
- `CONTEXT-CAPACITY-AUDIT-EXECUTOR-20260920` | executor | clean orphaned audit process and complete capacity audit | current service K=3 healthy | `agents/CONTEXT-CAPACITY-AUDIT-EXECUTOR-20260920.md`

**READY**
- none

**BLOCKED**
- none

**INTEGRATED**
- `CONTEXT-CAPACITY-AUDIT-RERUN-20260920` | prior worker terminated; no accepted capacity result; 220K request was admitted but cancelled before generation; orphan audit driver PID 96669 had flooded service; artifact `agents/CONTEXT-CAPACITY-AUDIT-RERUN-20260920.md`.
- `CONTEXT-CAPACITY-AUDIT-20260919` | prior worker captured config/PID/hash/startup memory only; all probes pending.
- `PROD-CANARY-TELEMETRY-20260919` | current K=3 service config/telemetry/rollback state recorded; PID 93152; private endpoint.

**NEXT**
- Dispatch executor to clean the orphan driver, verify quiet service, then execute the bounded capacity matrix one request at a time and finalize the table.

> ### 🖥️ OWNER 提供：**`swe-harness-901` VM**（2026-09-19；软件测试 VM）
> - 标识：**`swe-harness-901`**；用途：**Docker SWE-bench harness**；地址含 **`.203`**；**owner 已明示可直接 SSH**。
> - 属**本地网络**的独立测试 VM ⇒ 非本 Goal 的目标 GPU 机，是**评估/测试 harness 环境**。
> - **待核实**（由 `SCOUT-SVR01-VM-20260919` + 后续 SSH 验证）：完整 host/IP 与 SSH 端口、免密是否已就绪、harness 具体入口与用法。
> - 用途预期：为 Step 8「一组真实 coding workload」提供**标准 SWE-bench 评估**，而非重复文本 prompt。

**ACTIVE**
| task_id | owner | deliverable | deps | result artifact |
|---|---|---|---|---|
| `ENV-CAPTURE-20260919` | devops-executor（只读） | ✅ **DONE（已整合）**：本机 **P1–P4 全 REFUTED** | 无 | `agents/ENV-CAPTURE-20260919.md` |
| `REPO-ACQUIRE-RECON-20260919` | devops-executor | ✅ **DONE（已整合）**：副本 @ `b37d0dd3…`；13/13 CLI flag 存在；`sm_70` 需 CUDA ≥12.8 且 <13.0；Dockerfile=13.1.2 | 无 | `agents/REPO-ACQUIRE-RECON-20260919.md` |
| `REMOTE-ENV-CAPTURE-20260919` | devops-executor | ✅ **DONE（已整合）**：免密 SSH ✅；**真目标机 = `Tesla V100-SXM2-32GB` / sm_70 / driver 550.163.01 ✅ / CUDA toolkit 仅 12.4 / `cmake 3.22.1` / 无 ninja / 出口网络 UNKNOWN** | 无 | `agents/REMOTE-ENV-CAPTURE-20260919.md` |
| `REMOTE-NET-PROBE-20260919` | devops-executor（只读诊断） | ✅ **DONE（已整合）**：**GitHub HTTPS 不可达**；**hf-mirror.com 可达 (200)**；huggingface.co 超时；无 proxy；PyPI 可达 | 无 | `agents/REMOTE-NET-PROBE-20260919.md` |
| `TOOLCHAIN-SOURCE-FEASIBILITY-20260919` | devops-executor（只读诊断） | ✅ **DONE（已整合）**：CUDA 12.8 可从 NVIDIA apt repo 取得；cmake≥3.28 走 **PyPI**（apt 仅 3.22.1）；ninja 走 PyPI/apt；**CUTLASS 在目标机 BLOCKED**（GitHub 不可达 + 无可用镜像）⇒ 需本机中介 | 上项 ✅ | `agents/TOOLCHAIN-SOURCE-FEASIBILITY-20260919.md` |
| `SRC-TRANSFER-20260919` | devops-executor | ✅ **DONE（已整合）**：源码树经 SSH 流式传输到 `/hy-tmp/ninfer-v100`；HEAD + **tree hash `d6fda436…` 双侧一致**；`.git` 在 | 无 | `agents/SRC-TRANSFER-20260919.md` |
| `TOOLCHAIN-INSTALL-20260919` | devops-executor | ✅ **DONE**：CUDA 12.8 已在 `/hy-tmp/cuda-12.8`（V12.8.61，driver 仍 550.163.01）；cmake **3.31.10** + ninja **1.13.2** 在 `/hy-tmp/ninfer-tools`；**Step 4 依赖门禁 FAIL（pkg-config 缺失 ⇒ 全部 by-proxy FAIL）** | 无 | `agents/TOOLCHAIN-INSTALL-20260919.md` |
| `MODEL-ACQUIRE-VERIFY-20260919` | devops-executor | ✅ **DONE**：`/hy-tmp/models/qwen3_8_27b_nvfp4.ninfer` 23719715844 B；**SHA256 三源一致 MATCH**（LFS oid / SHA256SUMS / artifact-manifest.json）；单文件容器 | 无 | `agents/MODEL-ACQUIRE-VERIFY-20260919.md` |
| `DEP-GATE-VERIFY-20260919` | devops-executor（只读） | ✅ **DONE**：**FFmpeg 系统级完全缺失**（无 .so/无头/无 .pc）；**pkg-config 二进制不存在**（前次 FAIL 的根因）；系统 libcurl 仅 **7.81.0** 且无 dev；apt 仅 FFmpeg 4.4 / curl 7.81（**均低于要求**）；**conda 存在**（`/usr/local/miniconda3`，base 有 ffmpeg 8.11.1 curl） | 上项 ✅ | `agents/DEP-GATE-VERIFY-20260919.md` |
| `CUTLASS-MEDIATE-20260919` | devops-executor | ✅ **DONE**：CUTLASS v4.4.2 已落 `/hy-tmp/ninfer-v100-deps/cutlass`（SHA `da5e086d…`，无 submodule）；离线 configure 用 `-DFETCHCONTENT_SOURCE_DIR_CUTLASS=… -DFFETCHCONTENT_FULLY_DISCONNECTED=ON` | 无 | `agents/CUTLASS-MEDIATE-20260919.md` |
| `BUILD-V100-20260919` | devops-executor | ✅ **DONE**：`/usr/local/cuda`→`cuda-12.4` **已回滚**；conda env 门禁 **5/5 PASS**（avformat 60.16 / avcodec 60.31 / avutil 58.29 / swscale 7.5 / curl 8.21）；**三目标全部构建成功**；`ldd` **0 not found**；清理后 `/hy-tmp` **19GB** 可用。**未改任何源码** | 无 | `agents/BUILD-V100-20260919.md` |
| `CONDA-DEP-FEASIBILITY-20260919` | devops-executor（只读） | ✅ **DONE**：conda-forge 可取 ffmpeg 6.0.0–9.0.1 / pkg-config / libcurl 7.85–8.22 | 无 | `agents/CONDA-DEP-FEASIBILITY-20260919.md` |
| `FUNC-CLI-VALIDATE-20260919` | devops-executor | ⛔ **BLOCKED（真阻断）**：CLI flag 全在，但加载失败 —— **artifact `NINFER\0\3`(rev 3) vs 二进制仅支持 `NINFER\0\2`(rev 2)** | build ✅ | `agents/FUNC-CLI-VALIDATE-20260919.md` |
| `ARTIFACT-VERSION-DIVERGE-20260919` | devops-executor（只读调查） | ✅ **DONE**：V100 fork **未前进**（仍 `b37d0dd3`，0 commit）；rev3 只在真上游 `Neroued/ninfer@98dada0e`（**仅 sm_120a**）。模型仓 `main` **只发 rev3**。**结论：rev3+sm_70 无交集** | 上项 ✅ | `agents/ARTIFACT-VERSION-DIVERGE-20260919.md` |
| `MODEL-V2-HISTORY-FETCH-20260919` | devops-executor | ⛔ **BLOCKED（磁盘差 ~3.4GB）**：**已找到 rev2 revision = `3b84117e0fd258b45bd79778ec8d8f27a4ab3d56`**（2026-08-17，"Publish NInfer Qwen3.8-27B NVFP4 artifact"，**container_version 2**）；rev2 体积 **21,492,695,040 B**，SHA256 `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`；**无用的 rev3 文件已删**，剩 16.65GB | 上项 ✅ | `agents/MODEL-V2-HISTORY-FETCH-20260919.md` |
| `MODEL-V2-DISK-RECOVER-20260919` | devops-executor | ✅ **DONE**：rev2 artifact 已落 `/hy-tmp/models/qwen3_8_27b_nvfp4.ninfer`；SHA256 MATCH / 大小 MATCH / **前 8 字节 `NINFER\0\2` MATCH**；`/hy-tmp` 余 ~18.7GB。**BLOCKER-4 已解除** | 上项 ✅ | `agents/MODEL-V2-DISK-RECOVER-20260919.md` |
| `SWE-HARNESS-901-RECON-20260919` | devops-executor | ✅ **DONE**：`ssh swe901`(=`192.168.20.203`, user ubuntu) ✅；swebench 5.0.2 + mini-swe-agent 2.4.6；SWE-bench Verified(500) 已在位；**端点面 = `model.model_kwargs.api_base`（YAML）/ `SWE_API_BASE` env 覆盖** | 无 | `agents/SWE-HARNESS-901-RECON-20260919.md` |
| `SERVE-START-20260919` | devops-executor | ✅ **SERVE UP**：CLI 3/3 生成成功；`ninfer-serve` PID **33898**（tmux）**LISTEN `0.0.0.0:8080`**；`/health`=`{"status":"ok"}`；`/v1/models`=qwen3.8-27b；无 OOM/CUDA error | rev2 ✅ | `agents/SERVE-START-20260919.md` |
| `NET-BRIDGE-HARNESS-V100-20260919` | devops-executor | ✅ **DONE**：**Path A（公网）FAILED**（Privoxy 502 / 公网 IP 超时）；**Path B（本地 SSH 隧道）WORKING**：local `0.0.0.0:8080`→V100 `127.0.0.1:8080`（tunnel PID 1957126）；**harness VM 实测 `/v1/chat/completions` 成功（200，真实生成）**；endpoint=`http://192.168.20.250:8080/v1` | serve ✅ | `agents/NET-BRIDGE-HARNESS-V100-20260919.md` |
| `SWE-EVAL-RUN-20260919` | devops-executor | ✅ **Smoke PROVEN**：`--slice 0:3` 下 `astropy__astropy-12907`、`django__django-11299` 均 **Submitted 且产出真实 patch**；服务端日志无错误；TTFT 385ms–1.4s | 上项 ✅ | `agents/SWE-EVAL-RUN-20260919.md` |
| `SWE-EVAL-FULL-RUN-20260919` | devops-executor | ❌ **FAILED（空回件、零落盘）** ⇒ 是否已启动 full run **未知** | smoke ✅ | （无 artifact） |
| `SWE-FULL-RUN-RECONCILE-20260919` | devops-executor | ✅ **DONE**：full run **已在飞**（PID 57565，07:42 启动，非重复）；快照 **2/24**，两实例均产出 patch；GPU 100%、无错误；**该 harness 流程不计算 resolved rate**（需另跑评分） | 无 | `agents/SWE-FULL-RUN-RECONCILE-20260919.md` |
| `SWE-EVAL-COMPLETE-SCORE-20260919` | devops-executor | ❌ **FAILED（空回件、零落盘）** ⇒ 未造成破坏；改用有界轮询法 | — | （无 artifact） |
| `SWE-STATUS-CHECK-20260919` | devops-executor | ✅ **DONE（有界）**：生成 run **仍在跑**（PID 57565）；**8/24** 已处理、8 patch、全部 `Submitted`；**尚未评分**；GPU 100%、59°C、无错误 | 无 | `agents/SWE-STATUS-CHECK-20260919.md` |
| `SWE-MONITOR-SCORE-BOUNDED-20260919` | devops-executor | ⏳ **BLOCKED（有界预算耗尽，非故障）**：15 轮有界轮询后 **13/24** 完成；PID 57565 仍在跑；无错误；GPU 55–64°C；**未评分**（生成未完成） | 无 | `agents/SWE-MONITOR-SCORE-BOUNDED-20260919.md` |
| `SWE-MONITOR-SCORE-R2-20260919` | devops-executor | ❌ **FAILED（空回件 + WORKING stub）** ⇒ 再次印证：**等待不可放在 agent 内** | — | （stub） |
| `SWE-AUTOSCORE-DETACHED-20260919` | devops-executor | ✅ **DONE**：评分命令已定 = `swebench eval <local parquet> -p preds.json --run-id … -j 4 --split test --report-dir …`（**用本地 parquet，因该 VM 无 HF 网络**）；脱离终端 wrapper 已部署并启动（PID **105196**），状态文件 `evidence/autoscore.status` | 无 | `agents/SWE-AUTOSCORE-DETACHED-20260919.md` |
| `SWE-AUTOSCORE-STATUS-20260919` | devops-executor | ✅ **DONE（有界）**：`STATE=waiting`，23/24，生成仍在跑 | 无 | `agents/SWE-AUTOSCORE-STATUS-20260919.md` |
| `SWE-AUTOSCORE-POLL-R2-20260919` | devops-executor | ⚠️ **BLOCKED（预算耗尽，非故障）**：10 轮后仍 `STATE=waiting`、23/24、无错误 | 无 | `agents/SWE-AUTOSCORE-POLL-R2-20260919.md` |
| `SWE-LAST-INSTANCE-DIAG-20260919` | devops-executor | ✅ **DONE**：缺的是 `sympy__sympy-22456`；其容器 Up 17min（刚启动）；**PID 57565 存活（Sl, 0.5% CPU）**；V100 健康、req#929 在服务；**判定=慢实例正常推进，非挂死** | 无 | `agents/SWE-LAST-INSTANCE-DIAG-20260919.md` |
| `SWE-AUTOSCORE-POLL-R3-20260919` | devops-executor | ⚠️ **BLOCKED（预算耗尽）**：12 轮后仍 `STATE=waiting`、23/24 | 无 | `agents/SWE-AUTOSCORE-POLL-R3-20260919.md` |
| `SWE-LAST-INSTANCE-DIAG-R2-20260919` | devops-executor | ✅ **DONE（决定性）**：**服务端请求计数在 71s 内 `req#975`→`req#980` 前进**（~14s/req，每次 ~**95k token** prompt，decode 35–44 tok/s）⇒ **实例确实在推进，非挂死**；容器 `minisweagent-ad43bc34` Up 38min；无错误 | 无 | `agents/SWE-LAST-INSTANCE-DIAG-R2-20260919.md` |
| `SWE-AUTOSCORE-POLL-R4-20260919` | devops-executor | ✅ **DONE**：**生成完成 24/24**（`mini-extra` 已退出；`sympy__sympy-22456` 正常产出）；autoscore 进入 **`STATE=scoring instances=24`**，评分 **22/24 (92%)、0 失败** | 无 | `agents/SWE-AUTOSCORE-POLL-R4-20260919.md` |
| `SWE-AUTOSCORE-POLL-R5-FINAL-20260919` | devops-executor | ✅ **DONE**：评分为 96%（23/24）**评分进度**（非 resolved rate）；`preds.json`=24 | 无 | `agents/SWE-AUTOSCORE-POLL-R5-FINAL-20260919.md` |
| `SWE-AUTOSCORE-POLL-R6-20260919` | devops-executor | ✅ **DONE —— 终局数据**：`STATE=done`；**resolved rate = 21/24 = 87.5%**（0 error / 0 empty-patch）；未通过 3 例：`django__django-11820`、`scikit-learn__scikit-learn-12973`、`sympy__sympy-11618` | 无 | `agents/SWE-AUTOSCORE-POLL-R6-20260919.md` |
| `SCOUT-CODE-SIZE-20260919` | scout（只读） | ✅ **DONE**：仓库 1501 tracked files / 88M（含 .git 22M）；**项目自撰 ≈280,897 行**（`third_party` + `eval/corpora` 已剔除）；`src/` 149,844 行；**CUDA `.cu/.cuh` 77,294 行 = 27.5%** | 无 | `agents/SCOUT-CODE-SIZE-20260919.md` |

> ### ✅ SWE 评估完成（owner 终局判据 ② 达成）
> **`swe-harness-901` + SWE-bench Verified(24 实例) → resolved 21/24 = 87.5%**；0 基础设施失败、0 空 patch。
> 证据文件：`/home/ubuntu/swe-round1/evidence/openai__qwen3.8-27b.swebench-eval.json`。
> ⚠️ 严禁混淆：**96% 是评分进度**，**87.5% 才是 resolved rate**。

**剩余必要前沿**：**Production Acceptance Gate section 6 soak finalization**（60min/≥100 requests）。Sections 1–5 已完成；soak detached runner 仍在运行（PID 79438），未到终态。

> ### ✅ Gate section 5 完成（`GATE-P5P6-CONCURRENCY-SOAK-R2`）
> - **C1 baseline**：aggregate decode **59.60 tok/s**；single-request mean 67.08 tok/s。
> - **C2**：aggregate **81.66 tok/s = 1.370× C1 ⇒ PASS**（≥1.35）；single-request retention **85.7% ⇒ PASS**（≥65%）；OOM/CUDA=0。
> - **C4**：aggregate **63.90 tok/s = 1.073× C1 ⇒ FAIL**（能力线 ≥1.6）；无 OOM/CUDA。
> - 生产配置 C（max-concurrency=1, MTP K=3）已恢复并验证 `0.0.0.0:8080` health ok。
>
> ### ⏳ Gate section 6 soak 进行中
> - detached PID **79438**，目标 3600s / ≥100 requests；目录 `/hy-tmp/gate-20260919/soak/`。
> - 当前快照：约 1m14s、15 requests、0 OOM / 0 CUDA / 0 crash / 0 invalid；server config C healthy。
> - 最终 P95 degradation / throttling 判定须等 `soak_summary.json`。
>
> **综合当前（sections 1–5）**：decode 与 C2 并发达标；C4 不具扩展价值；MTP acceptance、128K cold TTFT、growing-prefix reuse ratio、device-only reuse 均未达 owner production gate。soak 完成后给最终生产判定。

> ### ✅ Production Acceptance Gate sections 1–4（`GATE-P1-DECODE-MTP-TTFT-CACHE-20260919`）
> **真实多文件 coding workload**（NInfer `src/serve` / `apps/cli` / `tools/bench`），V100 loopback client-side SSE TTFT；config C；256 output；1 warmup + 3 reps；生产 config C 已恢复。
>
> | 指标 | 实测 | Gate |
> |---|---:|---|
> | decode 2K/8K/32K/128K | **67.1 / 65.1 / 55.2 / 41.8 tok/s** | PASS / PASS / GOOD / GOOD |
> | MTP acceptance | **54.0 / 56.2 / 53.1 / 56.9%** | **FAIL**（≥60%） |
> | committed/round | **2.62 / 2.69 / 2.59 / 2.71** | PASS |
> | cold TTFT | **1.609 / 6.530 / 29.702 / 368.163s**（128K实际171K） | PASS / PASS / PASS / **FAIL** |
> | cache hit rate（warm turns 2–10） | **100% (9/9)** | PASS |
> | reused-prefix ratio | **63.1%** | **FAIL**（≥90%） |
> | device-hit TTFT | **4.988s mean**（1.749–11.023） | **FAIL**（≤1s） |
> | host-resume TTFT | **0.148s @32K / 0.294s @142K** | PASS |
>
> **关键机制**：owner 预期的 device-fast/host-slow 被**反转**：`host-state-slots=8` ⇒ 近 100% reuse + 亚秒 hot TTFT；`host-state-slots=0` ⇒ **无跨请求 reuse**。config C（device 1 + host 8）增长 conversation 的 reuse 在 **~8.4K tokens 饱和**，hot TTFT 由 1.7s 增长到 11s。
> ⇒ 当前仅凭 sections 1–4：**decode 达标，但 MTP acceptance、128K cold TTFT、growing-agent prefix ratio/device-hit TTFT 不达生产线**。sections 5–6 完成后才给最终生产结论。

> ### ✅ BENCH-ABCD 完成（16/16 格，`BENCH-ABCD-20260919`）—— 语料版上下文缩放表
> 语料 = 仓库 `ninfer-ppl-1m`（PG-19 / WikiText / 中文 wiki / **NInfer C++/CUDA 源码**）拼接，**非重复文本**；1 warmup + 3 reps；`max_tokens=128`；`cache_n=0`（各请求不共享前缀）。生产配置 C 已恢复（tmux `ninfer-serve`, `0.0.0.0:8080`, health ok）。
>
> | 配置 | 2K | 8K | 32K | 128K | （decode tok/s） |
> |---|---:|---:|---:|---:|---|
> | A 无 spec | 30.7 | 29.4 | 25.7 | 17.6 | |
> | B K=1 | 46.7 | 46.6 | 39.9 | 27.8 | |
> | **C K=3（生产）** | **63.1** | **61.1** | **52.3** | **30.4** | |
> | D K=4 | 59.2 | 52.6 | 49.2 | 31.2 | |
>
> | C 的 MTP | 2K | 8K | 32K | 128K |
> |---|---:|---:|---:|---:|
> | acceptance % | 48.1 | 50.2 | 49.2 | **36.3** |
> | acc/round（canonical `1+acc/rounds`） | 2.44 | 2.51 | 2.48 | 2.09 |
>
> **对 owner「最终核心判据」的初步对照（⚠️ 语料版，非 coding workload ⇒ 不作终判）**：
> - 32K ≥50 ⇒ **52.3 ✓ PASS**
> - 128K ≥35 ⇒ **30.4 ✗ FAIL**
> - **MTP acceptance ≥60% ⇒ 48–50 ✗ FAIL**（且 owner 明言 K=3/4 acceptance <50% 不适合作默认；C 恰在 48–50 边界，D 仅 34–38）
> - 无 spec baseline 门槛：8K ≥25 ⇒ 29.4 ✓；32K ≥20 ⇒ 25.7 ✓；128K ≥15 ⇒ 17.6 ✓
> - **Cold TTFT（`prompt_ms` lower bound）**：2K 1.79s ✓ / 8K 7.02s ✓ / **32K 33.3s ✗（限 32s，贴线）** / **128K 235s ✗✗（限 125s，超近 2×）**
>   ⚠️ **128K prefill 实测仅 558 tok/s**（8K 为 1162）⇒ **长上下文 prefill 吞吐腰斩**，与公开 ~1100 的线性外推不符，是真发现。
> - **A 配置 prefill 亦同**（558 tok/s @128K）⇒ 非 spec 引起。
> **⇒ 结论：语料版下 128K decode、MTP acceptance、长上下文 cold TTFT 三项已显 FAIL 风险；必须用 coding workload + prefix cache 复核后才可定判。**

> ### 🎯 OWNER 追加：**Production Acceptance Gate**（2026-09-19，**binding，第二个终局判据**）
> **在 A/B/C/D × context benchmark 完成后执行；不扩大模型/硬件范围。**
> **目标场景**：单张 V100 32G = **一个独立 Qwen3.8-27B agent inference service**；主 workload = **Codex/OpenCode：多轮、长 prefix、高 cache reuse**。
> **⚠️ 不得只看 TPS**：本 Gate 才是"**能否作为生产 Agent 服务**"的验收线。
>
> **1) 单请求 decode（真实 coding workload，非重复文本 ceiling）**
> | Context | PASS | GOOD |
> |---|---:|---:|
> | 2–8K | ≥60 tok/s | ≥80 tok/s |
> | 32K | ≥45 | ≥55 |
> | 128K | ≥30 | ≥40 |
> **无 speculative baseline 仅要求**：8K ≥25 / 32K ≥20 / 128K ≥15 tok/s。
>
> **2) MTP（coding workload）**：acceptance **PASS ≥60% / GOOD ≥70%**；mean committed tokens/round **PASS ≥2.5 / GOOD ≥3.0**。
> ⇒ 若 **K=3/4 acceptance <50%**，即使 synthetic TPS 高，**也不得作为默认配置**。
>
> **3) Cold TTFT**：2K ≤2.5s；8K ≤8s；32K ≤32s；128K ≤125s。（128K 慢可接受，因 agent 不应反复 cold-prefill 128K；关键在 prefix cache。）
>
> **4) Prefix cache（最重要）**：同一 conversation 首次 cold，然后连续追加 1–4K tokens。须**同时报告**：`request cache-hit rate`、`reused-prefix tokens / total-prefix tokens`、device-hit TTFT、host-hit TTFT、cold TTFT。
> - 第二轮起 **request cache hit ≥95%**；reused-prefix ratio **PASS ≥90% / GOOD ≥95%**。
> - TTFT：**Device checkpoint hit ≤1.0s**；**Host resume 32K ≤2s**；**Host resume 128K ≤5s**。
> - ⇒ **32K/128K hot TTFT 若仍是十几/几十秒 = 不合格**（买 V100 的核心前提就是 agent loop 靠 prefix reuse 免重复 prefill）。
>
> **5) 并行度**：生产默认 **`max-concurrency = 1`**（架构是"4×V100 → 4 个独立服务"，不是单卡服务 8 agent）。
> 测 **C=1/2/4**：C1=latency baseline；**C2** aggregate decode ≥**1.35×C1**、无 OOM、单请求 decode ≥C1 的 **65%**；**C4 仅测能力，非生产硬门槛**（aggregate ≥1.6×C1 才有实际价值）。
>
> **6) 稳定性 soak**：**60 min 连续 agent-style、≥100 requests**；要求 **OOM=0 / CUDA error=0 / crash=0 / invalid response=0**；**P95 decode TPS 退化 <15%**；**不得持续 throttling**。
>
> **最终核心判据（买卡线）**：**32K ≥50 tok/s；128K ≥35 tok/s；MTP acceptance ≥60%；hot-prefix TTFT ≤1s(device)；实际 agent loop prefix reuse ≥90%；C1 连续运行稳定。**
>
> **测量纪律（orchestrator 补充，binding）**：
> - 延迟敏感指标（TTFT/prefix hit）**必须在 V100 loopback 上测**，避免 SSH 隧道开销污染；跨主机行为另测并注明。
> - 必须先用**仓库/服务实际暴露的字段**确定每个指标怎么算（`timings.{cache_n,prompt_n,draft_n,draft_n_accepted}` 等），**不得编造**。
> - 默认配置若 K=3/4 acceptance <50% ⇒ 须明确报"默认配置建议改"，但**不得擅自改**。

> ### 🔬 Gate 可测性已取证（`ACCEPT-GATE-RECON-R2`，binding 测量口径）
> **直接暴露（HTTP `/v1/chat/completions`）**：
> - `timings.cache_n` = **复用前缀 token 数**；`timings.prompt_n` = **新 prefill token 数**；`cache_n + prompt_n = prompt_tokens`
>   ⇒ **reused-prefix ratio = `cache_n / prompt_tokens`**；**request cache-hit** 可由 `cache_n>0`/比例判定。
> - `usage.prompt_tokens_details.cached_tokens`（= `cache_n`）；`draft_n` / `draft_n_accepted`（仅 `draft_n≠0` 时出现）。
> - `timings.prompt_ms` = **`prompt_wall_seconds`**（**admission commit → 首 token**）= **TTFT 的 lower bound**（不含排队/到达）。
> - **无 `/metrics`、无 stats endpoint**；服务端只有 `/health`、`/v1/models`、OpenAI 端点。
>
> **不在 HTTP 响应中（须走 JSONL / 自测）**：
> - **`rounds` 不在 HTTP `timings` 里** ⇒ `mean committed tokens/round = 1.0 + accepted_tokens/rounds`（仓库 canonical `acceptance_length`）须从 **JSONL `request_done`**（`speculative.rounds`）或 bench tooling 取。**注意：此前 BENCH-ABCD artifact 里把 `draft_n_accepted/draft_n` 当作 mean-accepted/round 是错的，须纠正。**
> - **真 TTFT** 不在 HTTP 响应：**客户端必须自测 wall clock**（`t0`=写首字节前，`t1`=首个非空 model/reasoning/tool delta）；服务端 `ttft` 仅在 JSONL `request_done`。
> - **Device vs Host 复用无 per-request 区分字段** ⇒ 只能**受控配置**隔离：`--host-state-slots 0 --host-kv-mib 0`（device-hit baseline）vs `--device-state-slots 0`（host-resume baseline），比 TTFT。仓库 `tools/bench/ttft/` 已有对应 profiles（`cache-pressure-device` / `cache-pressure-state-host`）。
> - 服务器级缓存/搬运计数器（`context_cache.*`、`state_{d2h,h2d,d2d}`、`main_kv_*`）仅在 **JSONL/operational log** 聚合，非 per-request。

**当前状态**：**生成 24/24 完成**；评分 92% 进行中；`ninfer-serve` 已转空闲（预期，评分在本地跑）。

> ### ⏳ 长尾说明（供后续判断，非故障）
> 第 24 例 `sympy__sympy-22456` 是**长实例**：每步 prompt ≈ **95k token**、~14s/请求、`step_limit=250` ⇒ 单实例可能耗时**数十分钟**。
> ⇒ 23/24 停留**属正常**；判"挂死"的唯一有效信号 = **服务端 `req#` 连续 N 分钟不前进**（当前**明确在前进**）。**禁止 kill**（会丢弃在飞工作）。

**当前状态小结**：`ninfer-serve` 在 V100 上 **UP**（`0.0.0.0:8080`，经本地 SSH 隧道对 harness 可达）；SWE-bench blind24 **23/24 完成**，最后 1 例推进中；**脱离终端的 autoscore wrapper 正在等待并无条件接续评分**。**未改任何 runtime/源码/系统依赖**。

> ### 🧠 方法论修正（第 2 次教训，**binding**）
> 三次"等它跑完"式派单**全部空回件/stub**（`SWE-EVAL-FULL-RUN`、`SWE-EVAL-COMPLETE-SCORE`、`SWE-MONITOR-SCORE-R2`）。
> **根因**：把**长时等待**放在 agent invocation 内 ⇒ invocation 被切断，工作丢失。
> **修正（已采用）**：把等待与后续动作**下沉为 harness VM 上的脱离终端 shell 脚本**（`nohup`），
> agent 只负责**短命令读状态**。⇒ 等待发生在**远端**，不受 agent 生命周期影响。

> ### 📌 方法论教训（登记）：**长时监控任务连续两次空回件**
> `SWE-EVAL-FULL-RUN` / `SWE-EVAL-COMPLETE-SCORE` 两次 invocation 均空回件、零落盘。
> **根因推断**：要求在单个 invocation 内"等到跑完"（长时等待/长 SSH 前台）⇒ 被超时切断。
> **改用**：**有界轮询**（每次 ≤6 条短命令 + bounded sleep，指定总预算），未完成就**如实报进度并停止**，由 orchestrator 下一轮续派。这符合"不要用长前台命令"的既有教训。

> ### 🔴 BLOCKER-5 已解除（端到端通路已证）
> `swe-harness-901` → `http://192.168.20.250:8080/v1` → 本地 SSH 隧道 → V100 `ninfer-serve:8080`。
> ⚠️ **隧道非持久**（本地 ssh 进程死亡即断）：重连命令已记录于 `NET-BRIDGE-HARNESS-V100-20260919.md`。
> ⚠️ **观测到的模型行为**：`max_tokens=32` 时 32 token **全被 reasoning 占用**，`content` 为空、`finish_reason=length`（与 M2 历史上"thinking 吃光预算"同型）。harness 自身 frozen policy 为 `reasoning_effort: medium` ⇒ 运行中须留意此现象是否影响 SWE agent 解题；**不得擅自改 policy**，只如实报告。

> ### 🔴 BLOCKER-5（集成）：**harness VM 与 V100 网络不可互达**
> V100 在云实例内网 **`172.17.0.2`**（容器 bridge）；harness VM `192.168.20.203` 与 V100 **互 ping 100% 丢包 / 22 端口不可达**。
> owner 已给出平台规范：**V100 的 8080 经"自定义服务"暴露到公网**；harness 配置面支持 `SWE_API_BASE` 覆盖 ⇒ 需先确定**可达的 endpoint**。
> **候选通路**：(a) 平台公网 URL / `i-1.gpushare.com:8080`；(b) **SSH 隧道**：本机（`192.168.20.250`，持有 V100 免密私钥，与 harness 同 `/24`）执行
> `ssh -N -L 0.0.0.0:8080:127.0.0.1:8080 gpushare-v100` ⇒ harness 用 `http://192.168.20.250:8080/v1`。
> **优先取证 (a)，失败则用 (b)**；两条路都属**临时网络桥接**，不改系统环境、不改 runtime。

> ### ✅ BLOCKER-4 已解除（2026-09-19）—— 解法 = **使用模型仓历史中的 rev2 artifact**
> 本地 fork 自带 model card 记载该 artifact 为 `container_version: 2`；HF 仓 git 历史中的 rev2 commit：
> **`3b84117e0fd258b45bd79778ec8d8f27a4ab3d56`**（2026-08-17）⇒ 下载 21,492,695,040 B，
> SHA256 `bb336052…d81b32`，**前 8 字节 `NINFER\0\2`** ⇒ 与本机构建的 V100 二进制兼容。
> **未修改任何 runtime 源码**，未改系统环境。原 rev3 文件（不可用）已删除。

> ### 🔑 BLOCKER-4 突破证据（orchestrator 于本地 fork 中查得，**调查任务漏掉**）
> `ninfer-v100` **仓库自带的** model card（`model-cards/Qwen3.8-27B-nvfp4-NInfer/artifact-manifest.json` @ `b37d0dd3`）明确记载：
> - **`"container_version": 2`**  ← **rev2！**
> - `"recipe_id": "qwen3_8_27b_nvfp4-v2"`
> - `artifact-manifest.json` 内 `minimum_revision: 385b30ce…`（**≠** 当前 HF `main` 的 `98dada0e`）
>
> 而 `README.md`（fork 内 model card）L130：`| Container version | 2 |`；L3（fork 顶层 README）：**"Up to 219 decode tok/s from Qwen 3.8 27B on a single V100. With software NVFP4 on Volta."**
> ⇒ **V100 fork 是能跑这个模型 NVFP4 的**（`docs/v100.md` 亦有实测数据）。
> ⇒ **HF 仓 `main` 已被 v2→v3 覆盖，但 git 历史里应仍存有 rev2 artifact** ⇒ 按 **revision SHA 下载旧版**即可对齐。
> ⚠️ 磁盘：现 v3 artifact 23.7GB 占位，`/hy-tmp` 仅余 ~14GB ⇒ 取旧版前需先判体积；**只删已证不可用的 v3 文件**（owner 已授权全量使用数据盘；不足则报 owner 扩容）。

> ### 🧱 BLOCKER-4（**真阻断，可解**）：`.ninfer` 容器 framing 版本不匹配
> **证据**：`src/artifact/reader.cpp:28` 硬编码 `kMagic = "NINFER\0\2"`；`reader.cpp:274` 抛 `artifact magic is not NInfer v2`。
> 本地 `docs/maintainer/artifact-container.md`（@ HTML `b37d0dd3`）**只定义 version 2**（L59 明确 magic `4e 49 4e 46 45 52 00 02`）。
> 下载的模型文件前 8 字节 = `4e 49 4e 46 45 52 00 03` ⇒ **revision 3**。
> ⇒ 说明**模型仓 `neroued/Qwen3.8-27B-nvfp4-NInfer` 已更新为 rev3 容器**，而我们的 `b37d0dd3` 只认 rev2。
> **候选消除路径**（须先取证，勿擅动）：
> (a) 上游 `master` 在 `b37d0dd3` 之后**是否有支持 rev3 的提交**（本机可达 GitHub ⇒ 可查）；
> (b) 模型仓是否提供**兼容 rev2 的旧版 artifact** 或明确标注所需 NInfer 版本；
> (c) 若必须改 `src/artifact/reader.cpp` ⇒ **属 runtime 改动，须 owner 明示授权**（且优于改 runtime 的是换匹配的上游 commit）。
> ⚠️ 上游文档明言"Project-owned formats have no compatibility obligation"，**不存在格式兼容义务** ⇒ 版本对齐是正常运维，不属"runtime 被破坏"。

**⚠️ 已知非阻断缺陷（登记）**：`tests/ninfer_cli_options_test` 链接失败（`undefined reference to ninfer::product::parse_log_level`）。**仅测试二进制**；三个 app 目标均构建成功 ⇒ 不影响本 Goal（benchmark 只用 app 目标）。**不修**（属 runtime/测试改动，超出授权范围）。

**⏸ 待 owner 决策（MATERIAL USER DECISION — 依赖路线）** ➜ ✅ **已裁定：路线 A**（2026-09-19）
- **owner 决定**：**A** —— 最干净、最低风险；**不改源码**，**不碰系统依赖**。
- **同时要求回滚** `/usr/local/cuda` 的意外改动（后续一律用绝对路径 `/hy-tmp/cuda-12.8/bin/nvcc`）。
- **硬约束**：禁止 `apt upgrade`；禁止改系统 FFmpeg/libcurl；**禁止改 `CMakeLists.txt`**。
- **conda env**：`/hy-tmp/ninfer-deps`，仅装 `ffmpeg=6.*`、`pkg-config`、`libcurl>=7.85`（`--override-channels -c conda-forge`）。
- **门禁**：`pkg-config --modversion` 五项须满足 libavformat≥60 / libavcodec≥60 / libavutil≥58 / libswscale≥7 / libcurl≥7.85，**否则 STOP**。
- **构建**：保持离线 CUTLASS mediation（`-DFETCHCONTENT_SOURCE_DIR_CUTLASS=… -DFETCHCONTENT_FULLY_DISCONNECTED=ON`），**不新增源码改动**。
- **build 后**：`ldd build-v100/apps/ninfer-serve | grep -E 'not found|avformat|avcodec|avutil|swscale|curl'`，任何 `not found` ⇒ **STOP**。
- **磁盘处置（owner 授权）**：CUDA 12.8 验证正常后删 `cuda_12.8*.run`；conda env 建好后 `conda clean -a -y`；保证构建前 **≥12–15GB** 可用。
- **范围**：**不再扩大**。真正的不确定性已从"能否构建"收敛为"**V100 上 Qwen3.8 实际性能**"。
| `FORK-REPO-20260919` | devops-executor | ✅ **DONE**：fork `charleslai2000/ninfer-v100` 已存在且可 `ls-remote`；`origin`=fork、`upstream`=geoffwatts；fork HEAD **SAME**=`b37d0dd3…` | 副本 ✅ | `agents/FORK-REPO-20260919.md` |

**DECISION（orchestrator，2026-09-19）**：本地机 = RTX 3090 24GiB + CUDA 12.9 + 4.6GiB 空闲 ⇒ **不是本 Goal 的目标机**，且其 GPU 正被现役 sglang 生产进程占用 ⇒ **本地一律不跑 GPU 工作负载、不装驱动/CUDA、不动其进程**。目标机 = 用户提供的远端 `i-1.gpushare.com:53003`（owner 已授权配置免密登录）。

> ### 🔒 OWNER BINDING DECISION（2026-09-19，镜像与工具链路线）
> 1. **选定镜像**：远端 **V100 32G + CUDA 12.4.1（PyTorch 2.5.1 / Python 3.11）预装镜像**，**直接采用**；该镜像**不构成阻碍**。
> 2. **保留现有驱动**：**不卸载 CUDA 12.4、不换/升级 NVIDIA driver**。`nvidia-smi` 里的 `CUDA Version: xx.x` = **驱动支持的最高 runtime**，**不是**已装 Toolkit 版本；编译器版本只看 `nvcc --version`。
> 3. **构建工具链**：另**额外安装 CUDA Toolkit 12.8**，构建时显式指定 `-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc`（依据 `docs/v100.md`）。
> 4. **🛑 硬禁令**：**不允许任何 agent 自行乱升级 CUDA 或 driver**。安装 CUDA 12.8 的**具体指令必须等 owner 在看到 §"第一步输出" 后再下达**；在此之前只做只读采集。
> 5. **第一步输出清单（必须先回给 owner）**：`nvidia-smi`、`nvcc --version`、`cat /etc/os-release`、`gcc --version`、`cmake --version`、`free -h`、`df -h`，另加 `nvidia-smi --query-gpu=name,memory.total,driver_version,pstate,power.limit --format=csv`。
> 6. **判据**：CUDA 12.x minor-version compatibility 最低驱动要求 525.60.13 —— **启动后据实核验该云机是否满足**。
> 7. **canonical 参考**：`geoffwatts/ninfer-v100` 的 `docs/v100.md`（官方 V100 路线）。

> ### 🔱 OWNER DECISION（2026-09-19，fork 策略；binding）
> 必须 **fork** 上游 repo（**不要**只用只读上游 clone），以防后续可能需要修改。
> - Fork 目标账号：**`charleslai2000`**（GitHub）。
> - 本机已配置 **SSH 免密**（优先走 `git@github.com` over SSH，而非 HTTPS/token）。
> - 本地工作副本 `origin` ⇒ **fork**；上游 `geoffwatts/ninfer-v100` 保留为 **`upstream`** remote（只读参考）。
> - 目标：`charleslai2000/ninfer-v100` 存在且本地 `origin` 指向它；fork 与 upstream HEAD 的 SHA 关系已记录。
> - 🛑 仍然**不修改** inference runtime 源码；fork 仅为"可能需要修改"预留合法写面。
> - ⚠️ 本机 `/` 仅 ≈4.6GiB 空闲 ⇒ 克隆**不得**引入大文件/LFS 负载；若出现体积风险，先报 blocker。

> ### 🖥️ OWNER-SUPPLIED TARGET MACHINE SPEC（2026-09-19；待远端实测复核）
> | 项 | owner 给定值 |
> |---|---|
> | GPU | **V100-32G × 1**，显存 **32 GB** |
> | CPU | Intel Xeon Gold 6138，**10 核** |
> | 实例内存 | **93 G** |
> | 系统盘 | **20 G** |
> | 数据盘 | **50 GB NVMe** |
> | 带宽 | 上行 800 Mbps / 下行 800 Mbps |
> | **最高 CUDA 版本** | **12.4**（= 驱动可支持的最高 runtime） |
> | **显卡驱动版本** | **550.163.01** |
> | 机器 ID | `MACHoR4YE8ZDLyWmuwim4lBJ` |
> | 计费 | ￥0.79/小时（不可用代金券） |
>
> **orchestrator 预判（待实测复核，不得当作已证事实）**：
> - 驱动 `550.163.01` **≥ 525.60.13** ⇒ **CUDA 12.x minor-version compatibility 判据满足** ⇒ CUDA **12.8** toolkit 可在此驱动下运行（需实测确认）。
> - **磁盘是本 Goal 的已知高风险点**：模型 + 构建树必须落在 **50GB 数据盘**；`/`（系统盘 20G）容量紧。需实测 `df` 与模型实际体积后再定，否则可能触发 blocker。
> - 远端的 `nvcc` / toolkit 现状**未知**（owner 说"最高 CUDA 12.4"指驱动能力，不等于已装 toolkit）。

> ### 💾 OWNER 明确：**数据盘可用**（2026-09-19）
> owner 确认 **50GB NVMe 数据盘可以提供/使用**。⇒ 模型 `.ninfer` 与构建树**一律落在数据盘**，不得占用系统盘（`/` 20G）。
> 待实测：数据盘的**实际挂载点**与**可用容量**（由 `REMOTE-ENV-CAPTURE-20260919` 采集；若未挂载 ⇒ 需 owner 指示挂载方式后再下载模型）。

> ### 💾 OWNER 追加授权（2026-09-19，**capacity binding**）
> **数据盘可全量使用**（实测挂载点 = **`/hy-tmp`**，50G NVMe，当前 0% 使用）。
> 若空间不足，**owner 可扩容**。⇒ 不因磁盘余量对 build tree / 模型 / CUTLASS 缓存做妥协；容量不足时**报 owner 扩容**，而非降级方案。

> ### 🌐 远端网络约束（实测，binding 事实）
> | 目标 | 可达性 | 证据 |
> |---|---|---|
> | `github.com` HTTPS | ❌ **不可达**（curl exit 28；无 proxy） | `REMOTE-NET-PROBE` |
> | `huggingface.co` | ❌ 不可达（超时） | 同上 |
> | **`hf-mirror.com`** | ✅ **HTTP/2 200** | 同上 |
> | PyPI | ✅ 可达（`pip index versions` 成功） | 同上 |
> | apt 源 | 华为云镜像 + USTC + **`developer.download.nvidia.cn`**（CUDA repo） | 同上 |
>
> **后果**：① 仓库构建期 `FetchContent` 从 **GitHub 拉 CUTLASS v4.4.2** ⇒ **在目标机上会失败** ⇒ 需经镜像/本机中介；② 模型走 **hf-mirror.com**；③ ⚠️ **`apt-get -s` 模拟成功不等于网络可达**（`-s` 只读本地包索引）——须单独实测源可达性（已派 `TOOLCHAIN-SOURCE-FEASIBILITY-20260919`）。

> ### 🧱 BLOCKER-1（FORK）：**已解除**（2026-09-19）
> owner 已在网页创建 fork ⇒ `git ls-remote git@github.com:charleslai2000/ninfer-v100.git` 返回 `b37d0dd3…`（`HEAD` 与 `refs/heads/master` 同 SHA）。`origin`=fork 已 `fetch` 成功、`upstream`=geoffwatts、本地 `master` 跟踪 `origin/master`。fork 与 upstream HEAD **SAME**。可推送面已具备（尚未推送）。

> ### 🧱 BLOCKER-2（BUILD 前置，**待 owner 指令**）：远端工具链缺件
> 远端实测（`REMOTE-ENV-CAPTURE-20260919`）：
> | 需求 | 远端现状 | 判定 |
> |---|---|---|
> | 驱动 `550.163.01` | 装了，**> 525.60.13** | ✅ 满足 CUDA 12.x minor-version compatibility |
> | **CUDA Toolkit 12.8** | **只有 12.4**（`/usr/local/cuda-12.4/bin/nvcc` V12.4.131）；`/usr/local/cuda-12.8` **不存在** | ❌ **缺**；`CMakeLists.txt` L75–78 硬性要求 ≥12.8 |
> | CMake | **3.22.1** | ❌ **低于 `cmake_minimum_required(VERSION 3.28)`**（顶层 `CMakeLists.txt` L1） |
> | Ninja | **未安装** | ❌ 缺（构建命令用 `-G Ninja`） |
> | gcc | 11.4.0 | ✅ |
> | GPU 空闲 | `No running processes found` | ✅ 可独占 |
>
> **处置边界（owner binding）**：CUDA 12.8 的**确切安装指令必须由 owner 下达**；agent **不得自行升级 CUDA/driver**。cmake（3.28+）与 ninja 同属**安装动作** ⇒ 一并等 owner 指令（可走 apt / pip / 源码，需 owner 选路径）。
> **已定路由**：构建树与模型**一律落 `/hy-tmp`（50G NVMe 数据盘）**，不用根 overlay（30G）。

> ### ✅ OWNER 授权 + 精确安装配方（2026-09-19，**binding，已获准执行**）
> **隔离原则**：**不动现有 driver、不动 CUDA 12.4**；**CUDA 12.8 / CMake / Ninja / 源码 / build / 模型全部落 `/hy-tmp`**。
> 设备 = **`Tesla V100-SXM2-32GB`**（优于公开 PCIe-32G 测试机；同方法 SXM2 每轮快约 6–7%，且上游专供 `tools/v100/ninfer-sxm2.sh`）。
>
> **步骤 0（前置检查）**：`findmnt -no TARGET,OPTIONS /hy-tmp` —— 若 `noexec` ⇒ **STOP 报告**。然后 `mkdir -p /hy-tmp/{installers,tmp,cuda-12.8}`。
>
> **步骤 1（CUDA 12.8 runfile，toolkit-only，绝不装 driver）**：
> ```
> cd /hy-tmp/installers
> curl -fL -o cuda_12.8.0_570.86.10_linux.run \
>   https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/cuda_12.8.0_570.86.10_linux.run
> chmod +x cuda_12.8.0_570.86.10_linux.run
> ./cuda_12.8.0_570.86.10_linux.run --silent --toolkit \
>   --toolkitpath=/hy-tmp/cuda-12.8 --tmpdir=/hy-tmp/tmp
> ```
> ⚠️ 该 URL 主机为 `developer.download.nvidia.com`（**非** `.cn`）；`TOOLCHAIN-SOURCE-FEASIBILITY` 只证了 `developer.download.nvidia.cn` 可达 ⇒ **须实测该主机可达性**，不通则报 blocker（备选：cdimage/镜像或本机中介）。
>
> **步骤 2（CMake/Ninja 隔离 venv）**：`python3 -m venv /hy-tmp/ninfer-tools`；`pip install -U pip`；`pip install 'cmake>=3.28,<4' ninja`。
>
> **步骤 3（固定环境）**：写 `/hy-tmp/ninfer-env.sh`：
> `CUDA_HOME=/hy-tmp/cuda-12.8`、`CUDACXX=/hy-tmp/cuda-12.8/bin/nvcc`、`PATH` 前置 `/hy-tmp/ninfer-tools/bin:/hy-tmp/cuda-12.8/bin`、`LD_LIBRARY_PATH` 前置 `/hy-tmp/cuda-12.8/lib64`、`TMPDIR=/hy-tmp/tmp`。
>
> **步骤 4（依赖门禁 —— owner 新发现，build 前必须过）**：
> `g++ --version`；`pkg-config --version`；
> `pkg-config --modversion libavformat`（≥60）、`libavcodec`（≥60）、`libavutil`（≥58）、`libswscale`（≥7）、`libcurl`（≥7.85）。
> **若 FFmpeg/libcurl 版本不足 ⇒ STOP，不得自行乱装**（Ubuntu 22.04 默认很可能不够；由 owner 决定 Conda 隔离 或 Ubuntu 24.04 CUDA-12.8 容器）。
>
> **步骤 5（仅在步骤 4 全过时 build）**：
> `cmake -S . -B build-v100 -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_COMPILER=/hy-tmp/cuda-12.8/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=70`；`cmake --build build-v100 -j`。
>
> **通用禁令**：GitHub/HF/NVIDIA/PyPI 哪个不通就**报哪个**，**不得为网络问题改系统环境**；**不要扩范围**。

> ### 🧱 BLOCKER-3（BUILD 依赖）：**CUTLASS v4.4.2 必须本机中介**
> 仓库顶层 `CMakeLists.txt` 用 `FetchContent_Declare(cutlass GIT_REPOSITORY https://github.com/nvidia/cutlass.git GIT_TAG v4.4.2)`；而**目标机 GitHub HTTPS 不可达**且无可用镜像（ghproxy 403 / nuaa 超时 / gitclone 404 / gitee 无镜像）。
> **本机可达 github.com** ⇒ 需 **本机 fetch CUTLASS v4.4.2 → 经 SSH 传到 `/hy-tmp` → 让 CMake 用本地副本**（`FETCHCONTENT_SOURCE_DIR_CUTLASS` 或等价 mechanism）。这是 build 的前置，非 runtime 改动。

> ### 📄 上游 canonical 事实（`docs/v100.md`，已本地读核）
> - `sm_70` 构建是 **peer 实现**，支持全部五个注册 artifact + Text/Vision/MTP/prefix-reuse/CLI/OpenAI+Anthropic 协议面。
> - **NVFP4 与 K8V4 KV 存储 Volta 上不可用**（L44）⇒ 用 **INT8 group-64 KV**（与 owner 步骤一致）。
> - MTP 接受 **1–7** draft positions；**K=3 是真实文本的生产甜点**（L95）。
> - V100-PCIe-32GB 实测（CUDA 12.8 + INT8 KV）：Qwen3.8-27B `nvfp4` MTP **K=5 → 199.58 tok/s / 97.1%**；K=1 → 218.98 / 99.2%。
> - **SXM2 优先**：`NINFER_GPU_UUID=<uuid> tools/v100/ninfer-sxm2.sh --help`（launcher 会校验设备确为 SXM2-32GB）；`NINFER_EXECUTABLE` 可指到别处的二进制。
> - Qwen3.8-27B serving 建议 `--prefill-chunk 2048`（SXM2 8K prefill 1137.0 vs 1024-default 1078.6，+5.4%）。
> - 本 Goal 的 benchmark 规格（A/B/C/D × 2K/8K/32K/128K）与上游已发布的 varied-context sweep（2K–150K）**同形**，可作交叉核对基线（L111–117）。

**READY**
| necessary frontier item | role | deps |
|---|---|---|
| （待 ENV/REPO 回件后重算） | — | ENV-CAPTURE-20260919, REPO-ACQUIRE-RECON-20260919 |

**BLOCKED**
| item | blocker | unblock condition |
|---|---|---|
| 模型下载（`qwen3_8_27b_nvfp4.ninfer`）+ 全部构建/benchmark | 依赖 ENV 前提与磁盘余量 | ENV-CAPTURE 回件确认 GPU/CUDA12.8/磁盘；REPO 回件确认获取面 |

**INTEGRATED**
（无）

**NEXT**
1. 等 `REMOTE-ENV-CAPTURE-20260919` 终态 artifact ⇒ **把 OWNER-FACING 第一步输出原样交 owner**；
2. 依该输出复核：GPU=V100 32G / sm_70、驱动 `550.163.01` ≥525.60.13、**数据盘挂载点与可用容量**、远端是否已有 `nvcc`/toolkit；
3. 复核通过后 ⇒ 请 owner 下达 **CUDA 12.8 toolkit 安装指令**（agent 不得自行安装/升级 CUDA 或 driver）；
4. 模型获取（`neroued/Qwen3.8-27B-nvfp4-NInfer` → `qwen3_8_27b_nvfp4.ninfer` + SHA256 校验）落在**数据盘**；
5. 构建 `-DCMAKE_CUDA_ARCHITECTURES=70` + CUDA 12.8（**不跑 CUDA13 Dockerfile**）；若 TMA NVFP4 汇编失败 ⇒ 报 blocker，不擅自改 runtime。

**开包风险登记（供复核，非结论）**
- `ninfer_nvfp4_non_rdc` 无条件编译 `nvfp4_w4a4_tma.cu` / `nvfp4_linear_swiglu_w4a4_tma.cu`（TMA=sm_90+）⇒ 可能在 sm_70 ptxas 阶段失败（`src/CMakeLists.txt` L53–65）。属**构建期**问题，须实测。
- 本地 `/` 仅 4.6GiB ⇒ **本地只做 clone/构建编排，不落模型、不落 build tree**。

---
