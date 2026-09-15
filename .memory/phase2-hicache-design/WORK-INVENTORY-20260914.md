# WORK INVENTORY 2026-09-14 — LOCAL-PROD-BASELINE-v1

退出前完整盘点。所有结论都指向可核验的证据路径，不依赖任何 session 记忆。
配套文档：`HANDOFF-20260914-LOCAL-PROD-BASELINE-v1.md`（接手用）、`ledger.md`（决策流水）。

---

## 0. 状态一览

| 工作块 | 状态 | 说明 |
|---|---|---|
| B0 GROUP_COMMIT acceptance | ✅ DONE | 9/9 suite + C1/C2，独立复核后 CLOSED |
| B1 9B artifact/profile reconciliation | ✅ DONE | artifact 与启动链冻结 |
| B1-C 结构启动 + 语义正确性 | ✅ DONE | 1170/1170 body tensors，确定性探针 PASS |
| loader shim（root-cause 修复） | ✅ DONE | 独立复审 + GPU 验证链完整 |
| B2 G1 current-byte requalification | ✅ DONE | 161 tests，终审 PASS_FOR_CURRENT_BYTES |
| B3 token-exact prefill baseline | ✅ DONE | 24 repeats / 300 responses，token 精确相等 |
| B3 compute ceiling baseline | ✅ DONE | C1/C4/C8/C16 × 3 repeats |
| B3 bounded semantic aggregate | ✅ DONE（有范围限制） | 32/32 transport/schema/semantic，无 TTFT |
| 性能基线 cache 目录 + spec v2 | ✅ DONE | 目录、contract、erratum、可用性记录 |
| **P0 telemetry（低 cardinality + JSONL）** | ❌ **NOT DONE** | review `CHANGES_REQUIRED`，三项缺陷未修 |
| **P0 telemetry provenance** | ⚠️ 已重建为 current-byte，但历史闭环不成立 | 旧 packet hash 有 10 处空档 |
| B3 cache-l1/l2/l3 + agent 矩阵 | ⛔ BLOCKED | 等 P0 telemetry 终审 |
| B3 streaming TTFT/TPOT/ITL | ⛔ BLOCKED | 等 P0 telemetry 终审 |
| B3 soak / restart stability | ⛔ INCOMPLETE | 6 轮后中止，35/36 语义，未做 restart |
| 全面性能基线终审 + scorecard freeze | ⛔ BLOCKED | 上游全部未完成 |
| **B4 freeze/launcher/rollback/canary** | ⛔ BLOCKED（未授权） | 上游 gate 未通过 |
| v0.5.19 broad merge | 🅿️ PARKED | 已归档 park report，protected refs 完好 |

图例：✅ 完成并已复核 / ⚠️ 部分且已知缺口 / ❌ 未完成 / ⛔ 上游阻塞 / 🅿️ 主动搁置

---

## 1. 冻结身份（重跑必须逐字节匹配）

```
repo            /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
                （git worktree，共享 .git 在 sglang-3090-24g-hicache）
branch          3090-24g-opt（working branch；后续工作在此展开）
HEAD            34bd2ed49f2b2e6fef504019bfe3840eb30ac061（.memory 交接提交）
prod-source     993ef8e5c3a6448aff2e752cf66cc45deadab59a（= HEAD 去掉 .memory，逐字节相同）
git tree obj    75d8d1af8dfef5680085e67767c670554d7163af（生产源 tree，属 993ef8e5）
tree manifest   5fe5a694a628867ee6c5a7be10a7dfa5dd854501e9c2b75e475c24b6a033f338
                = sha256(git ls-tree -r 993ef8e5 --full-tree bytes)，≠ tree object ID
superset        origin/3090-24g-hicache @ 560f9ad5256ad95b8075f474a679918340fcca47
                （= opt + 3090-dev 的 22151 部署文档，+4 files / +278 行）
remote origin   git@github.com:charleslai2000/sglang.git（PRIVATE）
protected refs  refs/heads/checkpoint/pre-v0.5.19-20260913
                refs/tags/checkpoint/pre-v0.5.19-20260913
```

分支整合（2026-09-16，已核实）：

- `3060-12g-qwen35-4b` 是历史命名（源于最初在 12GB RTX 3060 / sm_86 上的适配工作，
  sm_86 同时是 3090 架构，故 kernel/loader 工作被 3090 复用）；其 tip `34bd2ed49f`
  已快进合并入 `3090-24g-opt` 并从本地与 `origin` 删除，35 个 commit 全部保留。
- `3090-24g-opt` 与 `3090-24g-hicache` 现为父子超集关系：
  `3090-24g-opt` unique = 0；`3090-24g-hicache` unique = 3（2 个文档 commit + merge commit）。
- merge 方向约定：**opt → hicache**。后续工作在 opt 上展开，需要归档时再合并入 hicache。
- `3090-24g-hicache` 的更上游来源是 `5090-32-hicache`
  （merge-base `54c394a2e1` = `origin/5090-32-hicache` 的 tip），再向上为
  `upstream/main b644771e07`。
- 合并时 hicache worktree 有 9 个未跟踪文件与 opt 的 tracked 路径重名（其中 8 个内容不同，
  且均不在 merge-base 中），已**移动**（非删除）至
  `/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/hicache-worktree-collision-backup-20260916/`
  并附 `untracked-snapshot-20260916.tar.gz`（619 entries）+ `moved-aside-manifest.txt`（逐文件 sha256）。

模型：`mssfj/Qwen3.5-9B-GPTQ-INT4` rev `d44718f79ab5dd3e46ce546d25168bb7ac6a175e`，
本地 `/mnt/data/models/local-prod-baseline-v1/qwen35-9b-gptq-int4/`，
`model.safetensors` SHA256 `a81fb938ed15819c7e76453fa3e599fa4dee84af75972d3f2aca6b65b11cefaa`（7,670,240,000 bytes）。

---

## 2. 已完成工作（含证据位置）

### 2.1 B0 — GROUP_COMMIT acceptance：CLOSED

- 9/9 temporal acceptance suite；
- 真实 `ExtentFileBackend` grouped KV+Mamba fixture；
- C1：`GROUP_COMMIT` 前崩溃 → KV/Mamba **均未**恢复；
- C2：durable `GROUP_COMMIT` → KV/Mamba **byte-identical** 恢复。
- 证据：`/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/B0-rerun-20260913/`

### 2.2 B1 / B1-C — artifact + 结构启动 + 语义正确性：PASS

- artifact 全文件 size/SHA256 冻结（revision 级）。
- 1170/1170 body tensors consumed；`lm_head.weight` 恰好一次；
  231 个 GPTQ companion tensors（248 each）；零 required not-found warning。
- GPTQ-Marlin dispatch、FlashInfer、Mamba cache、KV cache 分配、`/health` HTTP 200。
- 确定性语义探针（`enable_thinking=false`、greedy、`max_tokens=128`）→ 输出 `OK`，
  `finish_reason=stop`；相对修复前 `! × N` 是决定性差异。
- 证据：`B1-9B-gpu-runtime-disable-prefill-graph-20260914/`、
  `loader-semantic-probe-20260914/`、`B1-device-mapping-20260914/`、
  `B1-mamba-memory-diagnosis-20260914/`、`B1-long-startup-diagnosis-20260914/`

### 2.3 loader shim — root-cause 修复：DONE

- 根因：text wrapper → body loader 的 prefix 断链，导致 1170 body tensors **全部未加载**，
  模型退化为 constant-0 logits（输出 `!`）。**不是** CUDA/Marlin/kernel/thinking-template 问题。
- 修复：`python/sglang/srt/models/qwen3_5_text.py` 的 `load_weights`，
  在 generic `model.` strip **之前**处理 `model.language_model.`。
- SHA256：`22ef63395989e626e7258ae5b8c1f42bfafa8dcc9edd9bfce4989958b78a5352`
- 独立复审结论 `APPROVED_FOR_GPU_VALIDATION`，随后 GPU 验证通过。
- 证据：`loader-callchain-reconciliation-20260914/`、`loader-shim-implementation-20260914/`、
  `loader-shim-terminal-review-20260914/`、`loader-shim-gpu-validation-20260914/`

### 2.4 B2 — G1 current-byte requalification：PASS_FOR_CURRENT_BYTES

- `102 + 42 + 17 = 161` tests passed；`py_compile` / `compileall` exit 0；
- fresh subprocess SIGKILL/reopen harness：exact PID、return `-9`、进程消失、
  ungrouped + grouped KV/Mamba 字节恢复、incomplete group 排除、新 namespace epoch、sequence 重启；
- 独立终审：145 artifacts hash/size 全一致 → `PASS_FOR_CURRENT_BYTES`；
- **已知缺口**：历史 post-DEFECT-3 final reviewed-byte 的 per-file `EXACT_MATCH`
  仍为 `INSUFFICIENT_EVIDENCE`（B2 只对 current bytes 成立）。
- 证据：`B2-current-bytes-correct-20260914/`、`B2-current-bytes-terminal-review-20260914/`

### 2.5 B3 性能（已完成部分）

**a) token-exact prefill baseline — PASS**

- cells：`it2048/8192/32768/65536 × ot32 × C1/C4`；每 cell 1 warmup + 3 measured；
  C1 = 5 req、C4 = 20 req；合计 24 repeats / 300 responses；
- 每个请求 **local rendered token count == server `usage.prompt_tokens`**（token-exact 成立）；
- 有效上限：`max_total_num_tokens=196244`、`max_req_input_len=196238`、
  `max_prefill_tokens=16384`、`chunked_prefill_size=2048`；模型 context 262,144；
- 证据：`/mnt/data/cache/performance-baseline-v1/prefill/20260914T-token-exact-retry-.../`

**b) compute ceiling — PASS**

- C1/C4/C8/C16，每点 3 repeats；
- 证据：`/mnt/data/cache/performance-baseline-v1/compute/20260914T064033Z-compute-prefill-canonical/`

**c) bounded semantic aggregate — ARCHIVE_ACCEPTED（范围受限）**

- 32/32 transport/schema/semantic、0 error/timeout、577 completion tokens；
  `c1/c2/c4/c8 × 8` requests；completion latency p50/p95/p99
  = `0.2554 / 0.4572 / 0.5401 s`；
- 归档：`/mnt/data/cache/performance-baseline-v1/runs/B3-semantic-aggregate-20260914T1348Z/`
  与 `summaries/SEMANTIC-AGGREGATE-BASELINE.md`；
- **限制**：non-streaming → 无 TTFT；bounded synthetic，非 production traffic；
  不是 soak/restart，不计入稳定性结论。

**d) 已作废的早期结果（必须保持作废，不得复用）**

- `prefill-i*` 旧 cells：word-count 建模错误（64K 标签 = 65,536 个空白分词项
  → 模板化后 254,940 tokens > `max_req_input_len`，请求被拒）；
- 早期 `PERFORMANCE-PASS`：oracle 未检查 own-marker，把 `! × 32` 误判为 integrity pass；

### 2.6 性能基线 cache 与规范

```
/mnt/data/cache/performance-baseline-v1/
  runs/ corpora/ manifests/ logs/ summaries/
  manifest/ compute/ prefill/ cache-l1/ cache-l2/ cache-l3/ agent/ stability/ telemetry/
```

已冻结：

- `manifest/PERFORMANCE-BASELINE-SPEC-v2.{md,json}`（三类 TPS 定义、repeats、warmup/cold 纪律）
- `manifest/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.*`
- `manifest/telemetry-availability-20260914.{md,json}`（不可用字段一律 `UNAVAILABLE`）
- `manifest/prefill-context-reconciliation-20260914.{md,json}`
- `manifest/P0-TELEMETRY-DESIGN-20260914.*`、`manifest/P0-TELEMETRY-EXPERT-GATE-20260914.*`

三类吞吐（**绝不混用**）：

```
aggregate_output_tps   = output_tokens / wall_time
effective_compute_tps  = (actual_prefill_tokens + output_tokens) / wall_time
served_context_tps     = (prompt_tokens + output_tokens) / wall_time
```

### 2.7 环境与运行纪律（已固化）

- 共享运行时 `/mnt/data/cache/venv`（Python 3.12.3、torch 2.13.0+cu130、CUDA 13.0、
  driver 580.178.04）；**该系统 venv 的 SGLang editable finder 仍指向 27B source**，
  运行时必须用 `PYTHONPATH` 把目标 source 置前，不得直接当 9B runtime 使用。
- 系统 CUDA `/usr/local/cuda-13.0`（nvcc 13.0.48）；`~/.bashrc` 已导出 CUDA_* 变量。
- 应用依赖全部走 task-local overlay（orjson / msgspec+pyzmq+uvicorn / sgl_kernel 0.4.6.post1 /
  flashinfer 0.6.17 / gguf 0.19.0 / uvloop / fastapi / setproctitle / einops / jsonschema /
  soundfile / python-multipart），不写入共享 venv。
- run env（source-only）：`B1-unified-run-env-20260914/run-env.sh`、`B3-unified-run-env-20260914/run-env.sh`
- B0 测试依赖 venv：`B0-20260913-venv`（pytest 9.1.1 等）；用
  `/mnt/data/cache/venv/bin/python -m pytest`（无 `bin/pytest`）。
- 3090 协调锁 `/mnt/data/gpu/3090.lock`；GPU 必须用 **UUID** 绑定
  （本机 NVML index 与 CUDA ordinal 相反，`CUDA_VISIBLE_DEVICES=1` 会落到 GT 1030）。

---

## 3. 未完成工作

### 3.1 ❌ P0 telemetry — 当前唯一硬阻塞

**目的**：让后续每次优化都能回答"改善了哪一层"。缺它则 cache/RH/Mamba/Extent 的收益无法归因，
全面性能基线不成立。

**review 现状**：`CHANGES_REQUIRED`（`P0-telemetry-final-review-20260914/`）

未修缺陷：

1. **HIGH — proof 失效未原子化**
   一个 mismatched proof 仍可能被分类为 `unknown/null`，而 positive 的 durable total 与
   avoidable-recompute 保留，最终 `outcome=complete`。必须从**同一个已验证 proof result**
   一次性派生 classification / L3 / durable_total / avoidable_recompute / outcome；proof 失效即全 null。
2. **HIGH — hybrid component-complete authority 未实现**
   DSA/SWA/Mamba 共同边界（matched-prefix/component-complete）无证明；
   现有 suffix-completeness helper 只是过滤 KV 派生 sidecar，不构成共同边界证明。
   未证明的 layout 必须把 L3 / durable / recompute 全部置 null。
3. **MEDIUM — embedding 路径丢失 JSONL telemetry**
   `TokenizerManager` 只对 non-embedding 输出附加 JSONL 对象。
4. **测试覆盖不足**
   现有 13 个测试偏 helper/static，**未**覆盖真实 queue handoff、finalizer proof invalidation、
   metrics DI、JSONL writer、embedding seam。

**已完成的 P0 前置**：design、Expert Gate、spec erratum、实现、两轮 fix、focused 测试环境。

### 3.2 ⚠️ P0 provenance — 已降级为 current-byte 基线

- 系统在最后一次 remediation 调度期间重启/被中断；
- 被中断的 remediation **无任何输出目录或残留**；
  退出前核对：17 个 P0 文件的 `sha256sum -c` 相对冻结包**零失败** → 被中断的 coder 未写入任何字节；
- 旧 packet 对 bounded 文件集有 **10 处 hash 空档**，故历史闭环不成立
  （`PROVENANCE_CHANGED` / `INSUFFICIENT_EVIDENCE`）；
- 已重建唯一输入：
  `/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-current-correction-packet-17-20260914/`
  → `CURRENT_PACKET_READY`（17 files，HEAD/tree/逐文件 SHA256 已冻结）。
- **今后所有 P0 修复只能基于该 current packet，不得引用缺失的历史 hash。**

### 3.3 ⛔ B3 未完成矩阵

- `cache-l1` / `cache-l2` / `cache-l3`（cold vs warm、flush 后重放、RH 行为）；
- `agent/`（multi-round / tool-shaped corpus）；
- streaming UX：TTFT / TPOT / ITL / E2E 的 p50/p95/p99（**当前完全缺失**）；
- telemetry-enabled 重跑（P0 终审通过后）。

### 3.4 ⛔ soak / restart stability — INCOMPLETE

已发生的唯一一次：`B3-soak-restart-shim-20260914T061229Z`

- 6 轮 c4/c8、36 requests；transport 36/36；**semantic 35/36**；
- 在 round 5 / concurrency 8 停止（输出 `continue`，own marker 缺失）；
- 时长 ~64 s < 10 分钟阈值 → **不满足 soak 标准**；
- restart / port rebind / preservation corpus **完全未开始**。

该 run 只算 stability 证据，**不得**当性能分数。

### 3.5 ⛔ 全面性能基线终审与 scorecard

需在 P0 telemetry 终审 + 性能矩阵 + stability 全部完成后，做独立终审并冻结
scorecard / profile identity 到 `performance-baseline-v1/summaries/`。

### 3.6 ⛔ B4 — freeze / canary（未授权）

baseline manifest 冻结、launcher、rollback 程序、limitations、3090 canary 证据。
在所有 B3 正确性 + 性能 + stability gate 通过前**不启动**。

### 3.7 🅿️ v0.5.19 broad merge

已归档 `merge-park-20260913/PARK-REPORT.md`；protected refs 完好；本轮不恢复。

---

## 4. 未提交状态（进入 repo 的只有 `.memory/`）

退出时 worktree 的 production 变更是 **uncommitted**，这是有意的：

- 已授权但待 P0 终审：`python/sglang/srt/observability/hicache_telemetry.py`（untracked）
  与 13 个已修改文件（managers / mem_cache / observability / models）；
- loader shim：`python/sglang/srt/models/qwen3_5_text.py`（已通过自身 review，但未单独 commit）；
- test-only：`test/registered/unit/mem_cache/test_extent_g1_metadata_unit.py`、
  `test/registered/unit/managers/test_multi_tokenizer_mixin.py`、
  `test/registered/unit/observability/test_hicache_request_telemetry.py`（untracked）。

**不要把 P0 telemetry 未终审的字节随 `.memory` 一起提交。**

`.memory/` 的提交范围说明：

- 记录类文件（`*.md` / `*.yaml` / `*.json` / `*.jsonl` / `*.sha256` / `*.txt` / `*.py`）进 repo；
- `*.log`（约 808 MB 原始运行日志）、`*.out`、`__pycache__/` 由仓库既有 `.gitignore` 排除，
  按存储纪律这些字节本应位于 `/mnt/data` 卷，不应进 git。

---

## 5. 恢复工作时的执行顺序

1. 基于 `P0-current-correction-packet-17-20260914` 修 §3.1 三项缺陷 + 真实 production-seam tests；
2. 独立 correction-and-revalidate 终审（绑定 Expert Gate 与 erratum 的精确 hash）；
3. telemetry-enabled 性能重跑：cache-l1/l2/l3 + agent + streaming TTFT/TPOT/ITL；
4. stability：soak ≥10 min 多轮 C4/C8 + restart/rebind/preservation，**不计入性能分数**；
5. 独立终审 + scorecard / profile identity 冻结；
6. B4：manifest / launcher / rollback / limitations / canary。

---

## 6. 硬约束（跨 session 有效）

- 不做 v0.5.19 broad merge、repair8/9、U4/RH 新机制、fallback、新 durability/storage feature、engine tuning；
- 不改 production source，除非属于已授权的 loader shim / P0 telemetry scope 且通过独立终审；
- 不使用 `--disable-mtp`（当前 source 不存在）或其它未验证参数；不用改 dtype/quant/context 绕过失败；
- 不用 `CUDA_VISIBLE_DEVICES=1`；不用广域 `pkill -f`；不杀其它 session 的 GPU 进程；
- 不把 4B / 27B / 旧 4B evidence 当作 9B acceptance；
- 不把 metrics cardinality 升高（request/session/attempt ID 只进 JSONL）；
- 不伪造 hash、不臆测缺失字段 —— 不可用即 `UNAVAILABLE`；
- B3 语义正确性通过前不启动 B4。
