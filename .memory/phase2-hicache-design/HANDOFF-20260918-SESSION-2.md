# HANDOFF — 2026-09-18 SESSION 2（owner 下令交接）

> 本文件由**前任 orchestrator** 在 owner 令交接时写入。
> **唯一控制文件仍是 `.memory/phase2-hicache-design/ledger.md`**（只由 orchestrator 写）。
> 本文件是**交接**，不是控制真相；但它自足，**新 session 先读本文件即可接管**。
> 本 session **未被终止**；新 session 独立开跑，**不要重复已在飞的工作**。

---

## 0. 立即要做的三件事（最高优先，按序）

| # | 事项 | 关键约束 |
|---|---|---|
| **T1** | **执行 A：把加固版 `qwen3_coder` detector 上线**（owner 明令「A 你负责改」，ledger §112） | **并入 M2 发布窗口**（HiCache trio + telemetry + detector 加固）⇒ **不额外多开窗口** |
| **T2** | 停 `:30000` **前**必须先通知 owner；**上线后立即告知 owner** | P0 不变式 5/6（§97/§109）。owner 已对"跑之前通知"给过同类授权，但**每个窗口都要通知** |
| **T3** | 补派模板前置：`templates/launch.sh.tmpl` + `bin/launcher-repin.sh`（设计 D2/D3 模板分支） | 前任只派了 MECH-EDITS 与 AUDIT-PROFILE，**这项没派** |

**第一步动作**：读盘对账两个在飞任务（见 §4），**不要**重复其工作。
**A 的完整 runbook 已就绪**（见 §3.5）——只需先补 P1/P2 两个 CPU 前置。
**两个在飞任务均已于交接时回件并整合**（见 §4）——**无需再对账**；新 session 从 §0 的 T1–T3 开始即可。

---

### 3.6 ⭐ M3/M4 残余已定位（`GGUF-M3M4-RESIDUAL-CAUSE`，243 行 DONE）
**结论**：残余在 **SGLang qwen35 前向/权重路径**，**上游**于 detokenize / chat template / reasoning parser / stop 配置。
- **不是** tokenizer id 修复（raw prompt 不经过它仍循环）、**不是** Gemma-norm fold（同一次循环中已在）。
- `EMPTY_CONTENT`/`TOO_SHORT` = 模型**首个/早期采样 token 就是 eos `<|im_end|>`=248046**；**非** parser 切分。
- **修前判据 2 "PASS" 是假象**：当时模型在**循环**，期望子串正好落在环里；修后 3 token 停在 eos ⇒ 子串判据失败。**底层 incoherence 前后都在。**
- **`chat_code` 独过是判分缺陷**（按语法 `compile`；M3 空块 `compile('')` 空洞 PASS）——门禁 D1 缺陷（属 `3090-dev/gates/**`）。
- **唯一下一步决定性实验（需 GPU，1 臂）**：M4 raw `/generate` + `temperature=0`，对比 **`--kv-cache-dtype fp8_e4m3` vs `auto`（bf16）**，读前 3 步 `output_ids`。修复 fp8 ⇒ fp8-KV 数值路径；仍循环 ⇒ GGUF 权重变换/布局（下一步 dump 一层 GDN/融合-QKV vs 反量化 GGUF 参考）。

---

## 1. 环境与范围

| 项 | 值 |
|---|---|
| 仓库 | `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`（分支 `3090-24g-opt`） |
| 控制文件 | `.memory/phase2-hicache-design/ledger.md`（**只追加，不重写历史**；§1–§112） |
| 结果 artifacts | `.memory/phase2-hicache-design/agents/*.md` |
| 生产 | `:30000`，**当前 UP**（M2，role=m2，tree `/opt/sglang/local-prod-v1.2.1-candidate-M2`，pid 会变，**以 `state/gpu-owner.json` 为准**） |
| 生产脚手架 | `/tmp/opencode/prod-service-20260917/`（`bin/start.sh m2`、**`bin/stop-m2.sh`**、`bin/supervise.sh`、`conf/service.env`、`state/gpu-owner.json`） |
| ⚠️ 停止脚本 | **`bash bin/stop-m2.sh`**（`bin/stop.sh m2` **不存在**，只接受 `prod\|test\|all`） |
| canonical lock | `/tmp/opencode/gpu-3090.lock` |
| 冻结树 | `/opt/sglang/local-prod-v1.2.1-candidate`（M1）、`…-M2`（M2，`SGLANG_L3_MODE=disabled`） |
| 模型 | M1 `/data/models/qwen35-9b-w4a16`；M2 `/data/models/omnicoder-9b-gptq-int4`；M3 `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`；M4 `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` |
| 禁 | `pkill`/`killall`、杀未识别占卡者、改权重/训练、把 GGUF 字节并入 commit、**就地改冻结树 `src/`**（M1/M2 共享 hardlink inode；改 src 必须重冻） |
| 单卡 | RTX 3090 24GiB；**M1/M2 不能共存**；宿主 RAM 125.9 GiB（可用 ~121 GiB）；**磁盘 `/` 仅剩 18.85 GiB（97% 满）** |

---

## 2. 交接时的**实质裁定状态**

| 维度 | 状态 | 依据 |
|---|---|---|
| M2 functional readiness | ✅ **PASS** | owner |
| M2 cache/reasoning telemetry | ✅ **PASS** | owner |
| **M2 替换 M1 的并发性能资格** | **HOLD 的解除路径已定**：owner 裁 **(a) M2 启用 HiCache** | §106；机制见 §105 |
| M3/M4 GGUF correctness | ❌ **FAIL（post-fix 有效裁决）**：判据 2 语义 + 判据 6 连贯，**两模型同因** | §107 |
| **A：detector 加固** | **owner 明令本线执行；未上线** | §112 |
| #5 Mamba 线 | D1 live PASS；D2 单测级 | 早前 § |
| reasoning-effort | 代码已整合；**线上行为未验**（需重启 + calibration） | 早前 § |

---

## 3. **A 是什么、为什么、怎么做**（本交接最重要）

### 3.1 问题（外部专家 + 本侧独立确认，§111/§112）
- 报错：`{"message":"upstream response contained invalid tool calls (invalid index)","type":"invalid_request_error"}`
- 产生点：**网关**（`/opt/opencodex/src/adapters/openai-chat.ts:1870`）—— 上游 `tool_calls[i].index` 为负/非法则拒。
- **根因（我侧）**：VM 上 M2 **经 PYTHONPATH 加载冻结树的未加固 `qwen3_coder_detector.py`**。
  当流里出现**孤儿的** `<parameter=` / `</function>`（任何 `<function=` 之前）⇒ 发出 **`tool_index = -1`**（基类哨兵，无非负校验）⇒ 线上 `"index": -1` ⇒ 网关拒。
- **加固版在 repo 工作树里已存在**（`python/sglang/srt/function_call/qwen3_coder_detector.py`，delay-commit 重写：索引只在 commit 时 `++`；孤儿永不成为 call）—— **但被 PYTHONPATH 遮蔽，未曾上线**。
- **影响**：`usage.jsonl` 9/11–9/19 共 **4 次**，全部 `worker → local/qwen35-9b-local`（含 `executor`、`coder`）。⇒ **它正在破坏 worker→本地后端的工具调用回合**（很可能也是 subagent 空转的原因）。

### 3.2 已证（前任一手）
- **PRE-FIX**（冻结树 `92eeaeaf…`）在孤儿片段上发出 `tool_index=-1`（6 个负索引项）。
- **POST-FIX**（工作树 `848e0690…`）**0 个负索引项**，且正常 call 仍在 index 0 完整提交。
- 复现脚本与原始输出：`/tmp/opencode/qwen3coder-invalid-index-20260918/{probe_frozen.py,probe_repo.py,frozen-run.txt,repo-run.txt,summary-*.json}`。

### 3.3 怎么修（**必须走冻结/重钉纪律**）
**不能**就地改冻结树（共享 inode、PYTHONPATH 指向它）。**必须**用 `3090-dev/tools/freeze/**` 走正式发布：
在 **stage 树**里换上加固 detector + 其余 telemetry 变更 ⇒ `launcher-repin.sh` ⇒ `freeze.sh` 冻 **M1 与 M2** ⇒ 起服务。
**且**：加固 detector 已**已**在设计 D4 白名单里（`src/python/sglang/srt/function_call/qwen3_coder_detector.py`）⇒ **无需额外窗口**，并入同一次 M2 发布即可。

### 3.4 完整发布设计（**必读**）
`.memory/phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`（367 行，DONE）
—— D1 最终 argv、D2 门禁重定义、D3 审计 profile、D4 白名单、D5 身份重钉、D6 回滚、**D7 15 步单窗口 runbook**。

### 3.5 ⭐ **A 的专用 runbook 已交付**（`QWEN3CODER-INVALID-INDEX-PROD`，443 行 DONE）
**推荐路径 = (a) 新建 M2-only 冻结树（detector-only）**：
- **M1 不受影响** —— `freeze.sh` 用 `rsync -a`（**无 `-H`**）⇒ **解除 M2 的 src 硬链**，M1 的 inode `27529144` 与 `92eeaeaf…` 不变。
- **窗口 ~10–15 min**；保持"冻结树=已验哈希"语义。
- **备选 (a')**：把 owner §106 的 **HiCache trio 一并放入同一棵 M2 树** ⇒ **P2 免做**，窗口变长（须验 `hicache_attached=True` + **N=16 保留 16/16**）。
- **(b)** 原合并窗口（含 **M1 重冻**）**风险最高** ⇒ 仅当前置来不及时退。

**两个 CPU-only 前置（阻塞最快路径；前任未派，新 session 决定）**：
| # | 文件 | 为何必须 |
|---|---|---|
| **P1** | `templates/launch.sh.tmpl`（+ `bin/launcher-repin.sh` 传 profile） | `freeze.sh` **总是**从模板重渲 launcher；模板是 **M1 形状**（`192.168.20.250`、`--served-model-name`、extent L3）⇒ **M2 审计直接拒** ⇒ freeze exit 5 |
| **P2** | `pysrc/audit_launcher.py` | 现 M2 profile **强制 HiCache trio** ⇒ detector-only 的 M2 launcher 必被拒（**仅选 (a) 时需要**；选 (a') 免做） |

**Q1 已证（决定性）**：PRE-FIX（冻结树）经**生产入口** `FunctionCallParser` 在孤儿 `</function>`/`<parameter=` 上发出 **6 个 `index<0`**；POST-FIX（工作树）**0 个**。
**线上确能带 `"index":-1`**：`protocol.py:678 index: Optional[int]`（**无 `ge=0`**）；`serving_chat.py:2618`。
**Q3（强烈推断）**：opencode 日志 **两次**同串，均 `modelID=worker` 子代理（`agent=devops`、`agent=coder`）⇒ **很可能就是 subagent 空转之因**（未证）。
**验收**：新树 detector sha == `848e0690…`；确定性 probe **0 负索引**；`TestQwen3CoderDetector` 30 passed / 整文件 256 passed；**M1 detector 保持 `92eeaeaf…`**。
**完整 runbook** 见该 artifact 的 "Q5 — Window runbook"（12 步 + rollback），**照抄执行即可**。

---

## 4. 在飞任务（**读盘对账，勿重复**）

前任在交班前派出以下任务，**可能仍在后台运行**；**新 session 必须按 artifact 路径对账**（不依赖通知）：

| task_id | artifact | 状态（交接时已回件） |
|---|---|---|
| `GGUF-M3M4-RESIDUAL-CAUSE-20260918` | `agents/GGUF-M3M4-RESIDUAL-CAUSE-20260918.md` | ✅ **DONE（243 行）**；**已整合**（见 §3.6）⇒ **无需再对账** |
| `QWEN3CODER-INVALID-INDEX-PROD-20260918` | `agents/QWEN3CODER-INVALID-INDEX-PROD-20260918.md` | ✅ **DONE（443 行）**；推荐路径 **(a)** + 完整 runbook 已交付；两个 CPU 前置 P1/P2 **未派** |

> ⚠️ **前任的重要教训**：**大包（多文件写 / 大设计）系统性返回空结果或 stub**；**小包全部成功**。
> 前任已据此**改为拆小**（§110）。**新 session 沿用该纪律**。

---

## 5. 若需重派（前任拟好的派单要点）

### G1 · M3/M4 post-fix FAIL 定因（CPU 优先）
- 授权依据：owner 规则 —— **仅当**同 GGUF/同 prompt/同采样在 llama.cpp（CPU）**连贯**而 SGLang loop 时，才可开**窄范围**调查。**该条件已满足**（M4 `loop_w4=0.0552`、M3 `0.1029` 连贯）。
- 已证事实：**tokenizer id 修复已闭合**（真件五个 canonical id 全中）；**重跑后仍 FAIL**（`tokenizer_vocab_size=248320` = post-fix）；判据 2（`chat_code` 过、`chat_arithmetic`/`chat_capital`/`chat_tool` 不过）+ 判据 6（M4 `EMPTY_CONTENT`/`DEGENERATE`；M3 `DEGENERATE`/`TOO_SHORT`）。
- 报告路径：`/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs/{m4,m3}/report.json`；门禁 `3090-dev/gates/gguf-sampled-smoke/run_sampled_smoke.sh`（port **30165**，canonical flock，**永不 30000**）。
- 要问：(1) `enable_thinking:false` 是否真在渲染 prompt 中被尊重？(2) `EMPTY_CONTENT` 由什么产生（reasoning parser 吃光？）(3) `TOO_SHORT` 是哪个 stop 触发（检查修复是否改了 eos/special 语义）？(4) 为何 `chat_code` 独过？(5) **最便宜的决定性判别**。

### G2 · M2 发布实施（**含 A**）
- 前置：T3（模板）；`M2-TOOLING-MECH-EDITS`（execute DONE）、`M2-TOOLING-AUDIT-PROFILE`（DONE，81/0）。
- 步骤：**照设计 D7 的 15 步 runbook**。
- 验收：`hicache_attached=True`；**N=16 保留 16/16（原 1/16）**；telemetry 生效（cache/reasoning 字段有值）；**孤儿 `</function>` 的流不再产生 `index:-1`**；`/health` + `/v1/models` loopback+LAN 200。

---

## 6. 已完成（已整合，**勿重做**）

**近两轮关键**（artifact 全在 `agents/`）：
- `GGUF-M3M4-FAILFAST-OFFLINE` — tokenizer 修复在真件上 **CLOSED**；记录的 FAIL = **修前**字节。
- `M3M4-GATE-RERUN` — **post-fix 重跑**：M4/M3 仍 **FAIL**；修复**被真正使用**（vocab 248320）。**生产已恢复**。
- `M2-CONCURRENCY-DEGRADATION-RCA` — **WARM-REMOVES-QUEUE + CACHE-STATE-ROOT-CAUSE**；绑定资源 = **mamba slot 池**；**HiCache 解耦**（24/24）。
- `PROD-STATE-CHECK-R3` / `PROD-LIVENESS-CHECK` — 生产 UP，health 200 loopback+LAN。
- `HOST-CAPACITY-MEASURE` — RAM 充足；**磁盘仅 18.85 GiB** ⇒ HiCache **只用宿主内存模式**。
- `M2-HICACHE-WIRING-RECON` — M2 argv 在冻结 `launcher/launch.sh` 硬编码；门禁现**禁** HiCache；需改门禁 + 审计 + 重钉。
- `M2-HICACHE-RELEASE-DESIGN-R2` — **完整发布设计**（见 §3.4）。
- `M2-TOOLING-MECH-EDITS` — `freeze.sh` DEST 白名单 + 14 条白名单路径（**DONE**）。
- `M2-TOOLING-AUDIT-PROFILE` — `LAUNCHER_PROFILES` + `--profile`，**81 passed / 0 failed**（**DONE**）。
- 早期（历史）：#5 Mamba 线、`REASONING-EFFORT-POLICY-IMPL`、`HICACHE-NATIVE-CACHE-TELEMETRY-R2`、`REASONING-USAGE-TELEMETRY-R4`、`M2-CODING-EVAL-EXEC-E2`、`M2-FROZEN-TREE-INSTALL`、`PROTOCOL-ADVERTISE-*` 等（见 ledger INTEGRATED 表）。

---

## 7. 关键路径速查

```
控制文件      .memory/phase2-hicache-design/ledger.md            （§1–§112；只追加）
本交接        .memory/phase2-hicache-design/HANDOFF-20260918-SESSION-2.md
发布设计      .memory/phase2-hicache-design/agents/M2-HICACHE-RELEASE-DESIGN-R2-20260918.md
A 定因        .memory/phase2-hicache-design/agents/QWEN3CODER-INVALID-INDEX-PROD-20260918.md
M3/M4 定因    .memory/phase2-hicache-design/agents/GGUF-M3M4-RESIDUAL-CAUSE-20260918.md
M3/M4 门禁裁决 .memory/phase2-hicache-design/agents/M3M4-GATE-RERUN-20260918.md
M2 RCA        .memory/phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md
detector 修复  python/sglang/srt/function_call/qwen3_coder_detector.py（工作树 848e0690…；冻结树 92eeaeaf…=缺陷）
冻结工具     3090-dev/tools/freeze/{bin,pysrc,templates,pins}
生产脚手架    /tmp/opencode/prod-service-20260917/{bin/start.sh,bin/stop-m2.sh,conf,state}
复现证据      /tmp/opencode/qwen3coder-invalid-index-20260918/
门禁证据      /mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs/{m4,m3}/report.json
```

---

## 8. 前任自陈的操作纪律（**binding，已写入 ledger 顶部**）

1. **`:30000` 每次上线后主动告知 owner**；**停之前先通知 owner**。
2. **派 worker 前先确认 `:30000` 在服务**。
3. **大包拆小**（§110）：单文件/单交付物；否则系统性 stub。
4. **报告语言中文**；正式报告只写 `Result/Evidence/Remaining/Next`；常规进展一句。
5. **不采信自述**：整合前**读 artifact**；空 `task_result` ⇒ 读盘判终态。
