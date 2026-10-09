# G3/MMQ 接续说明（2026-09-07 收尾 → 下一会话）

时间：2026-09-07（orchestrator 会话按用户要求停止，写本交接）。
工作区：`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s`
任务总线：`.memory/g3-baseline-20260907/`（`ledger.md` 为 append-only 权威账本；`work/*.md` 为各任务报告/证据）。
上一交接：仓库根 `CODEX_HANDOFF.md`（codex→claude，2026-09-06）；本文件在其后接管推进后收尾。

## 1. 目标（不变）

G3/MMQ：在**未优化** IQ3_S v1 服务上保存基线（Profile A = 生产 C1/C4/C5；Profile B = 临时 true-C16 C1/C4/C8/C16 + prefill），隔离实现 I-quant MMQ，再用**逐字节相同**的 profile/命令/runner 复测，报告 delta。AGENTS.md 为冻结边界权威。

## 2. 环境与访问（无秘密入文件）

- 实验主机：`root@175.155.64.171` SSH 端口 `22109`，本机 key `/home/dev-codex/.ssh/id_ed25519`（passwordless，已验证）。
- v1 服务：PID **298123**，`http://127.0.0.1:8035`，served model `/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`。冻结启动参数见 AGENTS.md + `work/preflight.stdout`（kv fp8_e4m3、mamba extra_buffer_lazy、reasoning-parser auto、tool-call-parser qwen3_coder、preserve_thinking false）。cmdline sha256 = `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`。
- 远端环境：python `/data/sglang-qwen35-env/bin/python`（3.12.0）；runner 源码 `/data/sglang-qwen35/python`（sglang 0.5.10.dev0，**归档无 git**）；服务日志 `/data/sglang-qwen35/exp_server_j1_v1.log`。
- 基线产物目录：`/data/qwen3-g3-baseline/`。
- 本地仓库：分支 `sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`，HEAD `dac6db1e`；5 个故意 P1 修改文件；本地 `/python` 与远端归档内容同源（以远端为准，改前先 diff）。
- `/metrics`、pmon 进程归因均不可用；遥测用 `/v1/loads?include=all` + `nvidia-smi dmon -s pucvmt -d 1` + 前后 query。

## 3. 已冻结决策（D 系列，勿重开）

- E2 协议：Profile A 生产 C1/C4/C5（prompts 20/40/50，ISL2048/OSL512）；Profile B 性能 C1/C4/C8/C16。
- D1：合成固定长度 workload 用 `--random-range-ratio 1.0`；每个 manifest 记 `compat_note: requested fixed-length workload; current runner requires random_range_ratio=1.0`（本 checkout 不许 ratio 0）。
- D2：核心 MMQ 不依赖/不隐式下载 ShareGPT；ShareGPT 是独立 pinned realistic 层，排除在 MMQ PASS/FAIL 外。
- D3：B-prefill = C1/20 prompts/2K·8K·32K ×32 out ×3；每轮 RadixCache flush；B 准入 = 观测 `max_running_requests ≥ 16`（非客户端计数）。
- **D4**：`--dataset-name random` 在本 fork 会隐式下载 ShareGPT（离线不可绑定）→ 核心绑定 **`random-ids --tokenize-prompt`**（seed 42，raw input_ids 精确 2048），manifest 加 `dataset_compat_note`（内容=均匀随机整数 token，非 ShareGPT 采样）。
- **D5**：OOM 修复采用 runner 源码补丁（见 §5），命令保持逐字节不变。

## 4. 已完成 / 状态一览（详见 `work/*.md`）

| 任务 | 状态 | 要点 |
|---|---|---|
| G3-CAP-PROBE-20260907 | done | 执行通道可用；远端可达；服务健康 |
| G3-RUNBOOK-A-20260907（含 v2） | done | 冻结 9 命令、manifest、聚合、审查清单；random-ids+--tokenize-prompt 最终绑定 |
| G3-PRODUCTION-A-EXEC-20260907 | **blocked** | 见 §5 OOM；RUN_ID prod-a-20260907-105255（HALTED.txt 全证据） |
| G3-RUNNER-OOM-DIAG-20260907 | done | 根因确凿：check_chat_template 把 11.77GB GGUF 当 JSON 整读 → 42.6GB OOM |
| G3-RUNNER-OOM-FIX-20260907 | **in-flight → 会话停止可能中断** | 见 §6，续接第一步核对 |
| ledger.md | append-only | 含 D1–D5 全文与每次派发/核验记录 |

## 5. 阻断：Production-A 无法测量的根因（已确证）

- runner 启动即 OOM：`serving.py:2058 check_chat_template(args.model)` → `AutoTokenizer.from_pretrained(<GGUF>, trust_remote_code=True)` → transformers 5.12.1 把 GGUF 当 JSON config **整文件缓冲预读**（readlog `size=11771546784`）→ anon RSS ~42.6GB（48GB 主机、0 swap）→ rc=137，早于任何 `/generate`。
- 与 flag 无关（三种调用同签名）。分词器获取路径本身 GGUF-aware、内存小（1.33GB 实证）。
- `check_chat_template` 返回值**仅决定一条建议性警告**是否打印，对测量零影响 → 打补丁安全。
- 该环境下 `-m sglang.benchmark.serving` **从未成功跑过**（含历史 T100230Z/T101034Z 两次 halt）。

## 6. 续接第一步（关键）：settle G3-RUNNER-OOM-FIX

coder 任务（本地 + 远端补丁、内存封顶 verify、diff/sha 记录）在会话停止时被 kill。其最后消息称**补丁与验证均已全部完成、仅差写入报告文件**；但 `work/G3-RUNNER-OOM-FIX-20260907.md` 报告可能不存在或不完整——**以双端文件实际 diff/行为为准，勿信消息**。续接先：
1. diff 远端 `/data/sglang-qwen35/python/sglang/benchmark/serving.py` vs 本地 `/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/python/sglang/benchmark/serving.py` 的 `check_chat_template` 区域与整体；
2. 若补丁未落地/半落地：在两处施加**同一**最小补丁——model path 以 `.gguf` 结尾时，不把它交给普通 `AutoTokenizer.from_pretrained`（有 sidecar 目录则改为加载父目录 `tokenizer_config.json/tokenizer.json`；否则快速返回 advisory False，不读 GGUF）；保留原 try/except 与错误打印；
3. 内存封顶验证（`ulimit -v` ≤8GB）下调用补丁后函数对真 GGUF 快速返回（RSS <2GB）；`python -c "import sglang.benchmark.serving"` exit 0；
4. 记录 diff + 双端 sha256 到 `/data/qwen3-g3-baseline/g3-runner-oom-fix-20260907/`。
5. 若 G3-RUNNER-OOM-FIX 已 done：直接核对其报告 `work/G3-RUNNER-OOM-FIX-20260907.md` 即可。

## 7. 后续步骤（顺序执行，勿跳）

1. （§6）修复落地并验证后：**fresh RUN_ID** 派 devops-executor 重跑 Production-A（runbook v2 最终命令：`--backend sglang --base-url http://127.0.0.1:8035 --model <GGUF> --dataset-name random-ids --tokenize-prompt --random-input-len 2048 --random-output-len 512 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency C --num-prompts N --output-details --flush-cache --flush-cache-timeout 60 --warmup-requests 3`，C/N=1/20,4/40,5/50 ×3 reps；**禁 `--tokenizer`、禁 `--tag`**；产物 `/data/qwen3-g3-baseline/prod-a/<RUN_ID>/`；每点/每 rep warmup→flush→measure；invarian-gate 失败即 HALTED.txt + rc74）。
2. reviewer 独立核验：服务字节不变（cmdline sha256 7832781e…）、9 命令逐字节=runbook §8、artifact 完整、`recompute.py` 中位数可复现、`max_running==C`。
3. Profile B：需**独占 GPU 切换授权 + 自身 runbook**（临时 true-C16 server，port 另选，≥64 Mamba slots、~33024 tokens、`max_running≥16` 准入）；跑完 B 后还原 v1 服务。
4. MMQ 实现（隔离代码变更，不碰 v1 profile/权重）→ 用**同一 patched runner + 同一命令**复测 B → 报告 delta。
5. 全程保留：真实命令、环境 freeze、patch review；确认后提交实验分支（本地 ledger 在 `.memory`，不进 git）。

## 8. 安全边界（沿用 AGENTS.md / 50-forbidden / 55-network-fetch）

- 只碰 `175.155.64.171:22109`；**不碰 22151 / 24052 / 生产基线**；不改模型、不下 53.8GB BF16、不开 DFlash2/vision/MTP。
- 冻结 v1 profile 逐字节不变（cmdline hash 即证）；杀进程仅限**显式 PID + 先查进程树**（已知孤儿 dmon 已清：340306/338006）。
- runner 补丁只改 `check_chat_template` 的 GGUF 分支，不改 CLI/其它代码；本地与远端必须一致。
- 网络：禁 WebFetch；ShareGPT 任何下载都必须显式授权（URL/版本/SHA-256），runner 隐式下载违反 D2。
- 48GB 主机 0 swap + 常驻服务：任何诊断/复现子进程必须硬内存封顶（≤8GB），**严禁**再跑完整 workload 致整机 OOM。
- 破坏性 git（reset/checkout/stash/force-push）一律不用。

## 9. 关键证据文件索引（均在 `.memory/g3-baseline-20260907/work/`）

- `G3-CAP-PROBE-20260907.md` / `G3-RUNBOOK-A-20260907.md`（含 v2 RESOLUTION）/ `G3-PRODUCTION-A-EXEC-20260907.md`（blocked 报告 + OOM 证据）
- `G3-RUNNER-OOM-DIAG-20260907.md`（根因 + 修复选项）/ `G3-RUNNER-OOM-FIX-20260907.md`（在飞/待核）
- `preflight.stdout`（服务冻结参数快照）/ `c1-smoke.*`（探针） / `G3-BINDINGS-DISCOVERY-20260907.md`、`G3-PERF-PROFILE-DESIGN-20260907.md`（B 容量设计参考，细节有限，B runbook 需重建）
- 远端证据：`/data/qwen3-g3-baseline/prod-a/prod-a-20260907-105255/`（HALTED、dmesg、per-repeat）；`/data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/`（readlog smoking-gun）

## 10. 备注

- 历史决策不重写：`ledger.md` append-only；旧 INVALID/HOLD 状态勿当作最新。
- 本文件与 CODEX_HANDOFF.md 并存；CODEX_HANDOFF 描述 B2/GDN 早期状态，G3 以本文件 + ledger 为准。
