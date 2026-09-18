# HANDOFF — 2026-09-18 FINAL（编排终止）

> 本文件由 orchestrator 在 **owner 下令停止** 时写入。
> 目的：让任何后继者（人或 agent）在**不依赖对话记忆**的情况下接管。
> 唯一控制文件仍是 `.memory/phase2-hicache-design/ledger.md`（只由 orchestrator 写）。
> 本文件是**交接**，不是控制真相。

---

## 0. 终态（orchestrator 裁定）

**EVIDENCED BLOCKED — 且 owner 已下令终止**（用户授权终止，故不再寻求继续）。

- **未达成** `VERIFIED DONE`。
- `:30000` 生产：**DOWN**（`P7` 报 BLOCKED / NOT-STARTED；首个检查 `00:00:20Z` 时锁已被 sweep5 占据）。
- 全部 ACTIVE 子任务：**所有权关闭**（见 §6）。
- 未决的**实质决策**仍挂在 owner 手上（见 §7）。

---

## 1. 根本性裁定（最重要，务必先读）

**owner 原话：**

1. **本线（P 系列）负责 `:30000`；GPU 控制权归 owner；另一会话负责其他部分（M2/M3/M4/GGUF）。**
2. **这张 3090 是「生产 + 测试」公用资源** ——「早就跟你妈逼说过了这个卡是要生产和测试公用的！」
3. **取消 `48→56→64` mamba sweep**；改走只读容量算账（「先算账，不测试」）。
4. **不得**把「自动检测占卡者并杀掉」写进任何任务/脚本。

### 本 epoch 的错误（已登记，勿重犯）

- **本线把共享 GPU 当成可抢占资源**：`P6` 派单**逐字授权**「停掉任何占卡者 … **包括 `:30000` 上的生产服务**」，
  子代理据此把「停占卡者 → 取 lock → 起自己 server」写进 `run_cell.sh`/`cell_supervise.sh`；
  而 sweep 是**循环**（sweep2→3→4→5）⇒ **每次起 cell 就杀一次生产**。
- **归因失误**：本线两次把凶手写成「外部会话」，而答案就在**本线自己写的 `P6` 派单**里。
  ⇒ 「外部会话杀生产」的结论**已作废**。凶手是**本线自己的 sweep 自动化**。
- **并发反模式**：同一条线并发派了「起生产」(`P4`/`P7`) 与「夺卡跑 sweep」(`P5`/`P6`) ⇒ **互杀**。

### 正确运行协议（binding，取代一切旧机制）

1. `:30000` 是**常驻服务**，默认 UP；测试窗口结束**必须无条件恢复** UP + LAN 200。
2. 测试窗口 = **申请 + 让步**，不是夺取；腾卡需 **owner 就该次窗口批准**；窗口**有界**。
3. **禁止**任何「自动杀占卡者」逻辑。
4. **单一所有者**：任一时点只有一个 GPU 窗口所有者；新窗口前**先显式收回**前一个。
5. **生产优先**：冲突时生产胜出，测试退让重排。

---

## 2. 环境与范围

| 项 | 值 |
|---|---|
| 仓库 | `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`，分支 `3090-24g-opt` |
| HEAD | `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`（本轮由 `910e5a01c0` 推进） |
| 主机 | `sglang-build`（"VM 2500"），`eth0=192.168.20.250` |
| GPU | 单卡 RTX 3090 24GB —— **生产与测试互斥于同一时刻，但必须共用/轮流** |
| 控制文件 | `.memory/phase2-hicache-design/ledger.md`（**被另一 session 并发追加**，见 §5） |
| 生产脚手架 | `/tmp/opencode/prod-service-20260917/`（`bin/start.sh`/`stop.sh`/`supervise.sh`、`state/gpu-owner.json`） |
| 冻结树（当前被服务） | `/opt/sglang/local-prod-v1.2.1-candidate`（**IDENTITY-DIVERGED**，勿编辑） |
| 待建冻结树 | `/opt/sglang/local-prod-v1.2.2-candidate`（**尚未构建**） |
| canonical lock | `/tmp/opencode/gpu-3090.lock` |
| 共享 L3 | `/data/l3/local-prod-v1.1`（**只读，绝不 clear**） |
| 勿动 | `3090-dev/gates/**`（归 M 线） |

---

## 3. 已完成（有据）

### 3.1 缺陷 #1 — client context metadata ✅
- `~/.config/opencode/opencode.json`：`provider.opencodex.models.*.limit.context` 8× `400000 → 131072`。
- `gpt-5.5` 的 `262144` **未动**。
- **残留**：该修改同时改了 4 个 `.bak-*` 备份文件（额外 19 处替换）⇒ **无法回滚到原始 400000**。
  **运行期复验待客户端 reload**（现行 pid 早于修改时间）。

### 3.2 HTTP400 取证 ✅
- 400 为 **2026-09-17 13:13–13:16** 的 **4 个失败请求（8 行日志）**，模型 `gpt-5.6-luna`，经网关 `192.168.1.203:3456`。
- 原始报文引用 **262144**，**无任何 400 引用 400000**。
- `400000` 是**使能因素**（推迟了 OpenCode 压缩到 ~380K）。
- **残留未决**：本地 SGLang total-token 余量；15 个不相关的 `reasoning_content` 400；不可达网关主机上可能的 400000。

### 3.3 `switch-codex` 调查 ✅（已关闭）
- **不在本机**（root `find / -xdev` 0 命中；`debugfs` 无删除项；内容 grep 0 命中）。owner 确认在另一台机器。
- ⇒ **超出范围**，**勿再搜**。

### 3.4 `qquestion` 幻觉调查 ✅
- **真实存在**：`/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/server.console.log:2580`
  `Tool 'qquestion' is not defined in the tools list.`
- 唯一发射点：`python/sglang/srt/function_call/qwen3_coder_detector.py:91`。
- 生产 `--tool-call-parser qwen3_coder` = `Qwen3CoderDetector` = **会把未声明工具 SURFACE 出去**
  （base/gpt_oss/lfm2/pythonic 会跳过）。
- harness **从未**执行/持久化 `qquestion` 调用。
- 另见 `upstream response contained invalid tool calls (invalid index)` @ 21:57:55。

### 3.5 Gate-A / F1 harness ✅ 已提交
- `GATEA-CLOSURES-IMPLEMENT-20260917` R3b DONE（74 tests OK）。
- `R4` 复审 = **APPROVE-WITH-CONDITIONS**；D1(b)/D2/L4/L5 全清；无 false-PASS；两解释器下 74/74。
  唯一条件 A1（文档）已由 ledger 记录关闭。
- **commit `3f2a417e95330829c57c4cb8446e764abb801313`**（6 个 harness 路径，显式路径提交）。

### 3.6 v1.2.2 冻结工具链 ✅ 已提交
- **commit `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`**。
- `templates/launch.sh.tmpl:146 --host 192.168.20.250`、`:147 --served-model-name qwen35-9b-local`、
  `:151-153` context 131072 / max-running 8 / mamba 48。
- `bin/freeze.sh:127` 允许列表加入 `/opt/sglang/local-prod-v1.2.2-candidate`。
- `audit_launcher.py` fail-closed 矩阵已验证（未知 host / 未知 served-model-name / 缺 served-model-name / `--api-key` 全 FAIL；无 blanket 规则）。
- `test_audit_launcher.py` 修好（57 passed / 0 failed）。
- ⚠️ **v1.2.2 树尚未构建**。

### 3.7 `qwen3_coder` 裁决 ✅（且审计通过）
- **写域 = 恰好 2 个文件**：
  - `python/sglang/srt/function_call/qwen3_coder_detector.py`
  - 扩展 `test/registered/unit/function_call/test_function_call_parser.py` 的 `TestQwen3CoderDetector`
  - **勿动** `base_format_detector.py` / `function_call_parser.py`。
- 五个缺陷（均已 CONFIRMED）：
  1. 重复 `</function>` ⇒ 多余 `}`；
  2. 缺 `</function>` ⇒ 未闭合 JSON；
  3. `-1` 来自**孤儿片段**（**不是** base 的 `tool_indices.get(name,-1)`，那条不可达）；
  4. 继承的 `finish()` 是 **no-op**；
  5. 名字提取吞掉正文。
- 单一 EOS 规则 = **delay-commit**：仅当见到 `</tool_call>` 才成为结构化调用；否则 `finish()` 把原始字节作为
  `normal_text` 返回。
- **独立审计裁决：可照现状实现**；五缺陷全 CONFIRMED；单文件写域足够；**无生产安全阻断**。
  仅两处**文档性**更正：(C1) 显式调和 EOS=退回 content 与 P1 §3.2「不得把已解码调用退化为正文」、§4 rows 6/7「usable-empty」；
  (C2) 把 row 3b 明确标为「owner 可翻转的默认」。
- ⚠️ **代码尚未落地**（见 §4.3）。

### 3.8 已知事实（省得后继者重查）
- `:30000` **LAN 可达**（`curl 192.168.20.250:30000/health` → 200，曾验证）。
- **model id 不是阻断**：`model="qwen35-9b-local"` 与旧 id 均返回 200。
- 冻结树 `/opt/sglang/local-prod-v1.2.1-candidate` **有 4 个 pin 面**：
  `TREE_HASH`（现 `5ed662d0…`，原 pin `3bd285d5…`）、`SOURCE_COMMIT=b2bbd6ea28`、
  `launcher/launch.sh:146`、以及 **`launcher/launch.sh:29 EXPECTED_SRC_STREAM_SHA256`**（launch GATE 2/3，不匹配 exit 12）。
  ⇒ **任何 `src/` 改动都会强制 4 个 pin 全部重钉**。目标文件需先 `chmod`（文件 444、`src/` 555）再恢复。
  ⇒ **live server 导入的是冻结树**（`PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`），
  **只改 workspace 副本对生产是 NO-OP**。
- **无 `pkill`/`killall`**；只用身份校验的 `stop.sh`/`start.sh`、进程组处理。
- **冷启动 ≈ 132 s**。
- 禁改：template / sampling / model / quantization / 任何 serving flag；禁把网关校验挪进 parser；
  禁加 tool-name 校验（pass-through 正确）；禁静默丢弃调用或退化为文本；
  **禁为造证据加测试设施或重启生产**。
- 分工（owner）：网关 = 信任边界，永远校验 wire 不变量；SGLang = 「不得 GENERATE 非法 wire 状态」。

---

## 4. 未完成（关键）

### 4.1 `:30000` 生产 UP —— **未达成**
- 本轮被启动 4 次，每次被杀。**根因 = 本线自己 sweep 的自动杀逻辑**（§1）。
- `P7`（最后一次起生产尝试）因窗口被 sweep5 占据而 **BLOCKED / NOT-STARTED**，行为正确（未抢、未杀）。
- `P9` = 终止 sweep + 起生产 + 保持，**在 owner 下令终止时仍处 teardown（WORKING）**，**结果未产出/未消费**。
  ⇒ **生产当前状态需后继者自行核实**（可能 DOWN，也可能 P9 已在终止前起了）。

### 4.2 缺陷 #5 Mamba L2 容量账 —— **未达成**
- `P8`（只读）**仅 stub（WORKING）**，无结论。
- 待答：从 **LOCAL 代码**追溯 Mamba host pool 构造，从启动日志恢复 4 个量
  （Mamba device slots/GB、KV device tokens/GB、Mamba host GB、KV host GB），
  建立 `restore needs 3436–3556` 与 `free_before=142` 的**确切单位**（**未定单位前不得断言「25× 差距」**），
  然后给**单一裁决**：(A) 容量不足 ⇒ 调 `--hicache-size`（**不是** `max-mamba-cache-size`）；
  (B) 拆分比例错 ⇒ 改比例 / 小 patch；(C) allocator/回收 bug ⇒ 加内存无用。
- 已知：`--max-mamba-cache-size` 定的是 **DEVICE pool**；`--hicache-size=32` 按 device-pool 字节**比例拆分**
  ⇒ 48 → mamba host 7.31 GB / KV host 1,509,560 tokens；56 → 8.19 GB / 1,455,589 tokens。
- PUBLIC 只有全局 `--hicache-ratio` / `--hicache-size`（size 覆盖 ratio）；**未见 `mamba-hicache-size` CLI 杠杆**。
- 先前的 `48/56/64` sweep **未复现**生产故障（sweep 格产出 `WAIT_CAPACITY reason=FRONTIER`、
  零 `HOST_ALLOC`/`failed_domains`；生产是 42× `WAIT_CAPACITY/HOST_ALLOC`、`failed_domains=["mamba"]`、
  `free_before=0`、required ~3436–3556、每格停 60 s）⇒ **不能用于定容**，已作废。

### 4.3 缺陷 #6 `qwen3_coder` 代码落地 —— **未达成**
- `Q3A3` 派单后 **artifact 从未创建**（§5.11：无有效 terminal artifact = 未完成）。
- 更早的 `Q3a`/`Q3A2` 两次尝试：**一次把 repo 文件改脏**（mutant `3c1a06a1…`），**一次无 artifact**。
- 原始字节 sha256 = `92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089`。
- repo 内该文件可能**仍是脏的**（`3c1a06a1…`）⇒ 后继者**必须先核对/还原**。
- 落地后仍需 fold 进 v1.2.2 冻结树（连 #5 的最终杠杆一起，**避免建两次**）。

### 4.4 v1.2.2 冻结树 —— **未构建**
- `/opt/sglang/local-prod-v1.2.2-candidate` **不存在**。
- 构建需 **GPU 窗口 / owner 批准**；且应**等 #5 最终杠杆 + #6 parser 修复就位后再建**。

### 4.5 缺陷 #2/#4 —— 未动
- temperature/top_p A/B：**deferred**（owner 曾缓议）。

---

## 5. 危险区 / 陷阱（必读）

1. **`ledger.md` 控制真相已降级**：本 epoch 它从 ~8,180 行涨到 **~10,867 行**，**被另一 orchestrator session 并发追加**
   （对方用「激活 #N」编号）。两条线**对称地把对方误认成入侵者**。
   - 本线**不删除/不覆盖**对方条目。
   - **bootstrap 自己的编排前，务必先读 ledger 行 ~10561-10655（B 线「激活 #9」段）** —— 那里有对方**让出 `:30000`**、
     对方对进程链的取证、以及 owner 对它的仲裁原话。
2. **不要新建「归因取证」任务** —— 凶手已自证（本线 sweep）。`KILLCHAIN-ATTRIBUTION-20260918` 结果**不采信**。
3. **不要重跑 48/56/64 sweep** —— owner 永久取消。
4. **不要并行派第二个含 GPU/`:30000` 权限的任务**。单一所有者。
5. **worktree 卫生**：禁 `git add -A`；只用显式路径提交；禁 push/amend/rebase/reset。
   （曾有提交正确地把无关的 `gate_common.py` 删除**取消暂存**。）
6. `/tmp/opencode/mamba-sweep-20260918/`（64M 证据）**保留，勿删**。
7. `3090-dev/gates/**` 归 M 线；`gate_common.py` 在那边缺失**不是本线的事**，**勿碰**。
8. `gpu-owner.json` 可能是**陈旧**的（如 `lock_generation 14`）；判断「谁持有 GPU」以 **canonical lock 文件**为准。
9. 冻结树 pin 机制（§3.8）——**只改 workspace 是 NO-OP**。

---

## 6. 所有权关闭（本次终止）

| task_id | 角色 | 关闭时状态 | 处置 |
|---|---|---|---|
| `P9-KILL-OWN-SWEEP-AND-START-PROD-20260918` | devops-executor | WORKING（teardown 中；已定位 sweep 进程树、**确认无自动重启循环**） | **TERMINATED（owner 令）**；结果未消费 |
| `P8-MAMBA-L2-CAPACITY-ACCOUNTING-20260918` | debugger-deep | WORKING（stub） | **TERMINATED**；无结论 |
| `Q3A3-QWEN3CODER-IMPLEMENT-20260918` | coder | **artifact 不存在**（从未交付） | **TERMINATED / CLOSED** |
| `AUDIT-QWEN3CODER-ADJUDICATION-20260918` | reviewer | DONE | 已消费（§3.7） |
| `P7-PROD-START-FINAL-20260918` | devops-executor | BLOCKED | 已消费 ⇒ 由 P9 取代 ⇒ 关闭 |
| `KILLCHAIN-ATTRIBUTION-20260918` | devops | — | **作废**（已被自证取代） |
| `MAMBA-SWEEP-EVIDENCE-ASSESS` / `P5` / `P6` | — | — | 定容用途**作废** |
| `48/56/64` sweep | — | — | **永久取消** |

> 注：工具面无「取消后台 subagent」原语。实际终止 = 关闭所有权 + 停止一切派发 + 不再消费其 artifact。

---

## 7. 待 owner 决策（未决实质项）

| # | 决策 | 选项 | 后果 | 建议 |
|---|---|---|---|---|
| D1 | `:30000` 是否现在起 | (a) 免 sweep、给一个干净窗口起并保持；(b) 暂不起 | (a)=可回归 go-live 测试；(b)=生产继续 DOWN | **(a)**，且窗口内**不得**任何测试并发 |
| D2 | #5 走哪条 | (A) 加 `--hicache-size`；(B) 改拆分比例；(C) 认定回收 bug | (A)/(B) 需重启验证；(C) 加内存无用 | **先等 `P8` 类只读算账出结论**，再定 |
| D3 | v1.2.2 何时建 | (a) 等 #5+#6 就位一次建；(b) 先建骨架 | (b)=可能建两次 | **(a)** |
| D4 | `.bak-*` 备份已被污染（§3.1） | 接受 / 重建备份 | 影响回滚能力 | owner 定 |

---

## 8. 后继者最快路径

1. **读 `ledger.md` 行 ~10561-10655**（B 线让位段）+ 本文件。
2. **核实 `:30000` 与 GPU 当前状态**：
   `pgrep -af sglang.launch_server`；`ss -ltnp | grep -E '30000|30160'`；
   `cat /tmp/opencode/gpu-3090.lock`；`curl -sS -m5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health`。
3. 若 `:30000` DOWN ⇒ 取 D1=(a) 的窗口 ⇒ **单次** `bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`
   （冷启动 ~132 s）⇒ 验 loopback + **LAN 200** + 一次 smoke ⇒ 保持复核。
4. #5：派**只读**容量算账（不占卡）。
5. #6：核对 repo 文件 sha ⇒ 还原至 `92eeaeaf…` ⇒ 按 2 文件写域实现 ⇒ 跑
   `test/registered/unit/function_call/test_function_call_parser.py`。
6. 二者就位后**一次**构建 v1.2.2 冻结树（含 4 个 pin 重钉）。

---

## 9. 关键路径速查

```
控制文件        .memory/phase2-hicache-design/ledger.md                (~10,867 行, 并发追加)
本交接          .memory/phase2-hicache-design/HANDOFF-20260918-FINAL.md
结果 artifacts  .memory/phase2-hicache-design/agents/*.md
生产脚手架      /tmp/opencode/prod-service-20260917/{bin,state,logs}/
canonical lock  /tmp/opencode/gpu-3090.lock
sweep 证据      /tmp/opencode/mamba-sweep-20260918/  (64M, 保留)
parser 目标     python/sglang/srt/function_call/qwen3_coder_detector.py
parser 测试     test/registered/unit/function_call/test_function_call_parser.py
v1.2.2 工具链   3090-dev/tools/freeze/{templates,pysrc,bin}
冻结树(现役)    /opt/sglang/local-prod-v1.2.1-candidate   (勿编辑)
冻结树(待建)    /opt/sglang/local-prod-v1.2.2-candidate
client 配置     ~/.config/opencode/opencode.json
```

**Terminal verdict: EVIDENCED BLOCKED / OWNER-ORDERED STOP.**
