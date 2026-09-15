# HANDOFF 2026-09-14 — LOCAL-PROD-BASELINE-v1（Qwen3.5-9B / RTX 3090）

本文件是当前主线的完整交接文档。前一份交接见 `HANDOFF-20260913.md`；
canonical 决策流水见 `ledger.md`（B0/B1 相关条目约在 7043–7230 行）。

本文替代“口头上下文”，阅读本文即可接手，不需要重新研究代码，也不需要重跑旧实验。

---

## 1. 目标（Goal）

把 pre-v0.5.19 本地 baseline 冻结为 **`LOCAL-PROD-BASELINE-v1`**，让 RTX 3090 使用
**Qwen3.5-9B-w4a16 / GPTQ INT4** 稳定上线，并建立可比较、可优化的**全面性能基线**。

固定顺序（不得插队）：

```
B0 GROUP_COMMIT acceptance
  → B1 9B profile/source reconciliation
  → B2 G1 exact-baseline requalification
  → B3 生产型性能/稳定性 corpus
  → B4 freeze / canary
```

当前进度：**B0 / B1 / B2 已完成；B3 部分完成；P0 telemetry 尚未终审通过 → B4 禁止启动。**

---

## 2. 冻结身份（Identity，任何重跑必须逐字节匹配）

### 2.1 Source

| 项 | 值 |
|---|---|
| repo | `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` |
| HEAD | `993ef8e5c3a6448aff2e752cf66cc45deadab59a` |
| git tree object | `75d8d1af8dfef5680085e67767c670554d7163af` |
| canonical tree manifest SHA256 | `5fe5a694a628867ee6c5a7be10a7dfa5dd854501e9c2b75e475c24b6a033f338` |
| branch | `3060-12g-qwen35-4b`（历史命名，不代表模型） |
| protected refs | `refs/heads/3060-12g-qwen35-4b`、`refs/heads/checkpoint/pre-v0.5.19-20260913`、`refs/tags/checkpoint/pre-v0.5.19-20260913` |

注意：canonical tree manifest 的方法是
`sha256(git ls-tree -r HEAD --full-tree bytes)`；它**不等于** git tree object ID，两者必须分开记录。

### 2.2 已授权的 source 变更（production diff）

1. **loader shim（B1-C 关键修复）**
   - 文件：`python/sglang/srt/models/qwen3_5_text.py`
   - SHA256：`22ef63395989e626e7258ae5b8c1f42bfafa8dcc9edd9bfce4989958b78a5352`
   - 内容：在 generic `model.` stripping **之前**处理 `model.language_model.`，修好
     text-wrapper → body-loader 的 prefix 断链。
2. **P0 telemetry（尚未终审通过）**
   - 17-file bounded set，见 `P0-current-correction-packet-17-20260914`。
   - 当前 review 状态：`CHANGES_REQUIRED`（见 §6）。

其它 worktree 变更：`test/registered/unit/mem_cache/test_extent_g1_metadata_unit.py`（test-only overlay）、
`.memory/`（未跟踪）。这两项**不是** loader shim 的一部分，不得随 loader/P0 变更一起提升。

### 2.3 Model

| 项 | 值 |
|---|---|
| HF repo | `mssfj/Qwen3.5-9B-GPTQ-INT4` |
| revision | `d44718f79ab5dd3e46ce546d25168bb7ac6a175e` |
| local path | `/mnt/data/models/local-prod-baseline-v1/qwen35-9b-gptq-int4/` |
| `model.safetensors` SHA256 | `a81fb938ed15819c7e76453fa3e599fa4dee84af75972d3f2aca6b65b11cefaa` |
| `model.safetensors` size | `7,670,240,000` bytes |
| 全仓文件 | 8 files / `7,690,244,644` bytes |
| architecture | `Qwen3_5ForCausalLM` / `qwen3_5_text` |
| quantization | GPTQ v2、4-bit、group size 128、desc_act=false |
| tensors | 1171 = **1170 body**（`model.language_model.*`）+ `lm_head.weight` |

**重要**：不要再去寻找历史 `/root/models/Qwen3.5-9B-w4a16/`；该路径在本机不存在，
canonical 模型就是上面这一份。

### 2.4 Runtime / 环境分层（不要重复安装 Torch/CUDA）

```
/mnt/data/cache/venv          # 共享运行时（唯一）
/mnt/data/cache/pip           # pip 下载缓存（唯一共享来源）
/usr/local/cuda-13.0          # 系统 CUDA toolkit（nvcc 13.0.48）
~/.bashrc                     # 已加入 CUDA_HOME/PATH/CUDACXX/LD_LIBRARY_PATH
```

- `/mnt/data/cache/venv`：Python 3.12.3、`torch 2.13.0+cu130`、CUDA 13.0、
  transformers 5.12.1，并已含 cuDNN/NCCL/cuSPARSELt/NVSHMEM/CUPTI。
- **该 venv 的 SGLang editable finder 指向 27B source（`sglang-qwen3-27b-iq3s`），不是本 baseline。**
  因此运行时必须用 `PYTHONPATH` 把目标 `sglang-3090-24g-opt/python` 放在最前面，
  并且用 `.pth`/overlay 绑定目标 source；**不要把它当成 9B canonical runtime 直接使用**。
- 应用层依赖（orjson、msgspec、pyzmq、uvicorn、sgl_kernel、flashinfer、gguf、uvloop、
  fastapi、setproctitle、einops、jsonschema、soundfile、python-multipart）全部以
  **task-local overlay** 形式叠加，不写入共享 venv。

### 2.5 GPU / 3090 纪律

| 项 | 值 |
|---|---|
| RTX 3090 UUID | `GPU-2e3ed202-3655-d919-0a64-259209bc6587`（sm_86） |
| GT 1030 UUID | `GPU-6cd7c455-d040-d992-b5b4-ed8afc6a91fc`（sm_61） |
| 驱动 | `580.178.04` |
| 协调锁 | `/mnt/data/gpu/3090.lock` |

**必须知道的坑：本机 NVML index 与 CUDA ordinal 是反的。**

```
nvidia-smi index 1  → RTX 3090
nvidia-smi index 0  → GT 1030
CUDA ordinal 0      → RTX 3090
CUDA ordinal 1      → GT 1030
```

所以**永远不要用 `CUDA_VISIBLE_DEVICES=1`**，必须用 UUID：

```bash
export CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
```

否则程序会跑到 GT 1030 上并报 `CUDA error: no kernel image is available`。

所有 GPU/server 操作前必须持锁：

```bash
exec 9>/mnt/data/gpu/3090.lock; flock -w 300 9
```

Chrome / Obsidian / 其它 session 的 GPU 进程**不得**被杀；禁止 `pkill -f` 之类广域模式。

### 2.6 Canonical serving profile（B1-C 已验证可启动）

```bash
CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587 \
/mnt/data/cache/venv/bin/python -B -m sglang.launch_server \
  --model-path /mnt/data/models/local-prod-baseline-v1/qwen35-9b-gptq-int4/ \
  --host 127.0.0.1 --port <PORT> \
  --mem-fraction-static 0.8 \
  --disable-prefill-cuda-graph
```

说明：

- `--mem-fraction-static 0.8` 是必需的：不指定时自动推导会取
  `min(memory.total)`（含 GT 1030 的 2 GiB），得到 `-0.984`，导致
  `max_mamba_cache_size=-299` / `total_rest_memory=-30.09 GB` 的负预算失败。
- `--disable-prefill-cuda-graph` 是当前唯一已验证可完成启动的设置；
  prefill CUDA graph 在第一次 2048-token capture 处长时间不返回（≥504s 无进展）。
- **MTP/ speculative 一律不传参数**（不传 = off）。
  `--disable-mtp` / `--enable-mtp` / `--mtp` 在当前 source 都不存在，会被 parser 拒绝。
- 不要为了启动失败而改 dtype/quant/kernel/context 参数；先保留真实日志。

---

## 3. 已完成并通过的 gate（可直接引用，不要重跑）

### B0 — GROUP_COMMIT acceptance：**PASS / CLOSED**

- 9/9 temporal suite；真实 `ExtentFileBackend` grouped KV+Mamba fixture；
- C1 crash before `GROUP_COMMIT` → KV/Mamba 均未恢复；
- C2 durable `GROUP_COMMIT` → KV/Mamba byte-identical 恢复。
- 证据：`/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B0-rerun-20260913/`
  （`VERIFICATION-REPORT.md`、`manifest.json`）

### B1 — profile / artifact reconciliation：**DONE**

- 历史 9B intent（3090-dev launcher、pool64、concurrency 8、RH off 等）已盘点。
- canonical 模型 artifact 已按 revision + 全文件 SHA256 冻结（见 §2.3）。
- 启动链已打通（见 §2.6）。

### B1-C — 结构启动 + 语义正确性：**PASS**

- 1170/1170 body tensors consumed、zero required not-found warnings、
  `lm_head.weight` exactly once、231 GPTQ companion tensors（248 each）；
- GPTQ-Marlin dispatch、FlashInfer、Mamba cache、KV cache 分配、`/health` 200；
- 确定性语义探针：`enable_thinking=false`、`max_tokens=128`、greedy → 输出 `OK`、
  `finish_reason=stop`；
- 证据：`B1-9B-gpu-runtime-disable-prefill-graph-20260914/`（首次 health 200）、
  `loader-shim-gpu-validation-20260914/`、`loader-semantic-probe-20260914/`、
  `loader-shim-terminal-review-20260914/`。

### B2 — G1 current-byte requalification：**PASS_FOR_CURRENT_BYTES**

- `102 + 42 + 17 = 161` tests passed；`py_compile` / `compileall` exit 0；
- fresh subprocess SIGKILL/reopen harness：exact PID、return `-9`、进程消失、
  ungrouped + grouped KV/Mamba 字节恢复、incomplete group 排除、新 namespace epoch、
  sequence 重启；
- 独立终审：145 个 artifact 全部 hash/size 一致，decision
  `PASS_FOR_CURRENT_BYTES`。
- 证据：`B2-current-bytes-correct-20260914/`、
  `B2-current-bytes-terminal-review-20260914/`。
- **限制（必须保留）**：历史 post-DEFECT-3 final reviewed-byte 的 per-file
  `EXACT_MATCH` 仍是 `INSUFFICIENT_EVIDENCE`；B2 只对**当前 bytes**成立。

### B3 — 性能（部分完成）

已完成并归档：

1. **token-exact prefill baseline：PASS**
   - cells：`it2048/8192/32768/65536` × `ot32` × `C1/C4`，每 cell 1 warmup + 3 measured repeats；
   - C1 = 5 requests、C4 = 20 requests；共 24 repeats / 300 responses；
   - 每个请求 local rendered token count 与 server `usage.prompt_tokens` **精确相等**；
   - 证据：`/mnt/data/cache/performance-baseline-v1/prefill/20260914T-token-exact-retry-.../`
2. **compute ceiling：PASS**
   - C1/C4/C8/C16，3 repeats；
   - 证据：`/mnt/data/cache/performance-baseline-v1/compute/20260914T064033Z-compute-prefill-canonical/`
3. **bounded non-streaming semantic aggregate：已归档接受**
   - 32/32 transport/schema/semantic、0 error、577 completion tokens、
     completion latency p50/p95/p99 = `0.2554 / 0.4572 / 0.5401 s`；
   - 归档：`/mnt/data/cache/performance-baseline-v1/runs/B3-semantic-aggregate-20260914T1348Z/`
     与 `summaries/SEMANTIC-AGGREGATE-BASELINE.md`；
   - **限制**：non-streaming → **没有 TTFT**；不是 soak/restart，也不是 production traffic。

---

## 4. 当前唯一阻塞：P0 telemetry（B3 全面性能基线的前置）

### 4.1 为什么需要它

后续每一次优化（CUDA Graph、Marlin、Mamba、RH、Extent I/O、scheduler）都要能回答
“到底改善了哪一层”。当前 runtime 无法权威拆分：

- 精确 L1/L2/L3 per-tier token accounting 与 restore/stage latency；
- `avoidable_recompute_tokens`；
- RH `lead/slack`、ready-before-admission；
- Mamba restore/rebuild/eviction；
- GPU/CPU/PCIe/NVMe 外部 telemetry。

因此这些字段在基线中一律标记 `UNAVAILABLE`，**不得**用 occupancy 或 total token throughput 推断。

### 4.2 已完成的 P0 工作

- 设计（低 cardinality Prometheus + opt-in JSONL）：`P0-TELEMETRY-DESIGN-20260914.md`
- Expert Gate（公式与 authority 裁决）：`P0-TELEMETRY-EXPERT-GATE-20260914.md/json`
  - `prefetch_issue_mono_ns` 由 controller 在 `prefetch_queue.put` 前赋值一次；
  - L3 credit 必须是 same-lineage / same-attempt / same-generation / prompt-bound /
    component-complete，否则 `null`；
  - 守恒式唯一采用：`prompt_tokens = L1 + L2 + L3 + newly_prefilled`；
  - `avoidable_recompute` 是 `newly_prefilled` 的 nullable 子集，**不是**第四个分区。
- 性能规范 v2 + erratum：`/mnt/data/cache/performance-baseline-v1/manifest/`

### 4.3 尚未解决（review = CHANGES_REQUIRED）

1. **HIGH**：proof 失效后，positive 的 durable total / avoidable recompute 仍可能保留，
   导致 `outcome=complete`。必须把 classification / durable_total / avoidable_recompute /
   outcome 从**同一个已验证 proof result** 派生，proof 失效即全部 null。
2. **HIGH**：hybrid（DSA/SWA/Mamba）component-complete authority 未实现；
   现有 helper 只是过滤 KV 派生 sidecar，不构成共同边界证明。
   未证明的 layout 必须把 L3/durable/recompute 全部置 null。
3. **MEDIUM**：embedding 输出路径丢失 JSONL telemetry
   （`TokenizerManager` 只对 non-embedding 输出附加）。
4. 现有 13 个测试偏 helper/static，**未**覆盖真实 queue handoff、finalizer proof
   invalidation、metrics DI、JSONL writer、embedding seam。

### 4.4 Provenance 现状（重要）

系统在最后一次 remediation 调度期间重启/被中断：

- 被中断的 remediation **没有产生任何输出目录或残留文件**（已核对）；
- 没有遗留 SGLang 进程、没有锁持有者；
- 但旧 packet 对 bounded 文件集存在 hash 空档，故既有结论为
  `PROVENANCE_CHANGED` / `INSUFFICIENT_EVIDENCE`。

已用 **current-byte 17-file packet** 重新冻结为唯一输入：

```
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-current-correction-packet-17-20260914/
  → CONCLUSION: CURRENT_PACKET_READY
```

今后所有 P0 修复只能**基于这个 current packet**，不要再引用缺失的历史 hash。

---

## 5. 性能基线规范（v2）与目录契约

根目录：

```
/mnt/data/cache/performance-baseline-v1/
  manifest/     spec v2、telemetry contract、expert gate、erratum
  compute/      compute ceiling cells
  prefill/      token-exact prefill cells
  cache-l1/ cache-l2/ cache-l3/   cache reuse 分层
  agent/        multi-round / tool-shaped agent corpus
  stability/    soak / restart（**不计入性能分数**）
  telemetry/    外部 sidecar telemetry（P2）
  runs/ corpora/ logs/ summaries/
```

必须记录的三类吞吐（**绝不混用**）：

```
aggregate_output_tps   = output_tokens / wall_time
effective_compute_tps  = (actual_prefill_tokens + output_tokens) / wall_time
served_context_tps     = (prompt_tokens + output_tokens) / wall_time
```

用户体验指标：`TTFT`、`E2E`、`TPOT`、`ITL` 的 p50/p95/p99（streaming 请求）。

统计纪律：

- 每 cell ≥3 repeats，报告 median；
- `num_prompts >= 5 × concurrency`；
- warmup 与 measured 严格分离；cold 必须 flush，warm 禁止 flush；
- 固定 seed/corpus；p99 只在样本量足够时报告；
- soak/restart 属 stability，**不得**当作性能基线。

工作负载四类（不要组合爆炸）：compute ceiling / prefill / cache reuse / agent。
UX 与 agent 用 streaming；纯吞吐可用 non-streaming。

可用与不可用 telemetry（权威来源）：

- 可用：`/metrics`（需 `--enable-metrics`）、`/v1/loads?include=all&format=json`、
  `/health`、`/model_info`、`/server_info`；
- 当前实测：`/metrics` 返回 **404**（该 server 启动参数下），`/v1/loads` 返回 200；
- 不可用：见 §4.1 列表，必须写 `UNAVAILABLE`。

---

## 6. 关键教训（避免重复踩坑）

1. **不要为不同模型各装一套 Torch/CUDA。** 共享 `/mnt/data/cache/venv` + 系统 CUDA +
   task-local overlay 即可；`torch --no-deps` 之类做法会人为拆坏依赖闭包。
2. **checkout/source 绑定必须显式验证。** 曾出现测试环境绑定到 `sglang-3090-24g-hicache`
   或 `/home/charles/...` 的情况，导致“找不到测试文件”被误报。
3. **不要用 `$` 字面量或错误路径调用 Python**（曾出现 `$ /mnt/data/cache/venv/bin/python`
4. **oracle 必须检查 own-marker。** 早期 B3 oracle 只查 schema/非空，把
   `! × 32` 判成 integrity pass，导致错误的 `PERFORMANCE-PASS`。
5. **`! × 32` 的根因是 loader key mismatch**（1170 body tensors 全部未加载），
   不是 CUDA/Marlin/kernel 问题，也不是 thinking template 问题。
6. **prefill cell 必须 token-exact。** 早期 `--input 65536` 实际是 65536 个 `wN`
   空白分词项 → 模板化后 254,940 tokens > `max_req_input_len 196238`，请求被拒。
7. **运行环境的 SGLang source 可能是 27B 的**；`PYTHONPATH` 顺序与 `.pth` 必须显式校验，
   否则会在错误的 source 上得出结论。
8. **不要把 metrics 升 cardinality。** request/session/attempt ID 绝不进 Prometheus label；
   详细字段只进 JSONL。

---

## 7. 证据索引（按主题）

```
# baseline / B0 / B1
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B0-rerun-20260913/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-9B-artifact-20260913/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-9B-profile-20260913/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-9B-gpu-runtime-disable-prefill-graph-20260914/   # 首次 health 200
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-device-mapping-20260914/                        # GPU ordinal 反转实证
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-mamba-memory-diagnosis-20260914/                # mem_fraction 0.8 依据
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B1-long-startup-diagnosis-20260914/                # prefill graph capture 卡点

# loader shim
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/loader-callchain-reconciliation-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/loader-shim-implementation-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/loader-shim-terminal-review-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/loader-shim-gpu-validation-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/loader-semantic-probe-20260914/                    # SEMANTIC-PASS

# B2
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B2-current-bytes-correct-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B2-current-bytes-terminal-review-20260914/

# B3 语义退化与撤销
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B3-gptq-zero-token-diagnosis-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B3-root-cause-terminal-review-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B3-oracle-correction-20260914/

# P0 telemetry
/mnt/data/cache/performance-baseline-v1/manifest/P0-TELEMETRY-DESIGN-20260914.md
/mnt/data/cache/performance-baseline-v1/manifest/P0-TELEMETRY-EXPERT-GATE-20260914.md
/mnt/data/cache/performance-baseline-v1/manifest/PERFORMANCE-BASELINE-SPEC-v2.md
/mnt/data/cache/performance-baseline-v1/manifest/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.md
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-telemetry-final-fix-20260914/
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-telemetry-final-review-20260914/               # CHANGES_REQUIRED
/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-current-correction-packet-17-20260914/         # 唯一修复输入

# 性能 cache
/mnt/data/cache/performance-baseline-v1/
```

---

## 8. 下一步执行顺序（严格按序）

1. **P0 remediation（基于 current-17 packet）**
   - 单一 proof result 原子驱动 classification/durable_total/avoidable_recompute/outcome；
   - hybrid component-complete authority（未证明即 null）；
   - embedding JSONL telemetry 传播；
   - 补真实 production-seam tests（queue handoff / finalizer / metrics DI / JSONL / embedding）。
2. **P0 独立终审**（correction-and-revalidate）
   - 必须绑定 Expert Gate 与 erratum 的精确 hash；通过后才解锁性能重跑。
3. **telemetry-enabled 性能重跑**（新 immutable run ID）
   - cache-l1 / cache-l2 / cache-l3 / agent；
   - streaming TTFT / TPOT / ITL；
   - 三类 TPS 与 cache accounting（或明确 `UNAVAILABLE`）。
4. **stability run**
   - soak ≥10 分钟、多轮 C4/C8、health continuity、drain、graceful shutdown；
   - restart：port close/rebind、relaunch health、preservation corpus、GPU release。
   - **不得**把 soak/restart 计入性能分数。
5. **全面性能基线终审 + scorecard freeze**（落在 `performance-baseline-v1/summaries/`）。
6. **B4 freeze**：baseline manifest、launcher、rollback、limitations、3090 canary evidence。

---

## 9. 禁止事项（硬约束）

- 不做 v0.5.19 broad merge；不做 repair8/repair9；不引入 U4/RH 新机制、fallback、
  新 durability/storage feature、engine tuning。
- 不修改 production source，除非属于当前已授权 loader shim / P0 telemetry scope，
  且经过独立终审。
- 不使用 `--disable-mtp`（不存在）或其它未验证参数；不通过改 dtype/quant/context
  参数“绕过”失败。
- 不使用 `CUDA_VISIBLE_DEVICES=1`（会落到 GT 1030）。
- 不杀其它 session 的 GPU 进程；不用广域 `pkill -f`。
- 不把 4B / 27B / 旧 4B evidence 当作 9B acceptance。
- 不把 `.gitignore` 当作存储策略；构建产物与日志一律放 `/mnt/data`。
- 不伪造 hash、不臆测缺失字段；不可用即 `UNAVAILABLE`。
- 不在 B3 语义正确性通过前启动 B4。

---

## 10. 一句话状态总结

> baseline source、9B 模型 artifact、3090 canonical serving profile、loader shim、
> B2 G1 current-byte requalification、token-exact prefill/compute 性能基线**均已通过**；
> 当前唯一阻塞是 **P0 telemetry 的三项终审缺陷 + provenance 需基于 current-17 packet 重建**；
> telemetry 终审通过前，全面性能重跑与 B4 均不启动。
